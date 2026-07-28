"""
Exercise the watsonx SUCCESS paths.

Why this file exists: on 2026-07-27 the account's token quota was exhausted, so
every watsonx call returns 403 in about 0.6 s. That makes the failure paths very
well tested and the success paths completely unexercised in production, and the
quota does not reset until the first of the month, which is also the first day of
judging and the day after the last possible commit. Anything that only breaks
when watsonx WORKS would surface exactly when it could no longer be fixed.

So these stub requests.post with realistic success payloads, shaped exactly like
the responses the real endpoints return, and assert the behaviour that only
becomes reachable once the calls succeed. In particular `accepted=True`, which
is currently unreachable on the deploy and which gates the resolves_rule_ids the
UI uses to flip a row green.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from src.models import GapRegion, SpeechRegion


class _Resp:
    def __init__(self, payload, status=200):
        self._p, self.status_code, self.headers = payload, status, {}

    def json(self):
        return self._p

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def _chat(content: str):
    """Shape returned by /ml/v1/text/chat (vision, guardian, NL compiler)."""
    return _Resp({"choices": [{"message": {"content": content}}]})


def route(vision: str = "A woman walks through a graveyard.", guardian: str = "No",
          generation: str = "A plain-English summary."):
    """One dispatcher for every watsonx call.

    All these modules do `import requests`, so they share ONE module object.
    Patching `src.watsonx_vision.requests.post` and then
    `src.watsonx_guardian.requests.post` sets the same attribute twice and the
    last one wins for both, which silently fed the guardian's reply to the vision
    drafter. Route on the model id in the payload instead.
    """
    def _post(url, json=None, headers=None, timeout=None, **kw):
        model = (json or {}).get("model_id", "")
        if "vision" in model:
            return _chat(vision)
        if "guardian" in model:
            return _chat(guardian)
        return _generation(generation)
    return _post


def _keyframes() -> list[str]:
    """Real committed keyframes. draft_from_keyframes correctly refuses to call
    watsonx with an empty list, so passing [] tests nothing."""
    kf = sorted(pathlib.Path("data/demo/keyframes").glob("*.jpg"))
    assert kf, "expected committed demo keyframes"
    return [str(k) for k in kf[:3]]


def _generation(text: str):
    """Shape returned by /ml/v1/text/generation (summary, showcase)."""
    return _Resp({"results": [{"generated_text": text}]})


@pytest.fixture(autouse=True)
def _watsonx_configured(monkeypatch):
    monkeypatch.setenv("WATSONX_API_KEY", "k")
    monkeypatch.setenv("WATSONX_PROJECT", "p")
    for mod in ("watsonx_vision", "watsonx_guardian", "report_summary",
                "watsonx_showcase", "watsonx_nl"):
        monkeypatch.setattr(f"src.{mod}._iam_token", lambda _k: "tok", raising=False)
    yield


class TestVisionDraftSucceeds:
    def test_draft_is_parsed_and_quotes_stripped(self, monkeypatch):
        monkeypatch.setattr("requests.post", route(vision='"A woman walks through a graveyard."'))
        from src.watsonx_vision import draft_from_keyframes
        out = draft_from_keyframes(_keyframes(), 39.06, 44.94)
        assert out["generated_text"] == "A woman walks through a graveyard."
        assert "Llama" in out["source"] or "watsonx" in out["source"]
        assert not out.get("error")


class TestGuardianClearsOnSuccess:
    def test_no_means_cleared(self, monkeypatch):
        monkeypatch.setattr("requests.post", route(guardian="No"))
        from src.watsonx_guardian import screen_guardian_watsonx
        r = screen_guardian_watsonx("A woman walks through a graveyard.")
        assert r["cleared"] is True and r["ran"] is True

    def test_yes_means_blocked_and_still_ran(self, monkeypatch):
        monkeypatch.setattr("requests.post", route(guardian="Yes"))
        from src.watsonx_guardian import screen_guardian_watsonx
        r = screen_guardian_watsonx("something harmful")
        assert r["cleared"] is False and r["ran"] is True

    def test_unparseable_verdict_refuses_to_claim_a_clean_run(self, monkeypatch):
        monkeypatch.setattr("requests.post", route(guardian="I am not sure about that"))
        from src.watsonx_guardian import screen_guardian_watsonx
        r = screen_guardian_watsonx("x")
        assert r["ran"] is False and r["cleared"] is False


class TestSummarySucceeds:
    def test_summary_text_is_returned_with_no_error(self, monkeypatch):
        monkeypatch.setattr("requests.post", route(generation="  Four errors and eleven warnings.  "))
        from src.report_summary import summarize_report
        out = summarize_report({"error_count": 4, "warning_count": 11, "flag_count": 5,
                                "results": [], "ner": {"ner_score": 0.78}})
        assert out["summary"] == "Four errors and eleven warnings."
        assert not out.get("error")


class TestTheAcceptPathIsReachable:
    """`accepted=True` is unreachable on the deploy today. It must work on Aug 1."""

    def _gap(self):
        return GapRegion(start=39.06, end=44.94)

    def test_clean_draft_is_accepted_and_resolves_rules(self, monkeypatch):
        monkeypatch.setattr("requests.post", route())
        from src.generative_fix import generate_demo_fix

        result, source = generate_demo_fix(self._gap(), _keyframes(), speech_regions=[])

        assert result.draft_text == "A woman walks through a graveyard."
        assert result.dcmp_valid is True, result.dcmp_issues
        assert result.guardian_ran is True and result.guardian_cleared is True
        assert result.draft_provenance.fallback is False
        assert result.accepted is True, "the accept path must be reachable once watsonx works"
        # This is what the UI uses to flip a row green. Empty here means the
        # row-flip wired into App.tsx silently does nothing.
        assert result.resolves_rule_ids, "accepted fix must name the rules it resolves"
        assert all(r.startswith("DCMP-DESC") for r in result.resolves_rule_ids)

    def test_guardian_block_still_refuses_even_with_a_good_draft(self, monkeypatch):
        monkeypatch.setattr("requests.post", route(guardian="Yes"))
        from src.generative_fix import generate_demo_fix
        result, _ = generate_demo_fix(self._gap(), _keyframes(), speech_regions=[])
        assert result.accepted is False
        assert result.resolves_rule_ids == []

    def test_overlong_draft_is_refused_by_the_gate_not_by_watsonx(self, monkeypatch):
        long_draft = " ".join(["word"] * 200)
        monkeypatch.setattr("requests.post", route(vision=long_draft))
        from src.generative_fix import generate_demo_fix
        result, _ = generate_demo_fix(self._gap(), _keyframes(), speech_regions=[])
        assert result.fits_gap is False
        assert result.accepted is False


class TestEndpointsOnceWatsonxWorks:
    """Endpoint-level behaviour a judge triggers, currently masked by the 403."""

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from src.app import app
        return TestClient(app)

    def test_demo_fix_returns_an_accepted_result_with_resolved_rules(self, client, monkeypatch):
        monkeypatch.setattr("requests.post", route())
        r = client.post("/demo-fix", data={"gap_start": 39.06, "gap_end": 44.94})
        assert r.status_code == 200
        b = r.json()
        assert b["accepted"] is True
        assert b["guardian_ran"] is True and b["guardian_cleared"] is True
        assert b["draft_provenance"]["fallback"] is False
        # The frontend reads exactly these to flip the row green.
        assert b["resolves_rule_ids"], "UI cannot flip a row without these"
        assert b["draft_source"] and "fallback" not in b["draft_source"].lower()

    def test_demo_summary_returns_text_and_no_error(self, client, monkeypatch):
        monkeypatch.setattr("requests.post", route(generation="Four errors, eleven warnings."))
        b = client.get("/demo-summary").json()
        assert b.get("summary") == "Four errors, eleven warnings."
        assert not b.get("error")

    def test_summary_endpoint_accepts_a_report_body(self, client, monkeypatch):
        monkeypatch.setattr("requests.post", route(generation="Summary text."))
        r = client.post("/summary", json={"error_count": 1, "warning_count": 2,
                                          "flag_count": 3, "results": [], "ner": {}})
        assert r.status_code == 200
        assert r.json().get("summary") == "Summary text."

    def test_judges_reports_a_live_encoder_either_way(self, client):
        prov = client.get("/judges").json()["citation_provenance"]
        assert prov["active"], "judges must always name the encoder actually in use"


class TestNLCompilerOnceWatsonxWorks:
    """The NL review compiler parses structured JSON from the model.

    Currently every call 403s and falls to the deterministic compiler, so the
    watsonx branch, its JSON extraction, and the re-grounding step are entirely
    unexercised in production.
    """

    def _session(self):
        import json as _json
        from src.models import ConformanceReport
        from src.review_session import ReviewSession
        report = ConformanceReport(**_json.loads(
            pathlib.Path("data/demo/demo_report.json").read_text()))
        return ReviewSession(report, report_id="demo-notld-2026")

    def _route_intent(self, content: str):
        def _post(url, json=None, headers=None, timeout=None, **kw):
            return _chat(content)
        return _post

    def test_bare_json_intent_is_parsed_and_reported_as_watsonx(self, monkeypatch):
        monkeypatch.setattr("requests.post", self._route_intent(
            '{"action": "dismiss", "family": "DCMP", "level": null, "topic": null}'))
        from src.review_session import compile_nl
        res = compile_nl("dismiss the DCMP findings", self._session())
        assert res.engine == "watsonx"
        assert "re-grounded" in res.reasoning

    def test_fenced_json_is_parsed(self, monkeypatch):
        """Chat models routinely wrap JSON in a markdown fence."""
        monkeypatch.setattr("requests.post", self._route_intent(
            '```json\n{"action": "flag", "family": "NFLX"}\n```'))
        from src.review_session import compile_nl
        res = compile_nl("flag the netflix ones", self._session())
        assert res.engine == "watsonx"

    def test_prose_wrapped_json_is_parsed(self, monkeypatch):
        monkeypatch.setattr("requests.post", self._route_intent(
            'Sure! Here is the intent: {"action": "dismiss", "family": "FCC"} Hope that helps.'))
        from src.review_session import compile_nl
        res = compile_nl("dismiss fcc", self._session())
        assert res.engine == "watsonx"

    def test_unparseable_model_output_falls_back_deterministically(self, monkeypatch):
        monkeypatch.setattr("requests.post", self._route_intent("I cannot help with that."))
        from src.review_session import compile_nl
        res = compile_nl("dismiss every reading-speed flag", self._session())
        assert res.engine == "deterministic"

    def test_model_cannot_invent_a_finding_that_does_not_exist(self, monkeypatch):
        """The grounding guarantee: re-run through the deterministic selector."""
        monkeypatch.setattr("requests.post", self._route_intent(
            '{"action": "dismiss", "family": "TOTALLY-MADE-UP"}'))
        from src.review_session import compile_nl
        session = self._session()
        res = compile_nl("dismiss the made up ones", session)
        real_keys = set(session.state.findings)
        for op in res.ops:
            assert op.target in real_keys, "compiler emitted an ungrounded target"
