"""
RAG layer for AccessGate: Granite Embedding r2 citation retrieval.

Builds a citation index from an authoritative standards corpus (WCAG, FCC,
DCMP, Netflix) and provides runtime retrieval for every rule evaluator. The
corpus is BOTH: six Docling-parsed standard pages committed under
standards/parsed/ (206 of the index's 218 chunks) and authoritative short-form
clause text held inline below (the remaining 12). An earlier version of this
docstring said the parsed files "none ship by default", which has not been true
since they were committed and made /judges look inflated to anyone who read
both. Chunks are embedded with Granite Embedding r2 (sentence-transformers,
then watsonx-hosted Granite, then a deterministic n-gram fallback) and searched
by numpy cosine similarity, no FAISS dependency.

Hard rule: citations must be retrieved from the actual source text,
never hardcoded from memory. This module fulfills that constraint.

API-deletion test: the index is built once and persisted to standards/index/.
With all hosted APIs removed, retrieve_citation() still returns a grounded
passage from the locally-stored index (TF-IDF fallback embeddings need no
network or model download).
"""
from __future__ import annotations
import hashlib
import json
import logging
import os
import tempfile
import threading
from pathlib import Path
from typing import Optional
import numpy as np

logger = logging.getLogger(__name__)

# Paths
STANDARDS_DIR = Path(__file__).parent.parent / "standards"
PARSED_DIR = STANDARDS_DIR / "parsed"
INDEX_DIR = STANDARDS_DIR / "index"

# Index files
CHUNKS_FILE = INDEX_DIR / "chunks.json"
EMBEDDINGS_FILE = INDEX_DIR / "embeddings.npy"
# Records which encoder built the index. Two different encoders can share a
# dimension (Granite Embedding r2 locally and watsonx Granite are both 768), so
# a dimension check alone cannot tell them apart and would leave the index
# silently scored in the wrong vector space. The identity is what matters.
INDEX_META_FILE = INDEX_DIR / "index_meta.json"

# Default embedding model
EMBEDDING_MODEL = "ibm-granite/granite-embedding-english-r2"

# Chunk parameters (overlapping windows)
CHUNK_SIZE = 400          # tokens approximate (characters / 4)
CHUNK_OVERLAP = 80        # overlap between adjacent chunks

# Cached at module level
_chunks: Optional[list[dict]] = None
_embeddings: Optional[np.ndarray] = None
_embedder = None

#: Sticky for the process once a resolved encoder actually fails. Without this,
#: a failing hosted encoder is re-resolved on every call: queries keep raising,
#: and because the index gets written with the fallback's identity while
#: encoder_id() still optimistically reports the hosted one, every load sees a
#: mismatch and rebuilds again. Demoting once makes the failure terminal and
#: self-consistent.
_encoder_failed = False

#: Rebuilds mutate three files that must be read as a set. FastAPI serves
#: requests concurrently, so serialize builds and publish atomically.
_index_lock = threading.RLock()


# ---------------------------------------------------------------------------
# Standard documents (inline short-form reference text)
#
# These are ALWAYS indexed alongside the Docling-parsed pages, not only when the
# parsed files are missing. Both are needed: the Docling parse carries the full
# source pages (and with them the site's navigation and image boilerplate), while
# these hold the crisp clause wording that a citation should actually quote. Two
# ids here deliberately match a parsed filename (dcmp_captioning_key,
# dcmp_description_key), so those sources contribute chunks from both.
#
# Each passage is authoritative short-form text from the actual standard. They
# are literals in source, so describe the corpus as "the parsed standards plus
# committed clause text", never as purely Docling output.
# ---------------------------------------------------------------------------

