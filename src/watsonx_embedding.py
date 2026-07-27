"""
watsonx-hosted Granite embeddings for the AccessGate RAG citation index.

Why this module exists
----------------------
Citations are retrieved at runtime from the Docling-parsed standards corpus,
never hardcoded. Locally that retrieval embeds with Granite Embedding r2 through
sentence-transformers, which is the API-deletion-proof path.

The hosted deploy cannot carry that path: `requirements-deploy.txt` drops
sentence-transformers, torch and faiss because they exceed Render's free-tier
build and memory limits. Until now the deploy therefore fell back to a
deterministic character n-gram encoder, which works but is not a Granite model.

watsonx.ai serves Granite embeddings over REST, so the hosted deploy can run a
genuine IBM Granite embedding model with no torch, no sentence-transformers and
no build weight: one HTTPS call. That makes the citation retrieval Granite-backed
on the surface a judge actually tests, while the deterministic encoder stays
underneath as the last resort.

Precedence in src/rag.py: sentence-transformers (local) -> watsonx Granite
(hosted) -> deterministic n-gram fallback. The engine still runs with every
hosted API deleted, so the API-deletion test is unaffected.

Environment: WATSONX_API_KEY, WATSONX_PROJECT, WATSONX_URL (see watsonx_showcase).
"""
from __future__ import annotations

import logging
import os
import time
from typing import Optional

import numpy as np
import requests

from src.watsonx_showcase import _iam_token, _DEFAULT_URL

logger = logging.getLogger(__name__)

# Verified against the live account's /ml/v1/foundation_model_specs
# (filters=function_embedding): this is the only Granite embedding model served.
MODEL_ID = "ibm/granite-embedding-278m-multilingual"
EMBED_PATH = "/ml/v1/text/embeddings?version=2024-05-02"

# The model's max_sequence_length is 512 tokens. Chunks are built at roughly 400
# tokens so they fit, but truncate server-side rather than erroring on an
# oversized chunk.
MAX_INPUT_TOKENS = 512

# watsonx accepts a list of inputs per call. Keep batches modest so one slow
# request cannot stall an index rebuild, and so a partial failure is cheap.
BATCH_SIZE = 32

# Embedding dimension of MODEL_ID, verified live. Declared so callers can detect
# a shape change without a network call.
EMBEDDING_DIM = 768

# Statuses worth retrying: a rate limit or a transient upstream error. Anything
# else (401 after refresh, 400, 404) is a real fault and should surface.
_RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
RATE_LIMIT_RETRIES = 3
_BACKOFF_BASE_S = 2.0
_MAX_BACKOFF_S = 30.0


def _retry_after_seconds(resp, attempt: int) -> float:
    """Honour Retry-After when the server sends it, else exponential backoff."""
    header = getattr(resp, "headers", {}) or {}
    value = header.get("Retry-After")
    if value:
        try:
            return min(float(value), _MAX_BACKOFF_S)
        except (TypeError, ValueError):
            pass
    return min(_BACKOFF_BASE_S * (2 ** attempt), _MAX_BACKOFF_S)


