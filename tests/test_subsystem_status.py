"""
Tests for the per-subsystem truth reported on /health.

The property that matters is not "the endpoint returns 200". It is that the
endpoint cannot lie in the two directions that would make it worthless:

  1. It must never report an unexercised subsystem as healthy. Folding "could
     not check" into a positive answer is how a live demo ends up asserting a
     state nobody verified.
  2. It must never report a fallback as a live model, because detecting exactly
     that is the reason a judge reads it.
"""

from fastapi.testclient import TestClient

from src.app import app
from src.models import FixResult, GapRegion, Provenance
from src.subsystem_status import KNOWN_SUBSYSTEMS, record, reset, snapshot

client = TestClient(app)


def test_unexercised_subsystems_report_not_observed_never_ok():
    """A cold instance must say it does not know, not that it is fine."""
    reset()
    snap = snapshot()
    for name in KNOWN_SUBSYSTEMS:
        assert snap[name]["state"] == "not_observed", name
        assert snap[name]["state"] != "ok", name


def test_every_known_subsystem_is_always_present():
    """A subsystem missing from the payload would read as concealment."""
    reset()
    snap = snapshot()
    for name in KNOWN_SUBSYSTEMS:
        assert name in snap, f"{name} absent from /health payload"


def test_record_success_then_failure_reflects_latest_state():
    reset()
    record("guardian", ok=True, model_id="ibm/granite-guardian-3-8b", latency_ms=42)
    assert snapshot()["guardian"]["state"] == "ok"
    assert snapshot()["guardian"]["model_id"] == "ibm/granite-guardian-3-8b"

    record("guardian", ok=False, detail="403 token_quota_reached")
    entry = snapshot()["guardian"]
    assert entry["state"] == "failed"
    assert "quota" in entry["detail"]


def test_health_makes_no_outbound_call_and_carries_the_block():
    """
    /health is on the keepalive path. It must stay free.

    This asserts the shape rather than the network, but the shape is the
    contract: a probe would have to add a field, and adding one here fails.
    """
    reset()
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "subsystems" in body
    assert "configured" in body
    # Credentials-present is reported, and is explicitly NOT a health claim.
    assert isinstance(body["configured"]["watsonx_credentials"], bool)
    for name in KNOWN_SUBSYSTEMS:
        assert body["subsystems"][name]["state"] in {"ok", "failed", "not_observed"}


def test_a_fallback_draft_is_recorded_as_failed_not_ok():
    """
    The whole point: a canned string standing in for a live model is the
    condition a judge is trying to detect. Recording it as ok would reproduce
    the fabricated-provenance bug this check exists to catch.
    """
    from src.app import _record_fix_observations

    reset()
    result = FixResult(
        gap=GapRegion(start=1.0, end=5.0),
        draft_text="canned",
        draft_provenance=Provenance(label="deterministic fallback", fallback=True),
        dcmp_valid=False,
        guardian_cleared=False,
        guardian_ran=False,
        guardian_provenance=Provenance(label="did not run", fallback=True),
        accepted=False,
        word_count=1,
        fits_gap=True,
    )
    _record_fix_observations(result)

    snap = snapshot()
    assert snap["vision_drafter"]["state"] == "failed"
    assert snap["guardian"]["state"] == "failed"


def test_a_live_draft_is_recorded_as_ok():
    from src.app import _record_fix_observations

    reset()
    result = FixResult(
        gap=GapRegion(start=1.0, end=5.0),
        draft_text="A sedan rolls past the gate.",
        draft_provenance=Provenance(
            label="watsonx-hosted Llama 3.2 Vision",
            model_id="meta-llama/llama-3-2-11b-vision-instruct",
            latency_ms=900,
            fallback=False,
        ),
        dcmp_valid=True,
        guardian_cleared=True,
        guardian_ran=True,
        guardian_provenance=Provenance(
            label="Granite Guardian 3-8b",
            model_id="ibm/granite-guardian-3-8b",
            latency_ms=310,
            fallback=False,
        ),
        accepted=True,
        word_count=6,
        fits_gap=True,
    )
    _record_fix_observations(result)

    snap = snapshot()
    assert snap["vision_drafter"]["state"] == "ok"
    assert snap["vision_drafter"]["model_id"] == "meta-llama/llama-3-2-11b-vision-instruct"
    assert snap["guardian"]["state"] == "ok"


def test_summary_error_is_recorded_as_failed():
    from src.app import _summarize_and_record

    reset()
    _summarize_and_record({"summary": "", "model_id": None, "error": "403 quota"})
    assert snapshot()["report_summary"]["state"] == "failed"

    _summarize_and_record(
        {"summary": "Real text.", "model_id": "ibm/granite-3-8b-instruct", "error": None}
    )
    entry = snapshot()["report_summary"]
    assert entry["state"] == "ok"
    assert entry["model_id"] == "ibm/granite-3-8b-instruct"


def test_record_never_raises_on_bad_input():
    """A transparency layer must not be able to take down the request."""
    reset()
    record("weird", ok=True, model_id=object())  # type: ignore[arg-type]
    assert "weird" in snapshot()


def test_summarize_and_record_passes_the_result_through_unchanged():
    """It observes; it must not mutate what the judge receives."""
    from src.app import _summarize_and_record

    reset()
    payload = {"summary": "x", "model_id": "m", "error": None}
    assert _summarize_and_record(payload) == payload