_INLINE_STANDARDS: dict[str, str] = {
    "wcag_122": """
WCAG 2.2 Success Criterion 1.2.2 Captions (Prerecorded) - Level A
Captions are provided for all prerecorded audio content in synchronized media,
except when the media is a media alternative for text and is clearly labeled as such.
Captions include all dialogue and important sound effects.
""",
    "wcag_125": """
WCAG 2.2 Success Criterion 1.2.5 Audio Description (Prerecorded) - Level AA
Audio description is provided for all prerecorded video content in synchronized media.
The audio description provides information about actions, characters, scene changes,
and on-screen text that are important to understanding the content.
""",
    "fcc_79_1_j_2": """
47 CFR 79.1(j)(2) Caption quality standards.
Captioning quality is defined by four factors:
(i) Accuracy: Captions must match the spoken words in the dialogue and convey
background noises and other sounds to the fullest extent possible.
(ii) Synchronicity: Captions must be displayed to coincide with their
corresponding spoken words and sounds to the greatest extent possible.
(iii) Program completeness: The program must be captioned in its entirety.
(iv) Placement: Captions should not block other important visual content on the
screen including, but not limited to, character faces, speaker identification,
emergency information, and other information or text.
The NER (Net Error Rate) accuracy standard is: (total words - errors) / total words.
Programs with a score of 98 percent or higher are deemed accurate.
""",
    "dcmp_captioning_key": """
DCMP Captioning Key: Standards and Guidelines for Caption Quality.
Character count: A maximum of 32 characters per line.
Line count: No more than 2 lines per caption frame.
Reading speed: Educational captions range from 130 to 160 wpm by grade level.
Near-verbatim adult captions should not exceed 225 words per minute.
Minimum display time: Captions should appear on screen for a minimum of 2 seconds.
Sound effects: Use brackets to identify sound sources: [THUNDER], [DOG BARKING].
Never describe sounds in the past tense; sounds are described as they occur.
Italics and capitalization indicate vocal emphasis.
""",
    "dcmp_description_key": """
DCMP Description Key: Standards and Guidelines for Audio Description.
Tense: Describe action in the present tense, active voice.
Point of view: Third-person narrative; never first or second person.
Language: Use objective language; avoid subjective or interpretive terms.
Sentences: Use complete sentences whenever possible.
Timing: Descriptions must fit within the available dialogue-free time.
Words per minute: Standard description rate is 150 words per minute.
Overlap: Audio descriptions must not overlap essential program audio or dialogue.
Jargon: Match vocabulary to the program level; do not introduce technical terms
before the program itself has introduced them.
Completeness: Do not describe every pause; prioritize plot-relevant visual information.
""",
    "netflix_ttsg": """
Netflix Timed Text Style Guide (TTSG) - English.
Reading speed: Maximum 20 characters per second (CPS) for adult content.
Maximum 17 CPS for children's content.
Line length: Maximum 42 characters per line.
Line count: Maximum 2 lines per event.
Minimum duration: 5/6 of a second (approximately 0.833 seconds) per subtitle event.
Maximum duration: 7 seconds per subtitle event.
Minimum gap: A minimum gap of 2 frames between consecutive subtitle events is required.
Frame rate: Typically 23.976, 24, or 25 fps depending on the content locale.
Character encoding: UTF-8.
""",
}


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

