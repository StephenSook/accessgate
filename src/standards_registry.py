"""
Canonical standard URLs for each conformance rule.

Every finding already carries a verbatim RAG-retrieved quote (RuleResult.citation);
this module adds the *canonical clause reference*: a short standard label plus a
live URL a reviewer can open to read the rule in the authoritative source. Every
URL here was verified to return HTTP 200 (2026-07-26). Keeping the map keyed by
rule-id family means a new rule inherits its citation automatically.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

_REPO_ROOT = Path(__file__).resolve().parent.parent

# Family -> canonical source URL (all verified live 2026-07-26).
_STANDARD_URLS = {
    "FCC": "https://www.ecfr.gov/current/title-47/chapter-I/subchapter-B/part-79/section-79.1",
    "WCAG_CAP": "https://www.w3.org/WAI/WCAG22/Understanding/captions-prerecorded.html",
    "WCAG_AD": "https://www.w3.org/WAI/WCAG22/Understanding/audio-description-prerecorded.html",
    "DCMP_CAP": "https://dcmp.org/learn/captioningkey",
    "DCMP_DESC": "https://dcmp.org/learn/descriptionkey",
    "NFLX": "https://partnerhelp.netflixstudios.com/hc/en-us/articles/217350977-English-Timed-Text-Style-Guide",
}

# Family -> short human clause label shown next to the link.
_CLAUSE_LABEL = {
    "FCC": "FCC 47 CFR 79.1(j)(2)",
    "WCAG_CAP": "WCAG 2.2 SC 1.2.2",
    "WCAG_AD": "WCAG 2.2 SC 1.2.5",
    "DCMP_CAP": "DCMP Captioning Key",
    "DCMP_DESC": "DCMP Description Key",
    "NFLX": "Netflix English TTSG",
}


def _family(rule_id: str) -> Optional[str]:
    if rule_id.startswith("FCC"):
        return "FCC"
    if rule_id.startswith("WCAG-122"):
        return "WCAG_CAP"
    if rule_id.startswith("WCAG-125"):
        return "WCAG_AD"
    if rule_id.startswith("DCMP-CAP"):
        return "DCMP_CAP"
    if rule_id.startswith("DCMP-DESC"):
        return "DCMP_DESC"
    if rule_id.startswith("NFLX"):
        return "NFLX"
    return None



def clause_ref(rule_id: str) -> Optional[dict]:
    """Return {clause_id, clause_url} for a rule id, or None if unknown."""
    fam = _family(rule_id)
    if fam is None:
        return None
    return {"clause_id": _CLAUSE_LABEL[fam], "clause_url": _STANDARD_URLS[fam]}


def delta_pct(measured, limit):
    """Signed percent the observed value is over (+) or under (-) the limit.

    Single source of truth: RuleResult.delta_pct (live reports) and
    enrich_report_dict (served raw demo/cache dicts) both call this, so a demo
    number can never drift from a live-report number. None unless measured is
    present and limit is a non-zero number.
    """
    if measured is None or limit in (None, 0):
        return None
    return round((measured - limit) / limit * 100, 1)


def ruleset_stamp() -> dict:
    """Identify the ruleset that produced a report, computed from its content.

    WHY THIS EXISTS. A report a reader saves today is only meaningful if they can
    tell which rules produced it. Without a stamp, changing a threshold silently
    makes every previously exported report unreproducible, and nothing anywhere
    says so.

    The best-engineered rival in this field ships `formulaVersion` inside its
    response payload, which is exactly why its published scores could be
    independently recomputed and matched to the digit. This is the same idea for
    a rule engine.

    DERIVED, NOT DECLARED. The digest is a hash of the registry file itself, so
    it cannot drift from the rules the way a hand-maintained version string can.
    Edit a threshold and the digest changes without anyone remembering to bump it.

    Deliberately NOT a reproducibility claim. It says "these rules produced this
    report", which is checkable by hashing the file. It does not claim the whole
    run reproduces bit-for-bit, because the generative layer is not deterministic
    and asserting otherwise would be the kind of unverifiable claim this project
    grades rivals down for.
    """
    import hashlib

    registry = _REPO_ROOT / "rules" / "rules_registry.yaml"
    try:
        raw = registry.read_bytes()
    except OSError:
        return {"digest": None, "note": "rules registry not readable"}

    return {
        "digest": "sha256:" + hashlib.sha256(raw).hexdigest()[:16],
        "source": "rules/rules_registry.yaml",
        "note": "Identifies the ruleset that produced this report. Recompute with: "
                "shasum -a 256 rules/rules_registry.yaml. This is a ruleset "
                "identity, not a claim that the whole run reproduces bit-for-bit.",
    }


def enrich_report_dict(report: dict) -> dict:
    """Add clause_id/clause_url (and delta_pct) to each result in a serialized
    report dict.

    Used for served artifacts (the committed demo report, cached reports) that
    were produced before these fields existed, or that carry measured/limit but
    not the computed delta. Mutates and returns the dict; never overwrites a
    value already present.
    """
    # Which ruleset produced this. Set here rather than at each call site so
    # /demo, /report/{id} and a live /check cannot disagree about it.
    report.setdefault("ruleset", ruleset_stamp())

    for r in report.get("results", []):
        ref = clause_ref(r.get("rule_id", ""))
        if ref:
            r.setdefault("clause_id", ref["clause_id"])
            r.setdefault("clause_url", ref["clause_url"])
        if r.get("delta_pct") is None:
            d = delta_pct(r.get("measured"), r.get("limit"))
            if d is not None:
                r["delta_pct"] = d
    return report
