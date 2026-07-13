"""
Tests for the VAD gap detection engine.
Uses synthetic speech/silence regions to avoid needing real media files.
"""
import pytest
from src.gap_engine import compute_gaps, cue_overlaps_speech, ad_overlaps_speech
from src.models import SpeechRegion, GapRegion, CaptionCue


# ── compute_gaps ──────────────────────────────────────────────────────────────

def test_gaps_complement_of_speech():
    """Basic: single speech region in middle of 30s clip."""
    speech = [SpeechRegion(start=10.0, end=20.0)]
    gaps = compute_gaps(speech, total_duration=30.0, min_gap=2.5)
    # Should find gap before speech (0–10) and after (20–30)
    assert len(gaps) == 2
    assert abs(gaps[0].start - 0.0) < 0.01
    assert abs(gaps[0].end - 10.0) < 0.01
    assert abs(gaps[1].start - 20.0) < 0.01
    assert abs(gaps[1].end - 30.0) < 0.01


def test_gaps_min_duration_filter():
    """Gaps below min_gap should be filtered out."""
    # Speech regions with tiny gap between them (1s)
    speech = [
        SpeechRegion(start=5.0, end=10.0),
        SpeechRegion(start=11.0, end=20.0),
    ]
    gaps = compute_gaps(speech, total_duration=25.0, min_gap=2.5)
    # The 1s gap between 10-11 should be filtered
    gap_starts = [g.start for g in gaps]
    assert not any(abs(s - 10.0) < 0.1 for s in gap_starts), \
        f"1s gap should be filtered, got gaps: {gaps}"


def test_gaps_merge_blip():
    """Sub-300ms speech blips between gaps should be merged."""
    # Two long silences separated by a 0.2s speech blip
    speech = [
        SpeechRegion(start=0.0, end=5.0),
        SpeechRegion(start=8.0, end=8.2),   # 0.2s blip
        SpeechRegion(start=15.0, end=20.0),
    ]
    gaps = compute_gaps(speech, total_duration=25.0, min_gap=2.5, merge_blip=0.3)
    # The gap 5.0–15.0 (spanning the blip) should be merged into one
    big_gaps = [g for g in gaps if g.duration > 5.0]
    assert len(big_gaps) >= 1


def test_no_speech_returns_one_gap():
    """No speech regions → entire clip is one gap."""
    gaps = compute_gaps([], total_duration=30.0, min_gap=2.5)
    assert len(gaps) == 1
    assert abs(gaps[0].start - 0.0) < 0.01
    assert abs(gaps[0].end - 30.0) < 0.01


def test_all_speech_returns_no_gaps():
    """Speech covering entire clip → no gaps."""
    speech = [SpeechRegion(start=0.0, end=30.0)]
    gaps = compute_gaps(speech, total_duration=30.0, min_gap=2.5)
    assert len(gaps) == 0


def test_gap_duration_property():
    gaps = compute_gaps(
        [SpeechRegion(start=5.0, end=10.0)],
        total_duration=15.0, min_gap=2.5
    )
    assert any(abs(g.duration - 5.0) < 0.01 for g in gaps)


def test_gaps_sorted_by_start():
    speech = [
        SpeechRegion(start=5.0, end=10.0),
        SpeechRegion(start=15.0, end=20.0),
    ]
    gaps = compute_gaps(speech, total_duration=30.0, min_gap=2.5)
    starts = [g.start for g in gaps]
    assert starts == sorted(starts)


# ── cue_overlaps_speech ───────────────────────────────────────────────────────

def _make_cue(start: float, end: float) -> CaptionCue:
    return CaptionCue(index=1, start=start, end=end, text="test", lines=["test"])


def test_cue_overlaps_speech_direct():
    """Cue squarely inside speech region → overlaps."""
    speech = [SpeechRegion(start=10.0, end=20.0)]
    cue = _make_cue(12.0, 15.0)
    assert cue_overlaps_speech(cue, speech, tolerance_ms=500) is True


def test_cue_within_tolerance():
    """Cue starts just after speech ends but within 500ms tolerance → overlaps."""
    speech = [SpeechRegion(start=10.0, end=15.0)]
    cue = _make_cue(15.3, 17.0)  # 300ms after speech ends
    assert cue_overlaps_speech(cue, speech, tolerance_ms=500) is True


def test_cue_outside_tolerance():
    """Cue starts well after speech ends → no overlap."""
    speech = [SpeechRegion(start=10.0, end=15.0)]
    cue = _make_cue(16.0, 18.0)  # 1s after speech ends
    assert cue_overlaps_speech(cue, speech, tolerance_ms=500) is False


def test_cue_no_speech_regions():
    """No speech regions → no overlap."""
    cue = _make_cue(5.0, 8.0)
    assert cue_overlaps_speech(cue, [], tolerance_ms=500) is False


# ── ad_overlaps_speech ────────────────────────────────────────────────────────

def test_ad_overlaps_speech():
    speech = [SpeechRegion(start=10.0, end=20.0)]
    assert ad_overlaps_speech(12.0, 15.0, speech) is True


def test_ad_does_not_overlap_speech():
    speech = [SpeechRegion(start=10.0, end=20.0)]
    assert ad_overlaps_speech(5.0, 9.9, speech) is False
    assert ad_overlaps_speech(20.1, 25.0, speech) is False