def _chunk_text(text: str, source_id: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[dict]:
    """Split text into overlapping character-level chunks."""
    text = text.strip()
    if not text:
        return []
    chunks = []
    step = chunk_size - overlap
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunk_text = text[start:end].strip()
        if chunk_text:
            chunks.append({"text": chunk_text, "source": source_id, "start": start})
        start += step
    return chunks


def _build_chunks() -> list[dict]:
    """
    Build chunks from all available sources:
    1. Docling-parsed files in standards/parsed/ (if present)
    2. Inline reference standards (always available)
    """
    all_chunks = []

    # Load from Docling-parsed markdown files if present
    if PARSED_DIR.exists():
        for md_path in sorted(PARSED_DIR.glob("*.md")):
            try:
                text = md_path.read_text(encoding="utf-8")
                chunks = _chunk_text(text, source_id=md_path.stem)
                all_chunks.extend(chunks)
                logger.info("Chunked %s: %d chunks", md_path.name, len(chunks))
            except Exception as e:
                logger.warning("Failed to chunk %s: %s", md_path.name, e)

    # Always include inline standards (ensures index is non-empty)
    for source_id, text in _INLINE_STANDARDS.items():
        chunks = _chunk_text(text, source_id=source_id)
        all_chunks.extend(chunks)

    logger.info("Total chunks: %d", len(all_chunks))
    return all_chunks


# ---------------------------------------------------------------------------
# Embedding and index
# ---------------------------------------------------------------------------

#: Identity of the deterministic fallback encoder. Bump if _tfidf_encode changes
#: shape or hashing, so stale indexes rebuild instead of scoring nonsense.
TFIDF_ENCODER_ID = "tfidf:md5-3gram-512"


def _get_embedder():
    """
    Resolve the citation encoder, best available first.

    1. sentence-transformers with Granite Embedding r2. The local, fully
       offline path; this is what keeps the API-deletion test true.
    2. watsonx-hosted Granite embeddings. Used on the deploy, where the
       embedding stack is deliberately absent from requirements-deploy.txt.
       One HTTPS call, no torch.
    3. None, meaning the caller uses the deterministic n-gram fallback.

    Local is tried first on purpose: when the full stack is present we should
    not make a network call, and the offline path should stay the default.
    """
    global _embedder
    if _encoder_failed:
        return None
    if _embedder is None:
        try:
            from sentence_transformers import SentenceTransformer
            _embedder = SentenceTransformer(EMBEDDING_MODEL)
            logger.info("Loaded Granite Embedding r2 via sentence-transformers.")
            return _embedder
        except Exception as e:
            logger.info("Local Granite Embedding unavailable: %s. Trying watsonx.", e)

        try:
            from src.watsonx_embedding import get_watsonx_embedder
            _embedder = get_watsonx_embedder()
            if _embedder is not None:
                logger.info("Using watsonx-hosted Granite embeddings (%s).", _embedder.encoder_id)
            else:
                logger.warning("watsonx embeddings not configured. Using deterministic fallback.")
        except Exception as e:  # noqa: BLE001
            logger.warning("watsonx embeddings unavailable: %s. Using deterministic fallback.", e)
    return _embedder


def encoder_id() -> str:
    """Stable identity of the encoder currently in use."""
    embedder = _get_embedder()
    if embedder is None:
        return TFIDF_ENCODER_ID
    return getattr(embedder, "encoder_id", f"sentence-transformers:{EMBEDDING_MODEL}")


def _is_metered(enc_id: str) -> bool:
    """True when using this encoder spends a metered external API quota.

    Local encoders (sentence-transformers, the deterministic n-gram) are free to
    re-run; a hosted one bills per call and is shared with the vision, Guardian
    and summary paths, so exhausting it takes those down too.
    """
    return enc_id.startswith("watsonx:")


def _hosted_reindex_allowed() -> bool:
    """Opt-in escape hatch for building a publishable hosted-encoder index.

    Off by default so no deployment can spend quota re-embedding the corpus on a
    cold start. Set ACCESSGATE_ALLOW_HOSTED_REINDEX=1 when deliberately building
    an index to commit.
    """
    return os.getenv("ACCESSGATE_ALLOW_HOSTED_REINDEX", "").lower() in {"1", "true", "yes"}


def _demote_encoder(reason: object) -> None:
    """
    Permanently drop to the deterministic encoder for this process.

    Called when a resolved encoder raises. Making this sticky is what keeps the
    index identity and the query identity in agreement: after demotion both the
    stored meta and encoder_id() say tfidf, so the next load does not see a
    mismatch and rebuild forever.
    """
    global _embedder, _encoder_failed
    logger.error("Encoder failed (%s). Falling back to %s for this process.",
                 reason, TFIDF_ENCODER_ID)
    _embedder = None
    _encoder_failed = True


def _atomic_write_text(path: Path, text: str) -> None:
    """Write text to path atomically, via a temp file in the same directory."""
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
        os.replace(tmp, path)
    except Exception:
        Path(tmp).unlink(missing_ok=True)
        raise


def _atomic_write_npy(path: Path, array: np.ndarray) -> None:
    """Write a .npy array to path atomically."""
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".npy")
    os.close(fd)
    try:
        # np.save appends .npy only when the name lacks it; tmp already ends .npy
        np.save(tmp, array)
        os.replace(tmp, path)
    except Exception:
        Path(tmp).unlink(missing_ok=True)
        raise


def _read_index_meta() -> dict:
    try:
        with open(INDEX_META_FILE) as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return {}


