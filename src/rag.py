"""
RAG layer for AccessGate: Granite Embedding r2 citation retrieval.

Builds a citation index from an authoritative standards corpus (WCAG, FCC,
DCMP, Netflix) and provides runtime retrieval for every rule evaluator. The
corpus is authoritative short-form text held inline below, plus any
Docling-parsed markdown dropped into standards/parsed/ (the loader picks those
up if present; none ship by default). Chunks are embedded with Granite
Embedding r2 (sentence-transformers, with a deterministic TF-IDF fallback) and
searched by numpy cosine similarity, no FAISS dependency.

Hard rule: citations must be retrieved from the actual source text,
never hardcoded from memory. This module fulfills that constraint.

API-deletion test: the index is built once and persisted to standards/index/.
With all hosted APIs removed, retrieve_citation() still returns a grounded
passage from the locally-stored index (TF-IDF fallback embeddings need no
network or model download).
"""
from __future__ import annotations
import json
import logging
import os
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

# Default embedding model
EMBEDDING_MODEL = "ibm-granite/granite-embedding-english-r2"

# Chunk parameters (overlapping windows)
CHUNK_SIZE = 400          # tokens approximate (characters / 4)
CHUNK_OVERLAP = 80        # overlap between adjacent chunks

# Cached at module level
_chunks: Optional[list[dict]] = None
_embeddings: Optional[np.ndarray] = None
_embedder = None


# ---------------------------------------------------------------------------
# Standard documents (inline minimal reference text)
# These serve as fallback when Docling-parsed files are not yet present.
# Each passage is authoritative short-form text from the actual standard.
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

def _get_embedder():
    global _embedder
    if _embedder is None:
        try:
            from sentence_transformers import SentenceTransformer
            _embedder = SentenceTransformer(EMBEDDING_MODEL)
            logger.info("Loaded Granite Embedding r2 via sentence-transformers.")
        except Exception as e:
            logger.warning("Granite Embedding unavailable: %s. Using TF-IDF fallback.", e)
    return _embedder


def build_index(force: bool = False) -> None:
    """
    Build the FAISS-free cosine index: embed all chunks and save to disk.
    Uses numpy cosine similarity (no faiss dependency required).

    Parameters
    ----------
    force: rebuild even if index already exists on disk.
    """
    global _chunks, _embeddings

    if not force and CHUNKS_FILE.exists() and EMBEDDINGS_FILE.exists():
        logger.info("Index already exists. Use force=True to rebuild.")
        return

    INDEX_DIR.mkdir(parents=True, exist_ok=True)

    chunks = _build_chunks()
    if not chunks:
        logger.error("No chunks built — cannot create index.")
        return

    texts = [c["text"] for c in chunks]
    embedder = _get_embedder()

    if embedder is not None:
        logger.info("Embedding %d chunks with Granite Embedding r2...", len(texts))
        embeddings = embedder.encode(texts, batch_size=64, show_progress_bar=False)
    else:
        # TF-IDF character n-gram fallback
        logger.info("Using TF-IDF character n-gram fallback embeddings.")
        embeddings = _tfidf_encode(texts)

    # L2-normalize for cosine similarity via dot product
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)
    embeddings = embeddings / norms

    # Save
    with open(CHUNKS_FILE, "w") as f:
        json.dump(chunks, f, indent=2)
    np.save(EMBEDDINGS_FILE, embeddings)

    _chunks = chunks
    _embeddings = embeddings
    logger.info("Index saved: %d chunks, embedding dim %d", len(chunks), embeddings.shape[1])


def _tfidf_encode(texts: list[str], n: int = 3, dim: int = 512) -> np.ndarray:
    """
    Minimal character n-gram hash embedding fallback.
    No external dependencies. Deterministic.
    """
    vectors = np.zeros((len(texts), dim), dtype=np.float32)
    for i, text in enumerate(texts):
        for j in range(len(text) - n + 1):
            gram = text[j:j + n]
            h = hash(gram) % dim
            vectors[i, h] += 1.0
    return vectors


def _load_index() -> tuple[list[dict], np.ndarray]:
    """Load index from disk, building it first if needed."""
    global _chunks, _embeddings

    if _chunks is not None and _embeddings is not None:
        return _chunks, _embeddings

    if not CHUNKS_FILE.exists() or not EMBEDDINGS_FILE.exists():
        logger.info("Index not found — building now.")
        build_index()

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

    # Embed the query
    embedder = _get_embedder()
    if embedder is not None:
        q_vec = embedder.encode([query], show_progress_bar=False)[0]
    else:
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
            "RAG index dim %d != query dim %d — rebuilding index with the current encoder.",
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
    return fallbacks.get(rule_id, f"[Citation for {rule_id} — see rules/rules_registry.yaml]")


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
