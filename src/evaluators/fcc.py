"""
FCC 47 CFR 79.1(j)(2) evaluators.
Four factors: accuracy, synchronicity, completeness, placement.

Source: 47 CFR 79.1(j)(2)(i)-(iv), verbatim from eCFR.
Citations are placeholders — replaced by RAG layer at runtime.
"""
from __future__ import annotations
from src.models import CaptionCue, RuleResult, SpeechRegion, NERScoreResult
from src.gap_engine import cue_overlaps_speech, ad_overlaps_speech
from src.registry import get_rule


def eval_fcc_acc_01(
    ner_result: NERScoreResult | None,
) -> RuleResult:
    """
    FCC-ACC-01: Caption accuracy using NER-style scorer.
    NEVER auto-fail on ASR evidence alone.
    Fail only if the entire confidence BAND is below 98%.
    """
    rule = get_rule("FCC-ACC-01")

    if ner_result is None:
        return RuleResult(
            rule_id=rule.id,
            status="skip",
            message="No reference transcript available — accuracy check skipped.",
            citation=rule.source,
            sarif_level=rule.sarif_level,
            human_review_required=True,
        )

    if ner_result.n_words == 0:
        return RuleResult(
            rule_id=rule.id,
            status="skip",
            message="Reference transcript is empty — accuracy check skipped.",
            citation=rule.source,
            sarif_level=rule.sarif_level,
        )

    score_pct = round(ner_result.ner_score * 100, 2)
    band_low_pct = round(ner_result.band_low * 100, 2)
    band_high_pct = round(ner_result.band_high * 100, 2)

    if ner_result.passes_98_threshold:
        return RuleResult(
            rule_id=rule.id,
            status="pass",
            message=f"NER score {score_pct}% (band {band_low_pct}%–{band_high_pct}%) meets the 98% threshold.",
            citation=rule.source,
            sarif_level=rule.sarif_level,
            confidence=ner_result.ner_score,
        )

    if ner_result.straddles_threshold:
        # Band straddles 98% — flag for human review, NEVER auto-fail
        return RuleResult(
            rule_id=rule.id,
            status="flag",
            message=(
                f"NER score {score_pct}% (band {band_low_pct}%–{band_high_pct}%) "
                f"straddles the 98% threshold. Human review required. "
                f"ASR carries measured demographic disparity (Koenecke et al., PNAS 2020) — "
                f"never auto-fail on ASR evidence alone."
            ),
            citation=rule.source,
            sarif_level=rule.sarif_level,
            confidence=ner_result.ner_score,
            human_review_required=True,
        )

    # Entire band below 98%
    return RuleResult(
        rule_id=rule.id,
        status="fail",
        message=(
            f"NER score {score_pct}% (band {band_low_pct}%–{band_high_pct}%) "
            f"is below the 98% threshold. "
            f"Note: {len(ner_result.low_confidence_regions)} low-confidence region(s) flagged for human review."
        ),
        citation=rule.source,
        sarif_level=rule.sarif_level,
        confidence=ner_result.ner_score,
        human_review_required=True,
    )


def eval_fcc_syn_01(
    cues: list[CaptionCue],
    speech_regions: list[SpeechRegion],
    tolerance_ms: int = 500,
) -> list[RuleResult]:
    """
    FCC-SYN-01: Each caption cue must overlap a speech region within tolerance.
    Returns one result per failing cue.
    """
    rule = get_rule("FCC-SYN-01")
    results = []

    for cue in cues:
        if not cue_overlaps_speech(cue, speech_regions, tolerance_ms):
            results.append(RuleResult(
                rule_id=rule.id,
                status="fail",
                message=(
                    f"Caption cue at {cue.start:.2f}s–{cue.end:.2f}s does not overlap "
                    f"any detected speech region within {tolerance_ms}ms tolerance. "
                    f"Text: {cue.text[:60]!r}"
                ),
                timecode=cue.start,
                citation=rule.source,
                sarif_level=rule.sarif_level,
            ))

    if not results:
        results.append(RuleResult(
            rule_id=rule.id,
            status="pass",
            message=f"All {len(cues)} caption cues overlap detected speech regions.",
            citation=rule.source,
            sarif_level=rule.sarif_level,
        ))
    return results


def eval_fcc_cmp_01(
    cues: list[CaptionCue],
    speech_regions: list[SpeechRegion],
    total_duration: float,
) -> RuleResult:
    """
    FCC-CMP-01: Captions must run from beginning to end of program.
    Fails if any speech region is not covered by any caption cue.
    """
    rule = get_rule("FCC-CMP-01")

    if not speech_regions:
        return RuleResult(
            rule_id=rule.id,
            status="skip",
            message="No speech regions detected — completeness check skipped.",
            citation=rule.source,
            sarif_level=rule.sarif_level,
        )

    uncovered = []
    for region in speech_regions:
        covered = any(
            cue.start <= region.end and cue.end >= region.start
            for cue in cues
        )
        if not covered:
            uncovered.append(region)

    if uncovered:
        first = uncovered[0]
        return RuleResult(
            rule_id=rule.id,
            status="fail",
            message=(
                f"{len(uncovered)} speech region(s) have no caption coverage. "
                f"First uncovered region: {first.start:.2f}s–{first.end:.2f}s."
            ),
            timecode=uncovered[0].start,
            citation=rule.source,
            sarif_level=rule.sarif_level,
        )

    return RuleResult(
        rule_id=rule.id,
        status="pass",
        message="All speech regions have caption coverage.",
        citation=rule.source,
        sarif_level=rule.sarif_level,
    )


def eval_fcc_plc_01(cues: list[CaptionCue]) -> list[RuleResult]:
    """
    FCC-PLC-01: Captions must not overlap each other or run off-frame.
    Checks for temporal overlap between consecutive cues.
    """
    rule = get_rule("FCC-PLC-01")
    results = []
    sorted_cues = sorted(cues, key=lambda c: c.start)

    for i in range(len(sorted_cues) - 1):
        a = sorted_cues[i]
        b = sorted_cues[i + 1]
        if a.end > b.start:
            results.append(RuleResult(
                rule_id=rule.id,
                status="fail",
                message=(
                    f"Caption cues overlap: [{a.start:.2f}s–{a.end:.2f}s] "
                    f"and [{b.start:.2f}s–{b.end:.2f}s]."
                ),
                timecode=b.start,
                citation=rule.source,
                sarif_level=rule.sarif_level,
            ))

    if not results:
        results.append(RuleResult(
            rule_id=rule.id,
            status="pass",
            message="No overlapping caption cues detected.",
            citation=rule.source,
            sarif_level=rule.sarif_level,
        ))
    return results
