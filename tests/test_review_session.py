"""
Tests for the event-sourced conformance review session (src/review_session.py)
and its API, including an END-TO-END flow via the FastAPI TestClient:
create -> NL op -> typed op -> grounded rejection -> undo -> replay -> audit.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from src.models import ConformanceReport, RuleResult, GapRegion
from src.review_session import (
    ReviewSession, ReviewOp, ReviewQuery, GroundingError,
    compile_nl_deterministic, _parse_time, finding_key,
)
from src.app import app


def _report() -> ConformanceReport:
    return ConformanceReport(
        film_path="f.mp4", caption_path="c.srt",
        results=[
            RuleResult(rule_id="NFLX-CPS-01", status="flag", message="fast reading speed",
                       timecode=130.0, sarif_level="warning"),
            RuleResult(rule_id="DCMP-CAP-01", status="fail", message="line over 32 chars",
                       timecode=44.0, sarif_level="error"),
            RuleResult(rule_id="DCMP-CAP-03", status="flag", message="reading speed high",
                       timecode=200.0, sarif_level="warning"),
            RuleResult(rule_id="WCAG-1-2-2", status="pass", message="ok", timecode=1.0),
        ],
        gaps=[GapRegion(start=67.2, end=73.8)],
    )


# --------------------------------------------------------------------------- #
# Engine: state, ops, grounding
# --------------------------------------------------------------------------- #
class TestSessionState:
    def test_only_reviewable_findings_and_initial_status(self):
        s = ReviewSession(_report())
        assert set(s.state.findings) == {"f0", "f1", "f2"}  # pass (f3) excluded
        assert s.state.findings["f0"].review_status == "flagged"  # flag -> flagged
        assert s.state.findings["f1"].review_status == "open"     # fail -> open

    def test_accept_and_dismiss_with_reason(self):
        s = ReviewSession(_report())
        s.apply(ReviewOp(kind="accept_finding", target="f1"))
        assert s.state.findings["f1"].review_status == "accepted"
        s.apply(ReviewOp(kind="dismiss_finding", target="f0",
                         payload={"reason": "acceptable for this title"}))
        assert s.state.findings["f0"].review_status == "dismissed"
        assert s.state.findings["f0"].reason == "acceptable for this title"
        assert s.state.version == 2

    def test_grounding_rejects_unknown_finding(self):
        s = ReviewSession(_report())
        try:
            s.apply(ReviewOp(kind="accept_finding", target="f99"))
            assert False, "expected GroundingError"
        except GroundingError:
            pass

    def test_fix_ops_grounded_to_real_gaps(self):
        s = ReviewSession(_report())
        gk = ReviewSession.gap_key(67.2)
        s.apply(ReviewOp(kind="accept_fix", target=gk))
        assert s.state.fixes[gk] == "accepted"
        try:
            s.apply(ReviewOp(kind="reject_fix", target="g999.9"))
            assert False, "expected GroundingError on fake gap"
        except GroundingError:
            pass


class TestInverseUndoReplay:
    def test_undo_restores_prior_state_and_is_logged(self):
        s = ReviewSession(_report())
        s.apply(ReviewOp(kind="accept_finding", target="f1"))
        assert s.state.findings["f1"].review_status == "accepted"
        s.undo()
        assert s.state.findings["f1"].review_status == "open"  # restored
        # undo is itself appended (append-only, auditable)
        assert s.state.log[-1].source == "undo"
        assert s.state.log[-1].kind == "restore"

    def test_replay_is_deterministic(self):
        s = ReviewSession(_report())
        s.apply(ReviewOp(kind="dismiss_finding", target="f0", payload={"reason": "x"}))
        s.apply(ReviewOp(kind="accept_finding", target="f1"))
        s.apply(ReviewOp(kind="flag_finding", target="f2"))
        replayed = ReviewSession.replay(_report(), s.state.log)
        # same final review state from the log alone
        for k in ("f0", "f1", "f2"):
            assert replayed.state.findings[k].review_status == s.state.findings[k].review_status

    def test_audit_log_records_actions(self):
        s = ReviewSession(_report())
        s.apply(ReviewOp(kind="accept_finding", target="f1"))
        trail = s.audit_log()
        assert trail[-1]["kind"] == "accept_finding"
        assert trail[-1]["target"] == "f1"


# --------------------------------------------------------------------------- #
# NL compiler (deterministic path)
# --------------------------------------------------------------------------- #
class TestNlDeterministic:
    def test_parse_time_mmss_and_units(self):
        assert _parse_time("after 2:00")[0] == 120.0
        assert _parse_time("after 90 seconds")[0] == 90.0
        assert _parse_time("before 3 minutes")[1] == 180.0

    def test_dismiss_reading_speed_selects_both_rules_grounded(self):
        s = ReviewSession(_report())
        res = compile_nl_deterministic("dismiss all reading-speed flags", s)
        assert res.intent == "mutate"
        # reading-speed hints (CPS + CAP-03) match f0 (NFLX-CPS-01) and f2 (DCMP-CAP-03)
        assert set(res.matched) == {"f0", "f2"}
        assert all(op.kind == "dismiss_finding" for op in res.ops)

    def test_time_window_narrows_selection(self):
        s = ReviewSession(_report())
        res = compile_nl_deterministic("dismiss reading-speed flags after 2:30", s)
        # only f2 (timecode 200 >= 150); f0 (130) excluded
        assert res.matched == ["f2"]

    def test_show_is_a_query_not_a_mutation(self):
        s = ReviewSession(_report())
        res = compile_nl_deterministic("show me the DCMP errors", s)
        assert res.intent == "query"
        assert res.query.family == "DCMP"

    def test_reason_captured(self):
        s = ReviewSession(_report())
        res = compile_nl_deterministic(
            "dismiss all reading-speed flags as acceptable for this title", s)
        assert any(op.payload.get("reason") for op in res.ops)


# --------------------------------------------------------------------------- #
# END-TO-END via the API
# --------------------------------------------------------------------------- #
class TestReviewApiE2E:
    def test_full_flow(self):
        client = TestClient(app)

        # 1. open a session on the bundled demo report (no upload needed)
        r = client.post("/review/session", json={"report_id": "demo"})
        assert r.status_code == 200, r.text
        view = r.json()
        sid = view["session_id"]
        assert view["summary"]  # has findings
        keys = list(view["findings"].keys())
        assert keys, "demo report produced no reviewable findings"

        # 2. natural-language op: dismiss reading-speed flags (grounded + applied)
        r = client.post("/review/nl", json={
            "session_id": sid,
            "phrase": "dismiss all reading-speed flags as acceptable for this title",
            "apply": True,
        })
        assert r.status_code == 200, r.text
        nl = r.json()["nl"]
        assert nl["intent"] == "mutate"
        assert nl["engine"] in ("deterministic", "watsonx")
        # every compiled op targets a REAL finding key (grounded)
        for op in nl["compiled_ops"]:
            assert op["target"] in keys

        # 3. explicit typed op on a real finding
        target = keys[0]
        r = client.post("/review/op", json={
            "session_id": sid, "kind": "accept_finding", "target": target,
        })
        assert r.status_code == 200, r.text
        assert r.json()["findings"][target]["review_status"] == "accepted"

        # 4. grounding: an op on a non-existent finding is rejected (422)
        r = client.post("/review/op", json={
            "session_id": sid, "kind": "accept_finding", "target": "f99999",
        })
        assert r.status_code == 422

        # 5. undo the last real op -> its inverse restores prior state
        before = client.get(f"/review/{sid}").json()["version"]
        r = client.post("/review/undo", json={"session_id": sid})
        assert r.status_code == 200
        assert r.json()["version"] == before + 1  # undo is appended (append-only)

        # 6. audit trail exists and is ordered
        trail = client.get(f"/review/{sid}").json()["audit_log"]
        assert len(trail) >= 3
        assert trail[-1]["source"] == "undo"
