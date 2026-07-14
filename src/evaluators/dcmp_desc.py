"""
DCMP Description Key evaluators (DCMP-DESC-01 through DCMP-DESC-07).
Source: dcmp.org Description Key (learn/617 and learn/618), confirmed July 2026.
Citations are placeholders — replaced by RAG layer at runtime.

Load-Bearing Artifact #3: The AD structure validator.
All checks are self-built NLP heuristics — no hosted AI in the critical path.
"""
from __future__ import annotations
import re
from src.models import CaptionCue, GapRegion, SpeechRegion, RuleResult
from src.gap_engine import ad_overlaps_speech
from src.registry import get_rule

# AD reading speed for gap-fit check (words per minute)
AD_READING_WPM = 150.0

# First/second person pronouns (DCMP-DESC-02)
_FIRST_SECOND_PERSON_RE = re.compile(
    r"\b(I|me|my|mine|myself|we|us|our|ours|ourselves|you|your|yours|yourself|yourselves)\b",
    re.IGNORECASE,
)

# Passive voice patterns (DCMP-DESC-01) — simplified heuristic
# "was/were/is/are/has been + past participle"
_PASSIVE_VOICE_RE = re.compile(
    r"\b(was|were|is|are|has been|have been|had been|being)\s+\w+ed\b",
    re.IGNORECASE,
)

# Past tense detection (simple heuristic — verb endings)
_PAST_TENSE_RE = re.compile(
    r"\b(was|were|had|did|went|came|saw|ran|told|said|looked|walked|turned|moved|stood|fell|rose|sat)\b",
    re.IGNORECASE,
)

# Sentence fragment: no verb detected (very simplified)
_HAS_VERB_RE = re.compile(
    r"\b(is|are|was|were|has|have|had|do|does|did|will|would|can|could|shall|should|may|might|must|"
    r"run|runs|ran|go|goes|went|come|comes|came|see|sees|saw|look|looks|looked|"
    r"walk|walks|walked|turn|turns|turned|move|moves|moved|stand|stands|stood|"
    r"fall|falls|fell|rise|rises|rose|sit|sits|sat|say|says|said|tell|tells|told|"
    r"reach|reaches|reached|open|opens|opened|close|closes|closed|hold|holds|held)\b",
    re.IGNORECASE,
)

# Cinematic / premature jargon terms (DCMP-DESC-03)
# Per DCMP: "avoid jargon / no premature technical terms"
# We flag terms that appear before they've been introduced in the program
_JARGON_TERMS = {
    "flashback", "flash-back", "flash back",
    "dream sequence", "dream-sequence",
    "dissolve", "cross-cut", "cutaway", "cut to",
    "montage", "voiceover", "voice-over", "v.o.",
    "close-up", "closeup", "close up",
    "wide shot", "long shot", "medium shot",
    "slow motion", "slow-motion",
    "superimposed", "title card",
}


def eval_dcmp_desc_01(ad_cues: list[CaptionCue]) -> list[RuleResult]:
    """DCMP-DESC-01: AD lines must be present tense, active voice."""
    rule = get_rule("DCMP-DESC-01")
    results = []
    for cue in ad_cues:
        issues = []
        if _PASSIVE_VOICE_RE.search(cue.text):
            issues.append("passive voice")
        if _PAST_TENSE_RE.search(cue.text) and not _has_active_present(cue.text):
            issues.append("past tense")
        if issues:
            results.append(RuleResult(
                rule_id=rule.id, status="flag",
                message=f"AD at {cue.start:.2f}s may use {' and '.join(issues)}. Text: {cue.text[:60]!r}",
                timecode=cue.start,
                citation=rule.source, sarif_level=rule.sarif_level,
                human_review_required=True,
            ))
    if not results:
        results.append(RuleResult(
            rule_id=rule.id, status="pass",
            message="No past-tense or passive-voice AD lines detected.",
            citation=rule.source, sarif_level=rule.sarif_level,
        ))
    return results


def _has_active_present(text: str) -> bool:
    """Returns True if the text clearly contains an active present-tense construction."""
    present_re = re.compile(
        r"\b(is|are|has|have|do|does|runs|goes|comes|sees|looks|walks|turns|moves|stands|falls|rises|sits)\b",
        re.IGNORECASE,
    )
    return bool(present_re.search(text))


