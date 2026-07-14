"""
Unit tests for the score_captions engine wrapper (src/ner_scorer.py).

These cover the explicit-reference path (reference_text provided), which needs
no transcriber and no ML stack, so they run fast in CI. The auto-transcribe
path (faster-whisper / Granite Speech) is exercised end to end in
test_engine_end_to_end.py under graceful-degradation conditions.
"""
from __future__ import annotations

from src.models import CaptionCue
from src.ner_scorer import score_captions


def _cue(index: int, text: str) -> CaptionCue:
    return CaptionCue(index=index, start=float(index), end=float(index) + 1.0,
                      text=text, lines=[text])


def test_perfect_match_scores_one_with_no_errors():
    ref = "hello world this is a caption"
    cues = [_cue(1, "hello world"), _cue(2, "this is a caption")]
    r = score_captions(cues, "unused.mp4", reference_text=ref)
    assert r.ner_score == 1.0
    assert r.recognition_errors == 0
    assert r.edition_errors == 0
    assert r.n_words == len(ref.split())


def test_reference_relative_score_is_banded_and_asr_derived():
    # The caption paraphrases and drops words relative to the spoken reference.
    ref = "they are coming to get you barbara stop it now i mean it"
    cues = [_cue(1, "they are coming for you barbara"), _cue(2, "stop it")]
    r = score_captions(cues, "unused.mp4", reference_text=ref)
    assert r.n_words == len(ref.split())
    assert 0.0 <= r.ner_score <= 1.0
    assert r.band_low <= r.ner_score <= r.band_high
    # asr_derived must be True so the FCC accuracy rule flags for review,
    # never auto-fails (Koenecke et al. PNAS 2020).
    assert r.asr_derived is True


def test_hypothesis_is_built_from_all_cues():
    # Multi-line cue text is flattened; every cue contributes to the hypothesis.
    ref = "one two three four"
    cues = [_cue(1, "one\ntwo"), _cue(2, "three four")]
    r = score_captions(cues, "unused.mp4", reference_text=ref)
    # Reference matches the joined hypothesis exactly -> perfect score.
    assert r.ner_score == 1.0
