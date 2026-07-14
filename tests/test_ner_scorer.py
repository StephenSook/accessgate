"""
Tests for the NER-style caption scorer.
"""
import pytest
from src.ner_scorer import score_ner, _clean_text
from src.models import NERScoreResult


def test_perfect_match():
    """Identical reference and hypothesis → NER = 1.0."""
    result = score_ner("hello world this is a test", "hello world this is a test")
    assert result.ner_score == 1.0
    assert result.n_errors == 0


def test_empty_reference():
    """Empty reference → skip (score = 1.0, n_words = 0)."""
    result = score_ner("", "some hypothesis text")
    assert result.ner_score == 1.0
    assert result.n_words == 0


def test_below_98_threshold():
    """One substitution in a 10-word reference → should be below 98%."""
    ref = "the quick brown fox jumps over the lazy dog now"
    hyp = "the quick brown fox jumps over the lazy cat now"  # 1 sub
    result = score_ner(ref, hyp)
    assert result.ner_score < 1.0
    assert result.n_errors >= 1


def test_band_contains_point_estimate():
    """Confidence band must always bracket the point estimate."""
    ref = "the quick brown fox jumps over the lazy dog"
    hyp = "the fast brown fox leaps over a lazy dog"
    result = score_ner(ref, hyp)
    assert result.band_low <= result.ner_score <= result.band_high


def test_asr_derived_flag():
    """asr_derived=True means never auto-fail; passes_98_threshold is False
    when band straddles the threshold, not just when score is below."""
    ref = "one two three four five six seven eight nine ten"
    hyp = "one two three four five six seven eight nine cat"  # 1/10 error = 90%
    result = score_ner(ref, hyp, asr_derived=True)
    assert result.asr_derived is True
    # With heavy errors, neither band nor score should be >= 98%
    assert not result.passes_98_threshold


def test_high_confidence_recognition_error():
    """Phonetically similar substitution with low confidence → recognition error."""
    result = score_ner(
        reference="the cat sat on the mat",
        hypothesis="the cat sat on the bat",
        word_confidences=[0.9, 0.9, 0.9, 0.9, 0.9, 0.2],  # last word low conf
    )
    assert result.recognition_errors >= 1


def test_low_confidence_regions_flagged():
    """Low-confidence word regions must appear in the flagged list."""
    result = score_ner(
        reference="hello world test phrase end",
        hypothesis="hello world test phrase and",
        word_confidences=[0.95, 0.95, 0.95, 0.95, 0.1],
    )
    assert len(result.low_confidence_regions) >= 1


def test_clean_text_normalisation():
    assert _clean_text("Hello, World!") == "hello world"
    assert _clean_text("It's a test.") == "its a test"
    assert _clean_text("  spaces  ") == "spaces"


def test_result_is_pydantic_model():
    result = score_ner("hello world", "hello world")
    assert isinstance(result, NERScoreResult)


def test_consecutive_recognition_errors_counted_per_word():
    """Three consecutive low-confidence substitutions (serious recognition
    errors) must count as ~3 errors, not 1. Counting one-per-alignment-chunk
    under-reported serious ASR mishears and could wrongly clear the 98% FCC
    threshold on materially inaccurate captions."""
    base = ["alpha", "bravo", "charlie", "delta", "echo",
            "foxtrot", "golf", "hotel", "india", "juliet"]
    ref_words = base * 10  # 100 words
    ref = " ".join(ref_words)
    hyp_words = ref_words.copy()
    hyp_words[10:13] = ["xray", "yankee", "zulu"]  # 3 consecutive substitutions
    hyp = " ".join(hyp_words)
    confs = [0.95] * 100
    confs[10] = confs[11] = confs[12] = 0.2  # low confidence -> recognition errors
    result = score_ner(ref, hyp, word_confidences=confs)
    assert result.n_errors >= 3, f"expected >=3 errors, got {result.n_errors}"
    assert result.recognition_errors >= 3, f"expected 3 recognition errors, got {result.recognition_errors}"
    assert result.ner_score <= 0.98, f"3 serious errors must not clear 98%, got {result.ner_score}"


def test_edition_errors_are_minor():
    """Meaning-preserving omissions (edition errors) are minor under the NER
    model and must NOT tank the score the way serious recognition errors do."""
    ref = " ".join(["word"] * 100)
    hyp_words = ["word"] * 100
    del hyp_words[10:13]  # drop three words -> deletions -> edition (condensation)
    hyp = " ".join(hyp_words)
    result = score_ner(ref, hyp)
    assert result.edition_errors >= 3
    # 3 minor editions at weight 0.25 barely move the score.
    assert result.ner_score > 0.98


def test_threshold_fields_are_serialized():
    """passes_98_threshold / straddles_threshold must be @computed_field so they
    appear in the JSON the frontend reads; as bare @property they were absent and
    the NER indicator was pinned to amber."""
    result = score_ner("hello world this is a test", "hello world this is a test")
    dumped = result.model_dump()
    assert "passes_98_threshold" in dumped
    assert "straddles_threshold" in dumped
    assert dumped["passes_98_threshold"] is True  # perfect score clears 98%