def eval_dcmp_desc_02(ad_cues: list[CaptionCue]) -> list[RuleResult]:
    """DCMP-DESC-02: AD must use third-person narrative — no first/second person."""
    rule = get_rule("DCMP-DESC-02")
    results = []
    for cue in ad_cues:
        match = _FIRST_SECOND_PERSON_RE.search(cue.text)
        if match:
            results.append(RuleResult(
                rule_id=rule.id, status="flag",
                message=f"AD at {cue.start:.2f}s uses first/second person ({match.group()!r}). Text: {cue.text[:60]!r}",
                timecode=cue.start,
                citation=rule.source, sarif_level=rule.sarif_level,
                human_review_required=True,
            ))
    if not results:
        results.append(RuleResult(
            rule_id=rule.id, status="pass",
            message="No first/second person pronouns found in AD.",
            citation=rule.source, sarif_level=rule.sarif_level,
        ))
    return results


def eval_dcmp_desc_03(ad_cues: list[CaptionCue]) -> list[RuleResult]:
    """
    DCMP-DESC-03: Avoid premature jargon / cinematic terms.
    Flags technical terms used before the program has introduced them.
    Per DCMP: "Match vocabulary to the program; wait until technical vocabulary
    has been introduced before using it."
    """
    rule = get_rule("DCMP-DESC-03")
    results = []
    for cue in ad_cues:
        lower_text = cue.text.lower()
        found_terms = [t for t in _JARGON_TERMS if t in lower_text]
        if found_terms:
            results.append(RuleResult(
                rule_id=rule.id, status="flag",
                message=f"AD at {cue.start:.2f}s uses potential jargon terms: {found_terms}. Text: {cue.text[:60]!r}",
                timecode=cue.start,
                citation=rule.source, sarif_level=rule.sarif_level,
                human_review_required=True,
            ))
    if not results:
        results.append(RuleResult(
            rule_id=rule.id, status="pass",
            message="No premature jargon or cinematic terms detected in AD.",
            citation=rule.source, sarif_level=rule.sarif_level,
        ))
    return results


def eval_dcmp_desc_04(
    ad_cues: list[CaptionCue],
    gaps: list[GapRegion],
    reading_wpm: float = AD_READING_WPM,
) -> list[RuleResult]:
    """
    DCMP-DESC-04: Description word count must fit within its dialogue-free gap.
    Fails if a description's word count exceeds the gap-fit WPM for its gap.
    """
    rule = get_rule("DCMP-DESC-04")
    results = []

    # If VAD did not run there are no gaps to fit descriptions into. Skip
    # honestly rather than emitting a pass ("all descriptions fit") that was
    # never actually evaluated.
    if ad_cues and not gaps:
        return [RuleResult(
            rule_id=rule.id,
            status="skip",
            message="Gap detection unavailable (VAD did not run); description-to-gap fit not evaluated.",
            citation=rule.source,
            sarif_level=rule.sarif_level,
        )]

    for cue in ad_cues:
        # Find the gap that FULLY contains this AD cue. A cue that only partly
        # overlaps a gap extends into speech and is caught by DCMP-DESC-05; it
        # must not borrow the whole gap's word budget (which let over-long,
        # mostly-outside descriptions pass).
        containing_gap = None
        for gap in gaps:
            if gap.start <= cue.start and gap.end >= cue.end:
                containing_gap = gap
                break

        if containing_gap is None:
            continue  # DCMP-DESC-05 handles overlap-with-speech

        max_words = containing_gap.max_words(wpm=reading_wpm)
        actual_words = cue.word_count

        if actual_words > max_words:
            results.append(RuleResult(
                rule_id=rule.id, status="fail",
                message=(
                    f"AD at {cue.start:.2f}s has {actual_words} words but gap "
                    f"({containing_gap.duration:.2f}s) fits only {max_words} words "
                    f"at {reading_wpm:.0f} wpm."
                ),
                timecode=cue.start,
                citation=rule.source, sarif_level=rule.sarif_level,
            ))

    if not results:
        results.append(RuleResult(
            rule_id=rule.id, status="pass",
            message="All AD descriptions fit within their dialogue-free gaps.",
            citation=rule.source, sarif_level=rule.sarif_level,
        ))
    return results