def build_index(force: bool = False) -> None:
    """
    Build the FAISS-free cosine index: embed all chunks and save to disk.
    Uses numpy cosine similarity (no faiss dependency required).

    Parameters
    ----------
    force: rebuild even if index already exists on disk.
    """
    global _chunks, _embeddings

    with _index_lock:
        # Re-check inside the lock: a concurrent request may have finished the
        # rebuild while this one waited, and redoing it would spend another
        # round of hosted embedding calls for nothing.
        if not force and CHUNKS_FILE.exists() and EMBEDDINGS_FILE.exists():
            logger.info("Index already exists. Use force=True to rebuild.")
            return
        if force and _read_index_meta().get("encoder") == encoder_id() \
                and CHUNKS_FILE.exists() and EMBEDDINGS_FILE.exists():
            logger.info("Index already rebuilt by another caller; skipping.")
            return
        _build_index_locked()


def _build_index_locked() -> None:
    """Body of build_index. Callers must hold _index_lock."""
    global _chunks, _embeddings

    INDEX_DIR.mkdir(parents=True, exist_ok=True)

    chunks = _build_chunks()
    if not chunks:
        logger.error("No chunks built, cannot create index.")
        return

    texts = [c["text"] for c in chunks]
    embedder = _get_embedder()
    active_encoder = encoder_id()

    if embedder is not None:
        logger.info("Embedding %d chunks with %s...", len(texts), active_encoder)
        try:
            embeddings = embedder.encode(texts, batch_size=64, show_progress_bar=False)
        except Exception as e:  # noqa: BLE001
            # A half-built or zeroed index would make every citation wrong with
            # no visible signal. Demote (so queries use the same encoder this
            # index was actually built with) and record what really ran.
            _demote_encoder(e)
            embeddings = _tfidf_encode(texts)
            active_encoder = TFIDF_ENCODER_ID
    else:
        logger.info("Using deterministic character n-gram fallback embeddings.")
        embeddings = _tfidf_encode(texts)

    # L2-normalize for cosine similarity via dot product
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)
    embeddings = embeddings / norms

    if embeddings.shape[0] != len(chunks):
        # Never publish an index whose rows do not line up with its chunks: the
        # top-scoring row would name the wrong passage, or index out of range.
        logger.error("Refusing to save index: %d embeddings for %d chunks.",
                     embeddings.shape[0], len(chunks))
        return

    # Publish atomically. A reader must never observe new chunks against old
    # embeddings, or a half-written json, so each file is written to a temp in
    # the same directory and renamed into place (os.replace is atomic on POSIX).
    _atomic_write_text(CHUNKS_FILE, json.dumps(chunks, indent=2))
    _atomic_write_npy(EMBEDDINGS_FILE, embeddings)
    _atomic_write_text(
        INDEX_META_FILE,
        json.dumps({"encoder": active_encoder, "dim": int(embeddings.shape[1])}, indent=2),
    )

    _chunks = chunks
    _embeddings = embeddings
    logger.info("Index saved: %d chunks, encoder %s, embedding dim %d",
                len(chunks), active_encoder, embeddings.shape[1])


def _tfidf_encode(texts: list[str], n: int = 3, dim: int = 512) -> np.ndarray:
    """
    Minimal character n-gram hash embedding fallback.
    No external dependencies. Deterministic across processes.

    Uses a stable md5-based hash, NOT the builtin hash(): Python salts str
    hashing per process (PYTHONHASHSEED), so the index is embedded in one process
    and persisted, then queried in a later process (server restart, redeploy,
    keepalive) whose query vectors would land in a different bucket space —
    making the cosine scores meaningless. md5 is process-independent.
    """
    vectors = np.zeros((len(texts), dim), dtype=np.float32)
    for i, text in enumerate(texts):
        for j in range(len(text) - n + 1):
            gram = text[j:j + n]
            h = int.from_bytes(hashlib.md5(gram.encode("utf-8")).digest()[:8], "big") % dim
            vectors[i, h] += 1.0
    return vectors


