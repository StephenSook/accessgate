"""
NER-style caption accuracy scorer for AccessGate.
Load-Bearing Artifact #1 (scoring core).

Formula: NER = (N - E - R) / N
Where:
  N = total reference word count
  E = edition errors (meaning-preserving paraphrases/omissions)
  R = recognition errors (ASR mishears)

Source: Romero-Fresco & Pérez (2015), Ofcom 98% broadcast threshold.
Koenecke et al. PNAS 2020: never auto-fail on ASR evidence alone.

Hard rule (AGENTS.md):
  NEVER auto-fail a caption. ASR-derived scores are reference-relative,
  confidence-banded, and low-confidence regions are flagged for human review.
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from jiwer import process_words, AlignmentChunk
from src.models import NERScoreResult

# Ofcom/Romero-Fresco threshold
NER_ACCEPTABLE_THRESHOLD = 0.98

# Word confidence below this → treat as recognition-uncertain (down-weight)
LOW_CONFIDENCE_THRESHOLD = 0.6

# Semantic similarity above this → treat as edition (meaning-preserving)
MEANING_PRESERVED_THRESHOLD = 0.85


def score_ner(
    reference: str,
    hypothesis: str,
    word_confidences: list[float] | None = None,
    asr_derived: bool = True,
) -> NERScoreResult:
    """
    Compute NER-style caption accuracy score with confidence band.

    Args:
        reference: The reference transcript (from Granite Speech or human gold).
        hypothesis: The caption text to score (from the caption file).
        word_confidences: Per-word probability from faster-whisper (optional).
                          If provided, used to classify recognition errors.
        asr_derived: True if the reference came from ASR (not human gold).
                     When True, the hard rule applies: never auto-fail.

    Returns:
        NERScoreResult with point estimate, confidence band, and flagged regions.
    """
    reference = _clean_text(reference)
    hypothesis = _clean_text(hypothesis)

    if not reference:
        # No reference — cannot score, skip this check
        return NERScoreResult(
            ner_score=1.0, band_low=1.0, band_high=1.0,
            n_words=0, n_errors=0,
            recognition_errors=0, edition_errors=0,
            asr_derived=asr_derived,
        )

    result = process_words(reference, hypothesis)
    N = len(reference.split())

    recognition_errors = 0
    edition_errors = 0
    ambiguous_errors = 0
    low_confidence_regions: list[dict] = []

    ref_words = reference.split()
    hyp_words = hypothesis.split()

    for chunk in result.alignments[0]:
        if chunk.type == "equal":
            continue

        ref_slice = ref_words[chunk.ref_start_idx:chunk.ref_end_idx]
        hyp_slice = hyp_words[chunk.hyp_start_idx:chunk.hyp_end_idx]

        # Get word confidence for this chunk (if available)
        conf = _get_chunk_confidence(chunk, word_confidences, len(ref_words))

        error_type = _classify_error(
            ref_slice, hyp_slice, chunk.type, conf
        )

        if error_type == "recognition":
            recognition_errors += 1
        elif error_type == "edition":
            edition_errors += 1
        else:  # ambiguous
            ambiguous_errors += 1

        if conf is not None and conf < LOW_CONFIDENCE_THRESHOLD:
            low_confidence_regions.append({
                "ref_words": ref_slice,
                "hyp_words": hyp_slice,
                "confidence": conf,
                "chunk_type": chunk.type,
            })

    # Point estimate: ambiguous errors split 50/50
    E_point = edition_errors + ambiguous_errors * 0.5
    R_point = recognition_errors + ambiguous_errors * 0.5
    ner_point = max(0.0, (N - E_point - R_point) / N) if N > 0 else 1.0

    # Band: best-case = all ambiguous are edition (heavily down-weighted)
    #       worst-case = all ambiguous are recognition
    E_best = edition_errors + ambiguous_errors
    R_best = recognition_errors
    ner_best = max(0.0, (N - E_best * 0.5 - R_best) / N) if N > 0 else 1.0

    E_worst = edition_errors
    R_worst = recognition_errors + ambiguous_errors
    ner_worst = max(0.0, (N - E_worst - R_worst) / N) if N > 0 else 1.0

    return NERScoreResult(
        ner_score=round(ner_point, 4),
        band_low=round(min(ner_worst, ner_best), 4),
        band_high=round(max(ner_worst, ner_best), 4),
        n_words=N,
        n_errors=recognition_errors + edition_errors + ambiguous_errors,
        recognition_errors=recognition_errors,
        edition_errors=edition_errors,
        asr_derived=asr_derived,
        low_confidence_regions=low_confidence_regions,
    )


def _clean_text(text: str) -> str:
    """Normalize text for WER scoring: lowercase, strip punctuation."""
    text = text.lower()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _get_chunk_confidence(
    chunk: AlignmentChunk,
    word_confidences: list[float] | None,
    n_ref_words: int,
) -> float | None:
    """Get average confidence for a chunk's reference words."""
    if word_confidences is None:
        return None
    try:
        start = chunk.ref_start_idx
        end = min(chunk.ref_end_idx, len(word_confidences))
        if start >= end:
            return None
        confs = word_confidences[start:end]
        return sum(confs) / len(confs) if confs else None
    except (IndexError, AttributeError):
        return None


def _classify_error(
    ref_words: list[str],
    hyp_words: list[str],
    chunk_type: str,
    confidence: float | None,
) -> str:
    """
    Classify an error chunk as 'recognition', 'edition', or 'ambiguous'.

    Recognition error: ASR mishears — phonetically similar, low confidence,
                       meaning NOT preserved.
    Edition error: meaning-preserving paraphrase or omission a human editor
                   might make.

    Returns: 'recognition' | 'edition' | 'ambiguous'
    """
    # Deletions (words in reference, not in hypothesis) →
    # likely edition (omission) unless confidence is very low
    if chunk_type == "delete":
        if confidence is not None and confidence < LOW_CONFIDENCE_THRESHOLD:
            return "recognition"
        return "edition"

    # Insertions (words in hypothesis, not in reference) →
    # typically edition errors
    if chunk_type == "insert":
        return "edition"

    # Substitutions: check phonetic similarity + confidence
    if chunk_type == "substitute" and ref_words and hyp_words:
        try:
            import jellyfish
            ref_str = " ".join(ref_words)
            hyp_str = " ".join(hyp_words)
            # Jaro-Winkler similarity: 0–1, high = similar
            similarity = jellyfish.jaro_winkler_similarity(ref_str, hyp_str)

            # Phonetic match (same Metaphone code) → recognition error
            ref_meta = jellyfish.metaphone(ref_words[0]) if len(ref_words) == 1 else None
            hyp_meta = jellyfish.metaphone(hyp_words[0]) if len(hyp_words) == 1 else None
            phonetically_similar = (ref_meta and hyp_meta and ref_meta == hyp_meta)

            if phonetically_similar or (
                confidence is not None and confidence < LOW_CONFIDENCE_THRESHOLD
            ):
                return "recognition"
            if similarity > MEANING_PRESERVED_THRESHOLD:
                return "edition"
            return "ambiguous"
        except Exception:
            pass

    return "ambiguous"