def eval_dcmp_desc_05(
    ad_cues: list[CaptionCue],
    speech_regions: list[SpeechRegion],
) -> list[RuleResult]:
    """
    DCMP-DESC-05: AD must not overlap detected speech regions.
    SARIF level: error (most severe AD violation).
    """
    rule = get_rule("DCMP-DESC-05")
    results = []

    # If VAD did not run there are no speech regions to check overlap against.
    # Skip honestly rather than emitting a pass ("no AD overlaps speech") for the
    # most severe AD rule when the analysis never ran.
    if ad_cues and not speech_regions:
        return [RuleResult(
            rule_id=rule.id,
            status="skip",
            message="Speech detection unavailable (VAD did not run); AD-vs-speech overlap not evaluated.",
            citation=rule.source,
            sarif_level=rule.sarif_level,
        )]

    for cue in ad_cues:
        if ad_overlaps_speech(cue.start, cue.end, speech_regions):
            results.append(RuleResult(
                rule_id=rule.id, status="fail",
                message=(
                    f"AD at {cue.start:.2f}s–{cue.end:.2f}s overlaps a detected "
                    f"speech region. Text: {cue.text[:60]!r}"
                ),
                timecode=cue.start,
                citation=rule.source, sarif_level=rule.sarif_level,
            ))

    if not results:
        results.append(RuleResult(
            rule_id=rule.id, status="pass",
            message="No AD cues overlap detected speech regions.",
            citation=rule.source, sarif_level=rule.sarif_level,
        ))
    return results


def eval_dcmp_desc_06(ad_cues: list[CaptionCue]) -> list[RuleResult]:
    """
    DCMP-DESC-06: Descriptions should be complete sentences.
    Flags sentence fragments (no detected verb) outside tight-timing cases.
    Tight-timing exception: gap < 1.5s.
    """
    rule = get_rule("DCMP-DESC-06")
    results = []
    for cue in ad_cues:
        # Skip very short cues (tight-timing exception)
        if cue.duration < 1.5:
            continue
        # Check for sentence fragment (no verb)
        if not _HAS_VERB_RE.search(cue.text):
            results.append(RuleResult(
                rule_id=rule.id, status="flag",
                message=f"AD at {cue.start:.2f}s may be a sentence fragment (no verb detected). Text: {cue.text[:60]!r}",
                timecode=cue.start,
                citation=rule.source, sarif_level=rule.sarif_level,
                human_review_required=True,
            ))
    if not results:
        results.append(RuleResult(
            rule_id=rule.id, status="pass",
            message="No sentence fragments detected in AD.",
            citation=rule.source, sarif_level=rule.sarif_level,
        ))
    return results


def eval_dcmp_desc_07(ad_cues: list[CaptionCue]) -> list[RuleResult]:
    """
    DCMP-DESC-07: Objectivity — human-judgment flag.
    Flags AD lines that may contain subjective or interpretive language.
    This cannot be machine-verified; always human-review required.
    """
    rule = get_rule("DCMP-DESC-07")
    subjectivity_indicators = re.compile(
        r"\b(beautiful|ugly|terrifying|amazing|wonderful|horrible|scary|lovely|"
        r"seems|appears|looks like|as if|clearly|obviously|apparently|probably|"
        r"perhaps|maybe|might be|could be|seems to be)\b",
        re.IGNORECASE,
    )
    results = []
    for cue in ad_cues:
        if subjectivity_indicators.search(cue.text):
            results.append(RuleResult(
                rule_id=rule.id, status="flag",
                message=f"AD at {cue.start:.2f}s may contain subjective/interpretive language. Text: {cue.text[:60]!r}",
                timecode=cue.start,
                citation=rule.source, sarif_level=rule.sarif_level,
                human_review_required=True,
            ))
    if not results:
        results.append(RuleResult(
            rule_id=rule.id, status="pass",
            message="No obvious subjectivity indicators found in AD (human review still recommended).",
            citation=rule.source, sarif_level=rule.sarif_level,
        ))
    return results