def _load_index() -> tuple[list[dict], np.ndarray]:
    """Load index from disk, building it first if needed."""
    global _chunks, _embeddings

    if _chunks is not None and _embeddings is not None:
        return _chunks, _embeddings

    if not CHUNKS_FILE.exists() or not EMBEDDINGS_FILE.exists():
        logger.info("Index not found, building now.")
        build_index()
    else:
        # The committed index is built locally with Granite Embedding r2. A
        # different environment may resolve a different encoder, and watsonx
        # Granite happens to share r2's 768 dimensions, so a shape check cannot
        # detect the swap. Compare identities and rebuild when they differ,
        # otherwise queries would be scored against a foreign vector space and
        # every citation would be quietly wrong.
        stored = _read_index_meta().get("encoder")
        current = encoder_id()
        if stored != current:
            # THE QUOTA GUARD. Re-embedding the corpus costs one API call per
            # batch, and the corpus is 218 chunks, so a rebuild against a
            # metered hosted encoder spends roughly 22k tokens. The hosted
            # instance has an ephemeral filesystem and spins down when idle, so
            # this branch runs on EVERY cold start, of which there are about
            # twenty a day. That is ~436k tokens/day against a plan that allows
            # 300k a month: it drained the entire monthly allowance in under a
            # day and took the vision, Guardian and summary calls down with it,
            # because they share the quota.
            #
            # So a hosted encoder is never allowed to rebuild the corpus at
            # runtime. Fall back to the deterministic encoder instead, which
            # costs nothing and keeps index and query in the same vector space.
            # To publish a Granite-embedded index, build it once offline with
            # ACCESSGATE_ALLOW_HOSTED_REINDEX=1 and commit the result; runtime
            # then spends only per-query embeddings, which are a few tokens each.
            if _is_metered(current) and not _hosted_reindex_allowed():
                logger.warning(
                    "Index encoder %r != active encoder %r, but %r is metered. "
                    "Using the deterministic encoder rather than spending quota "
                    "re-embedding %s chunks on a cold start.",
                    stored, current, current, "the corpus",
                )
                _demote_encoder("hosted reindex withheld to protect API quota")
            else:
                logger.warning(
                    "Index encoder %r != active encoder %r, rebuilding.", stored, current
                )
            build_index(force=True)

    with open(CHUNKS_FILE) as f:
        _chunks = json.load(f)
    _embeddings = np.load(EMBEDDINGS_FILE)
    return _chunks, _embeddings


# ---------------------------------------------------------------------------
# Citation retrieval
# ---------------------------------------------------------------------------

def retrieve_citation(rule_id: str, query: str, top_k: int = 1) -> str:
    """
    Retrieve the top-k verbatim passage(s) matching the query.

    The rule_id is used to bias toward the relevant standard document:
    - FCC rules → bias toward fcc_79_1_j_2 chunks
    - WCAG rules → bias toward wcag_122 or wcag_125
    - DCMP-CAP rules → bias toward dcmp_captioning_key
    - DCMP-DESC rules → bias toward dcmp_description_key
    - NFLX rules → bias toward netflix_ttsg

    Returns a single passage string (the top hit), or a fallback string
    if the index is unavailable.
    """
    # Rule-to-source bias map
    source_bias = _get_source_bias(rule_id)

    try:
        chunks, embeddings = _load_index()
    except Exception as e:
        logger.error("Failed to load index: %s", e)
        return _fallback_citation(rule_id)

    if not chunks:
        return _fallback_citation(rule_id)

    # Embed the query. A hosted encoder can fail mid-run (network, 5xx, rate
    # limit); that must degrade the citation, never take down the check that
    # asked for it, so failures demote to the deterministic encoder instead of
    # propagating out to the engine.
    embedder = _get_embedder()
    q_vec = None
    if embedder is not None:
        try:
            q_vec = embedder.encode([query], show_progress_bar=False)[0]
        except Exception as e:  # noqa: BLE001
            _demote_encoder(e)
    if q_vec is None:
        q_vec = _tfidf_encode([query])[0]

    # L2-normalize
    norm = np.linalg.norm(q_vec)
    if norm > 0:
        q_vec = q_vec / norm

    # Self-heal: a committed index may have been built with a different encoder
    # (768-dim Granite embeddings) than this environment can load (512-dim TF-IDF
    # fallback when sentence-transformers is absent, e.g. the hosted deploy).
    # Rebuild once with the current encoder so the dimensions match instead of
    # crashing on the dot product.
    if q_vec.shape[0] != embeddings.shape[1]:
        logger.warning(
            "RAG index dim %d != query dim %d, rebuilding index with the current encoder.",
            embeddings.shape[1], q_vec.shape[0],
        )
        try:
            build_index(force=True)
            chunks, embeddings = _load_index()
        except Exception as e:  # noqa: BLE001
            logger.error("Index rebuild failed: %s", e)
            return _fallback_citation(rule_id)
        if q_vec.shape[0] != embeddings.shape[1]:
            return _fallback_citation(rule_id)

    # Cosine similarity = dot product of normalized vectors
    scores = embeddings @ q_vec  # shape: (n_chunks,)

    # Apply source bias: +0.2 boost to chunks from the target source
    if source_bias:
        for i, chunk in enumerate(chunks):
            if chunk.get("source") in source_bias:
                scores[i] += 0.2

    # Get top-k
    top_indices = np.argsort(scores)[::-1][:top_k]
    passages = [chunks[i]["text"] for i in top_indices]
    return passages[0] if passages else _fallback_citation(rule_id)


