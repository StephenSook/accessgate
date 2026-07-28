"""
DCMP Captioning Key evaluators (DCMP-CAP-01 through DCMP-CAP-06).
Source: dcmp.org Captioning Key, confirmed July 2026.
Citations are placeholders — replaced by RAG layer at runtime.
"""
from __future__ import annotations
import re
from src.models import CaptionCue, RuleResult
from src.registry import get_rule

# DCMP line character limit
DCMP_MAX_CHARS_PER_LINE = 32
DCMP_MAX_LINES = 2
DCMP_MIN_DISPLAY_S = 2.0
DCMP_MAX_WPM = 225.0


def eval_dcmp_cap_01(cues: list[CaptionCue]) -> list[RuleResult]:
    """DCMP-CAP-01: No line exceeds 32 characters."""
    rule = get_rule("DCMP-CAP-01")
    results = []
    for cue in cues:
        for line in cue.lines:
            if len(line) > DCMP_MAX_CHARS_PER_LINE:
                results.append(RuleResult(
                    rule_id=rule.id, status="fail",
                    message=f"Line exceeds {DCMP_MAX_CHARS_PER_LINE} chars ({len(line)} chars) at {cue.start:.2f}s: {line!r}",
                    timecode=cue.start,
                    measured=float(len(line)), limit=float(DCMP_MAX_CHARS_PER_LINE), unit="chars",
                    citation=rule.source, sarif_level=rule.sarif_level,
                ))
    if not results:
        results.append(RuleResult(
            rule_id=rule.id, status="pass",
            message=f"All caption lines are within the {DCMP_MAX_CHARS_PER_LINE}-character limit.",
            citation=rule.source, sarif_level=rule.sarif_level,
        ))
    return results


def eval_dcmp_cap_02(cues: list[CaptionCue]) -> list[RuleResult]:
    """DCMP-CAP-02: No more than 2 lines per caption."""
    rule = get_rule("DCMP-CAP-02")
    results = []
    for cue in cues:
        if len(cue.lines) > DCMP_MAX_LINES:
            results.append(RuleResult(
                rule_id=rule.id, status="fail",
                message=f"Caption at {cue.start:.2f}s has {len(cue.lines)} lines (max {DCMP_MAX_LINES}).",
                timecode=cue.start,
                measured=float(len(cue.lines)), limit=float(DCMP_MAX_LINES), unit="lines",
                citation=rule.source, sarif_level=rule.sarif_level,
            ))
    if not results:
        results.append(RuleResult(
            rule_id=rule.id, status="pass",
            message="All captions have 2 or fewer lines.",
            citation=rule.source, sarif_level=rule.sarif_level,
        ))
    return results


#: DCMP reading-speed tiers. The educational tiers are real limits from the
#: Captioning Key, but nothing in this project ships content graded to them, so
#: only "adult" is ever selected in practice. They are mapped rather than
#: documented-and-ignored: the previous version took a `profile` argument,
#: promised the tiers in its docstring, and then unconditionally used 225, which
#: is a claim the code did not honour.
DCMP_WPM_TIERS = {
    "lower": 130.0,
    "middle": 140.0,
    "upper": 160.0,
    "adult": DCMP_MAX_WPM,
}


def eval_dcmp_cap_03(cues: list[CaptionCue], profile: str = "adult") -> list[RuleResult]:
    """
    DCMP-CAP-03: Reading speed within the tier limit for the content profile.

    Tiers: lower-level educational 130 wpm, middle 140, upper 160, adult
    near-verbatim 225. An unrecognised profile falls back to the adult cap
    rather than silently passing everything.
    """
    rule = get_rule("DCMP-CAP-03")
    wpm_cap = DCMP_WPM_TIERS.get(profile, DCMP_MAX_WPM)
    results = []
    for cue in cues:
        if cue.duration <= 0:
            continue
        wpm = cue.wpm
        if wpm > wpm_cap:
            results.append(RuleResult(
                rule_id=rule.id, status="fail",
                message=f"Caption at {cue.start:.2f}s exceeds {wpm_cap:.0f} wpm ({wpm:.0f} wpm). Text: {cue.text[:50]!r}",
                timecode=cue.start,
                measured=round(wpm, 1), limit=wpm_cap, unit="wpm",
                citation=rule.source, sarif_level=rule.sarif_level,
            ))
    if not results:
        results.append(RuleResult(
            rule_id=rule.id, status="pass",
            message=f"All captions within {wpm_cap:.0f} wpm reading speed limit.",
            citation=rule.source, sarif_level=rule.sarif_level,
        ))
    return results


