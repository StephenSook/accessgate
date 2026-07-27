"""
Tests for the judge-facing evidence layer:
  - clause citations (canonical standard label + URL per rule)   [Steal B]
  - computed-number evidence (measured vs limit + delta_pct)      [Steal A]
"""
from __future__ import annotations

from src.models import CaptionCue, RuleResult
from src.standards_registry import clause_ref, enrich_report_dict, _STANDARD_URLS
from src.evaluators.netflix import eval_nflx_cps_01, eval_nflx_len_01, eval_nflx_dur_01
from src.evaluators.dcmp_caption import eval_dcmp_cap_01, eval_dcmp_cap_03, eval_dcmp_cap_04
from src.exporters.editor import export_findings_csv
from src.models import ConformanceReport


# ---- Steal B: clause citations ------------------------------------------------

def test_clause_ref_covers_every_family():
    cases = {
        "FCC-ACC-01": "ecfr.gov",
        "WCAG-122-01": "captions-prerecorded",
        "WCAG-125-01": "audio-description-prerecorded",
        "DCMP-CAP-03": "captioningkey",
        "DCMP-DESC-04": "descriptionkey",
        "NFLX-CPS-01": "netflixstudios",
    }
    for rule_id, needle in cases.items():
        ref = clause_ref(rule_id)
        assert ref is not None, rule_id
        assert ref["clause_id"]
        assert needle in ref["clause_url"], (rule_id, ref["clause_url"])


def test_clause_ref_unknown_rule_is_none():
    assert clause_ref("BOGUS-99") is None


def test_all_standard_urls_are_https():
    assert all(u.startswith("https://") for u in _STANDARD_URLS.values())


def test_enrich_report_dict_adds_clause_and_delta_without_overwriting():
    report = {"results": [
        {"rule_id": "NFLX-CPS-01", "measured": 25.0, "limit": 20.0},
        {"rule_id": "WCAG-122-01"},
        {"rule_id": "NFLX-CPS-01", "clause_id": "keep-me", "clause_url": "http://x", "delta_pct": 99.0},
    ]}
    enrich_report_dict(report)
    r0, r1, r2 = report["results"]
    assert r0["clause_id"] == "Netflix English TTSG"
    assert r0["delta_pct"] == 25.0            # (25-20)/20*100
    assert r1["clause_url"].endswith("captions-prerecorded.html")
    assert r2["clause_id"] == "keep-me"        # not overwritten
    assert r2["delta_pct"] == 99.0             # not overwritten


# ---- Steal A: computed-number evidence ---------------------------------------

def _cue(idx, start, end, text):
    return CaptionCue(index=idx, start=start, end=end, text=text, lines=text.split("\n"))


def test_delta_pct_computed_over_and_under():
    over = RuleResult(rule_id="NFLX-CPS-01", status="fail", message="", measured=25.0, limit=20.0, unit="cps")
    assert over.delta_pct == 25.0
    under = RuleResult(rule_id="NFLX-DUR-01", status="fail", message="", measured=0.5, limit=1.0, unit="s")
    assert under.delta_pct == -50.0
    none = RuleResult(rule_id="WCAG-122-01", status="fail", message="")
    assert none.delta_pct is None


def test_cps_evaluator_sets_measured_limit():
    # ~53 cps: 53 chars in ~1s
    cue = _cue(1, 0.0, 1.0, "x" * 53)
    fails = [r for r in eval_nflx_cps_01([cue], profile="adult") if r.status == "fail"]
    assert fails and fails[0].measured is not None
    assert fails[0].limit == 20.0 and fails[0].unit == "cps"
    assert fails[0].delta_pct is not None and fails[0].delta_pct > 0


def test_len_evaluator_reports_char_breach():
    cue = _cue(1, 0.0, 3.0, "x" * 50)
    fails = [r for r in eval_nflx_len_01([cue]) if r.status == "fail"]
    assert fails and fails[0].measured == 50.0 and fails[0].limit == 42.0 and fails[0].unit == "chars"


def test_dur_below_minimum_is_negative_delta():
    cue = _cue(1, 0.0, 0.5, "hi")
    fails = [r for r in eval_nflx_dur_01([cue]) if r.status == "fail"]
    assert fails and fails[0].unit == "s"
    assert fails[0].delta_pct is not None and fails[0].delta_pct < 0


def test_dcmp_caption_numeric_rules_carry_measured():
    long_line = _cue(1, 0.0, 3.0, "y" * 40)          # > 32 DCMP line limit
    fast = _cue(2, 10.0, 10.5, "one two three four five six")  # very high wpm
    short = _cue(3, 20.0, 21.0, "brief")             # < 2s
    assert eval_dcmp_cap_01([long_line])[0].measured == 40.0
    assert eval_dcmp_cap_03([fast], profile="adult")[0].measured is not None
    d = eval_dcmp_cap_04([short])[0]
    assert d.measured == 1.0 and d.limit == 2.0 and d.unit == "s"


def test_csv_export_has_clause_and_measured_columns():
    r = RuleResult(rule_id="NFLX-CPS-01", status="fail", message="too fast",
                   timecode=1.0, measured=25.0, limit=20.0, unit="cps",
                   clause_url="https://partnerhelp.netflixstudios.com/x")
    report = ConformanceReport(film_path="f", caption_path="c", results=[r])
    csv_text = export_findings_csv(report)
    header = csv_text.splitlines()[0]
    for col in ("clause_url", "measured", "limit", "unit", "delta_pct"):
        assert col in header
    assert "25.0" in csv_text and "netflixstudios" in csv_text
