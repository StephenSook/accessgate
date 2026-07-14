"""
WCAG 2.2 SC 1.2.2 and SC 1.2.5 evaluators.
Captions (Prerecorded) Level A and Audio Description (Prerecorded) Level AA.

Citations are placeholders — replaced by RAG layer at runtime.
"""
from __future__ import annotations
from src.models import CaptionCue, RuleResult
from src.registry import get_rule


def eval_wcag_122_01(cues: list[CaptionCue]) -> RuleResult:
    """WCAG-122-01: Fail if captions are absent."""
    rule = get_rule("WCAG-122-01")
    if not cues:
        return RuleResult(
            rule_id=rule.id, status="fail",
            message="No caption cues found. Captions are required for all prerecorded audio content (WCAG 2.2 SC 1.2.2, Level A).",
            citation=rule.source, sarif_level=rule.sarif_level,
        )
    return RuleResult(
        rule_id=rule.id, status="pass",
        message=f"Caption track present with {len(cues)} cues.",
        citation=rule.source, sarif_level=rule.sarif_level,
    )


def eval_wcag_125_01(ad_cues: list[CaptionCue] | None) -> RuleResult:
    """WCAG-125-01: Fail if audio description track is absent."""
    rule = get_rule("WCAG-125-01")
    if not ad_cues:
        return RuleResult(
            rule_id=rule.id, status="fail",
            message="No audio description track found. Audio description is required for all prerecorded video content (WCAG 2.2 SC 1.2.5, Level AA).",
            citation=rule.source, sarif_level=rule.sarif_level,
        )
    return RuleResult(
        rule_id=rule.id, status="pass",
        message=f"Audio description track present with {len(ad_cues)} cues.",
        citation=rule.source, sarif_level=rule.sarif_level,
    )


def eval_wcag_125_02(ad_cues: list[CaptionCue] | None) -> RuleResult:
    """
    WCAG-125-02: Human-judgment flag for AD semantic sufficiency.
    SC 1.2.5 requires AD to convey important visual information.
    Presence and timing are automatable; semantic sufficiency is not.
    """
    rule = get_rule("WCAG-125-02")
    if not ad_cues:
        return RuleResult(
            rule_id=rule.id, status="skip",
            message="No audio description track to evaluate for sufficiency.",
            citation=rule.source, sarif_level=rule.sarif_level,
        )
    return RuleResult(
        rule_id=rule.id, status="flag",
        message=(
            f"Audio description semantic sufficiency requires human review. "
            f"Automatable checks (presence, timing, structure) are covered by other rules. "
            f"SC 1.2.5 sufficiency — whether descriptions convey important visual information — "
            f"cannot be machine-verified per W3C ACT guidance."
        ),
        citation=rule.source, sarif_level=rule.sarif_level,
        human_review_required=True,
    )