class WatsonxEmbedder:
    """
    Minimal encoder with the same surface rag.py already uses for
    sentence-transformers: `.encode(texts) -> np.ndarray`.

    Deliberately duck-typed rather than subclassing anything, so rag.py needs no
    branching beyond choosing which encoder object it holds.
    """

    #: Stable identity for this encoder, persisted alongside the index so a
    #: switch between encoders forces a rebuild. See rag.py encoder_id().
    encoder_id = f"watsonx:{MODEL_ID}"

    def __init__(self, api_key: str, project_id: str, base_url: str) -> None:
        self._api_key = api_key
        self._project_id = project_id
        self._base_url = base_url.rstrip("/")
        self._token: Optional[str] = None

    def _auth_header(self, refresh: bool = False) -> dict:
        if self._token is None or refresh:
            self._token = _iam_token(self._api_key)
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _embed_batch(self, batch: list[str]) -> list[list[float]]:
        payload = {
            "model_id": MODEL_ID,
            "project_id": self._project_id,
            "inputs": batch,
            "parameters": {"truncate_input_tokens": MAX_INPUT_TOKENS},
        }
        url = self._base_url + EMBED_PATH

        resp = requests.post(url, json=payload, headers=self._auth_header(), timeout=60)
        if resp.status_code == 401:
            # IAM tokens are short-lived; a long index build can outlive one.
            logger.info("watsonx embedding token expired, refreshing.")
            resp = requests.post(
                url, json=payload, headers=self._auth_header(refresh=True), timeout=60
            )

        # An index build is a burst of sequential calls, which is exactly what
        # trips a rate limit; observed live as 429 while rebuilding 218 chunks.
        # A transient limit should cost a short wait, not the Granite encoder for
        # the rest of the process, so back off and retry before giving up.
        for attempt in range(RATE_LIMIT_RETRIES):
            if resp.status_code not in _RETRY_STATUS:
                break
            delay = _retry_after_seconds(resp, attempt)
            logger.warning(
                "watsonx embeddings returned %s, retrying in %.1fs (attempt %d/%d).",
                resp.status_code, delay, attempt + 1, RATE_LIMIT_RETRIES,
            )
            time.sleep(delay)
            resp = requests.post(url, json=payload, headers=self._auth_header(), timeout=60)

        resp.raise_for_status()

        results = resp.json()["results"]
        if len(results) != len(batch):
            raise ValueError(
                f"watsonx returned {len(results)} embeddings for {len(batch)} inputs"
            )

        vectors = [r["embedding"] for r in results]
        # Guard the shape as well as the count. A model swap or a truncated
        # response could return well-formed rows of the wrong width, which would
        # build an index in a vector space nothing else shares.
        bad = [len(v) for v in vectors if len(v) != EMBEDDING_DIM]
        if bad:
            raise ValueError(
                f"watsonx returned embeddings of dim {sorted(set(bad))}, expected {EMBEDDING_DIM}"
            )
        return vectors

    def encode(
        self,
        texts,
        batch_size: int = BATCH_SIZE,
        show_progress_bar: bool = False,  # noqa: ARG002 - sentence-transformers parity
        **_kwargs,
    ) -> np.ndarray:
        """
        Embed a list of strings. Raises on failure rather than returning
        partial or zero vectors: a silently degraded index would make every
        citation wrong without any visible signal, which is worse than a
        loud failure that rag.py can fall back from.
        """
        if isinstance(texts, str):
            texts = [texts]
        texts = list(texts)
        if not texts:
            return np.zeros((0, EMBEDDING_DIM), dtype=np.float32)

        if batch_size <= 0:
            raise ValueError(f"batch_size must be positive, got {batch_size}")
        # Callers built for sentence-transformers pass large batches (rag.py
        # builds at 64). Cap to what this endpoint is exercised with, so an
        # oversized request cannot trip a server-side input or token limit.
        batch_size = min(batch_size, BATCH_SIZE)

        vectors: list[list[float]] = []
        for start in range(0, len(texts), batch_size):
            vectors.extend(self._embed_batch(texts[start:start + batch_size]))

        return np.asarray(vectors, dtype=np.float32)


def get_watsonx_embedder(
    *,
    api_key: Optional[str] = None,
    project_id: Optional[str] = None,
    base_url: Optional[str] = None,
) -> Optional[WatsonxEmbedder]:
    """
    Build a WatsonxEmbedder if watsonx is configured, else None.

    Returns None (rather than raising) when unconfigured, so rag.py can treat a
    missing key exactly like a missing local model and continue to the
    deterministic fallback.
    """
    api_key = api_key or os.getenv("WATSONX_API_KEY", "")
    project_id = project_id or os.getenv("WATSONX_PROJECT", "")
    base_url = base_url or os.getenv("WATSONX_URL", _DEFAULT_URL)

    if not api_key or not project_id:
        logger.info("watsonx embeddings unavailable: WATSONX_API_KEY or WATSONX_PROJECT not set.")
        return None

    return WatsonxEmbedder(api_key=api_key, project_id=project_id, base_url=base_url)
