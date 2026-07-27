"""
Canonical standard URLs for each conformance rule.

Every finding already carries a verbatim RAG-retrieved quote (RuleResult.citation);
this module adds the *canonical clause reference*: a short standard label plus a
live URL a reviewer can open to read the rule in the authoritative source. Every
URL here was verified to return HTTP 200 (2026-07-26). Keeping the map keyed by
rule-id family means a new rule inherits its citation automatically.
"""
from __future__ import annotations
from typing import Optional

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


def _delta_pct(measured, limit):
    """Signed percent over(+)/under(-) the limit. Mirrors RuleResult.delta_pct
    so served raw dicts (demo, cache) get the same number a live report would."""
    if measured is None or limit in (None, 0):
        return None
    return round((measured - limit) / limit * 100, 1)


def enrich_report_dict(report: dict) -> dict:
    """Add clause_id/clause_url (and delta_pct) to each result in a serialized
    report dict.

    Used for served artifacts (the committed demo report, cached reports) that
    were produced before these fields existed, or that carry measured/limit but
    not the computed delta. Mutates and returns the dict; never overwrites a
    value already present.
    """
    for r in report.get("results", []):
        ref = clause_ref(r.get("rule_id", ""))
        if ref:
            r.setdefault("clause_id", ref["clause_id"])
            r.setdefault("clause_url", ref["clause_url"])
        if r.get("delta_pct") is None:
            d = _delta_pct(r.get("measured"), r.get("limit"))
            if d is not None:
                r["delta_pct"] = d
    return report
