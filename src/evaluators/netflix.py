"""
Netflix Timed Text Style Guide (English) evaluators.
NFLX-CPS-01, NFLX-LEN-01, NFLX-DUR-01.

Source: Netflix Partner Help Center TTSG, re-verified July 2026.
Numbers: 20 CPS adult / 17 CPS children; 42 chars/line; 2 lines;
         minimum 5/6 second to 7 seconds; 2-frame minimum gap.
Citations are placeholders — replaced by RAG layer at runtime.
"""
from __future__ import annotations
from src.models import CaptionCue, RuleResult
from src.registry import get_rule

# Netflix English TTSG confirmed values
NETFLIX_MAX_CPS_ADULT = 20.0
NETFLIX_MAX_CPS_CHILDREN = 17.0
NETFLIX_MAX_CHARS_PER_LINE = 42
NETFLIX_MAX_LINES = 2
NETFLIX_MIN_DURATION_S = 5 / 6      # five-sixths of a second ≈ 0.833s
NETFLIX_MAX_DURATION_S = 7.0
NETFLIX_MIN_GAP_FRAMES = 2
NETFLIX_FRAME_RATE = 24.0           # default; real check would use the file's frame rate


def eval_nflx_cps_01(
    cues: list[CaptionCue],
    profile: str = "adult",
) -> list[RuleResult]:
    """
    NFLX-CPS-01: Caption CPS must not exceed 20 (adult) or 17 (children).
    Note: Netflix uses characters-per-second (not WPM).
    The older WPM section was removed in a TTSG revision — cite CPS only.
    """
    rule = get_rule("NFLX-CPS-01")
    max_cps = NETFLIX_MAX_CPS_CHILDREN if profile == "children" else NETFLIX_MAX_CPS_ADULT
    results = []

    for cue in cues:
        if cue.duration <= 0:
            continue
        cps = cue.cps
        if cps > max_cps:
            results.append(RuleResult(
                rule_id=rule.id, status="fail",
                message=(
                    f"Caption at {cue.start:.2f}s exceeds {max_cps} CPS "
                    f"({cps:.1f} CPS, {profile} profile). "
                    f"Text: {cue.text[:50]!r}"
                ),
                timecode=cue.start,
                citation=rule.source, sarif_level=rule.sarif_level,
            ))

    if not results:
        results.append(RuleResult(
            rule_id=rule.id, status="pass",
            message=f"All captions within {max_cps} CPS ({profile} profile).",
            citation=rule.source, sarif_level=rule.sarif_level,
        ))
    return results


def eval_nflx_len_01(cues: list[CaptionCue]) -> list[RuleResult]:
    """
    NFLX-LEN-01: Maximum 42 characters per line, maximum 2 lines per event.
    """
    rule = get_rule("NFLX-LEN-01")
    results = []

    for cue in cues:
        issues = []
        for line in cue.lines:
            if len(line) > NETFLIX_MAX_CHARS_PER_LINE:
                issues.append(f"line {len(line)} chars: {line!r}")
        if len(cue.lines) > NETFLIX_MAX_LINES:
            issues.append(f"{len(cue.lines)} lines (max {NETFLIX_MAX_LINES})")

        if issues:
            results.append(RuleResult(
                rule_id=rule.id, status="fail",
                message=f"Caption at {cue.start:.2f}s: {'; '.join(issues)}",
                timecode=cue.start,
                citation=rule.source, sarif_level=rule.sarif_level,
            ))

    if not results:
        results.append(RuleResult(
            rule_id=rule.id, status="pass",
            message=f"All captions within {NETFLIX_MAX_CHARS_PER_LINE} chars/line and {NETFLIX_MAX_LINES} lines.",
            citation=rule.source, sarif_level=rule.sarif_level,
        ))
    return results


def eval_nflx_dur_01(
    cues: list[CaptionCue],
    frame_rate: float = NETFLIX_FRAME_RATE,
) -> list[RuleResult]:
    """
    NFLX-DUR-01: Caption duration must be between 5/6 second and 7 seconds.
    Minimum gap between events: 2 frames.
    """
    rule = get_rule("NFLX-DUR-01")
    min_gap_s = NETFLIX_MIN_GAP_FRAMES / frame_rate
    results = []
    sorted_cues = sorted(cues, key=lambda c: c.start)

    for i, cue in enumerate(sorted_cues):
        issues = []
        if cue.duration < NETFLIX_MIN_DURATION_S:
            issues.append(
                f"duration {cue.duration:.3f}s below minimum {NETFLIX_MIN_DURATION_S:.3f}s"
            )
        if cue.duration > NETFLIX_MAX_DURATION_S:
            issues.append(
                f"duration {cue.duration:.1f}s exceeds maximum {NETFLIX_MAX_DURATION_S}s"
            )
        # Check gap to next cue
        if i < len(sorted_cues) - 1:
            gap = sorted_cues[i + 1].start - cue.end
            if 0 < gap < min_gap_s:
                issues.append(
                    f"gap to next event {gap:.3f}s below 2-frame minimum ({min_gap_s:.3f}s)"
                )

        if issues:
            results.append(RuleResult(
                rule_id=rule.id, status="fail",
                message=f"Caption at {cue.start:.2f}s: {'; '.join(issues)}",
                timecode=cue.start,
                citation=rule.source, sarif_level=rule.sarif_level,
            ))

    if not results:
        results.append(RuleResult(
            rule_id=rule.id, status="pass",
            message=f"All captions within {NETFLIX_MIN_DURATION_S:.3f}s–{NETFLIX_MAX_DURATION_S}s duration range.",
            citation=rule.source, sarif_level=rule.sarif_level,
        ))
    return results