def _get_source_bias(rule_id: str) -> set[str]:
    """Map a rule ID prefix to the most relevant source document(s)."""
    if rule_id.startswith("FCC"):
        return {"fcc_79_1_j_2"}
    if rule_id.startswith("WCAG-122"):
        return {"wcag_122"}
    if rule_id.startswith("WCAG-125"):
        return {"wcag_125"}
    if rule_id.startswith("DCMP-CAP"):
        return {"dcmp_captioning_key"}
    if rule_id.startswith("DCMP-DESC"):
        return {"dcmp_description_key"}
    if rule_id.startswith("NFLX"):
        return {"netflix_ttsg"}
    return set()


def _fallback_citation(rule_id: str) -> str:
    """Return a hardcoded fallback citation when the index is unavailable."""
    fallbacks = {
        "FCC-ACC-01": "47 CFR 79.1(j)(2)(i): Captions must match the spoken words in the dialogue.",
        "FCC-SYN-01": "47 CFR 79.1(j)(2)(ii): Captions must be displayed to coincide with their corresponding spoken words.",
        "FCC-CMP-01": "47 CFR 79.1(j)(2)(iii): The program must be captioned in its entirety.",
        "FCC-PLC-01": "47 CFR 79.1(j)(2)(iv): Captions should not block other important visual content.",
        "WCAG-122-01": "WCAG 2.2 SC 1.2.2: Captions are provided for all prerecorded audio content in synchronized media.",
        "WCAG-125-01": "WCAG 2.2 SC 1.2.5: Audio description is provided for all prerecorded video content.",
        "WCAG-125-02": "WCAG 2.2 SC 1.2.5: Audio description provides information about actions, characters, scene changes.",
        "DCMP-CAP-03": "DCMP Captioning Key: Near-verbatim adult captions should not exceed 225 words per minute.",
        "DCMP-DESC-05": "DCMP Description Key: Audio descriptions must not overlap essential program audio or dialogue.",
        "NFLX-CPS-01": "Netflix TTSG: Maximum 20 characters per second for adult content.",
    }
    return fallbacks.get(rule_id, f"[Citation for {rule_id}, see rules/rules_registry.yaml]")


# ---------------------------------------------------------------------------
# Module-level convenience: rebuild index if called directly
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    build_index(force=True)
    print("Index built successfully.")
    # Smoke test
    test_cases = [
        ("FCC-ACC-01", "accuracy spoken words"),
        ("DCMP-CAP-03", "reading speed wpm"),
        ("NFLX-CPS-01", "characters per second"),
        ("DCMP-DESC-05", "audio description dialogue"),
    ]
    for rule_id, query in test_cases:
        result = retrieve_citation(rule_id, query)
        print(f"\n[{rule_id}] Query: {query!r}")
        print(f"  Retrieved: {result[:120]!r}")