def eval_dcmp_cap_04(cues: list[CaptionCue]) -> list[RuleResult]:
    """DCMP-CAP-04: No caption displayed for less than 2 seconds."""
    rule = get_rule("DCMP-CAP-04")
    results = []
    for cue in cues:
        if cue.duration < DCMP_MIN_DISPLAY_S:
            results.append(RuleResult(
                rule_id=rule.id, status="fail",
                message=f"Caption at {cue.start:.2f}s displayed for {cue.duration:.2f}s (minimum {DCMP_MIN_DISPLAY_S}s). Text: {cue.text[:50]!r}",
                timecode=cue.start,
                measured=round(cue.duration, 2), limit=DCMP_MIN_DISPLAY_S, unit="s",
                citation=rule.source, sarif_level=rule.sarif_level,
            ))
    if not results:
        results.append(RuleResult(
            rule_id=rule.id, status="pass",
            message=f"All captions meet the {DCMP_MIN_DISPLAY_S}s minimum display duration.",
            citation=rule.source, sarif_level=rule.sarif_level,
        ))
    return results


# Regex pattern for bracketed sound-effect sources: [SOUND] or [Sound Source]
_BRACKETED_SOURCE_RE = re.compile(r"\[.+?\]")


def eval_dcmp_cap_05(cues: list[CaptionCue]) -> list[RuleResult]:
    """
    DCMP-CAP-05: Sound effect captions must include a bracketed source.
    Flags any caption that looks like a sound description but lacks brackets.
    """
    rule = get_rule("DCMP-CAP-05")
    results = []
    # Sound keywords that indicate a non-speech caption
    sound_keywords = re.compile(
        r"\b(sound|noise|music|bang|crash|beep|alarm|ring|click|thud|screech|whistle)\b",
        re.IGNORECASE
    )
    for cue in cues:
        if sound_keywords.search(cue.text):
            if not _BRACKETED_SOURCE_RE.search(cue.text):
                results.append(RuleResult(
                    rule_id=rule.id, status="flag",
                    message=f"Sound-effect caption at {cue.start:.2f}s may lack a bracketed source. Text: {cue.text[:60]!r}",
                    timecode=cue.start,
                    citation=rule.source, sarif_level=rule.sarif_level,
                    human_review_required=True,
                ))
    if not results:
        results.append(RuleResult(
            rule_id=rule.id, status="pass",
            message="No unbracketed sound-effect captions detected.",
            citation=rule.source, sarif_level=rule.sarif_level,
        ))
    return results


_PAST_TENSE_SOUND_RE = re.compile(
    r"\[(.*?)(banged|crashed|rang|beeped|clicked|thudded|screeched|whistled|sounded)(.*?)\]",
    re.IGNORECASE
)


def eval_dcmp_cap_06(cues: list[CaptionCue]) -> list[RuleResult]:
    """
    DCMP-CAP-06: Never use past tense for sound descriptions.
    Sound captions are synchronized with the sound → present tense.
    """
    rule = get_rule("DCMP-CAP-06")
    results = []
    for cue in cues:
        if _PAST_TENSE_SOUND_RE.search(cue.text):
            results.append(RuleResult(
                rule_id=rule.id, status="flag",
                message=f"Sound caption at {cue.start:.2f}s may use past tense. Text: {cue.text[:60]!r}",
                timecode=cue.start,
                citation=rule.source, sarif_level=rule.sarif_level,
                human_review_required=True,
            ))
    if not results:
        results.append(RuleResult(
            rule_id=rule.id, status="pass",
            message="No past-tense sound captions detected.",
            citation=rule.source, sarif_level=rule.sarif_level,
        ))
    return results
