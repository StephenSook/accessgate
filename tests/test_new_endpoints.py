"""
Coverage for the endpoints and watsonx modules added for the deployed fix,
the Granite summary, and the mobile client. These assert structure and
graceful degradation, so they pass in CI where no watsonx key is set.
"""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("ACCESSGATE_DEMO_MODE", "true")
from src.app import app  # noqa: E402

client = TestClient(app)

DEMO_SRT = "data/demo/notld_broken.srt"


def test_check_captions_runs_structural_rules():
    with open(DEMO_SRT, "rb") as f:
        r = client.post("/check-captions", files={"captions": ("notld_broken.srt", f, "text/plain")},
                        data={"profile": "netflix"})
    assert r.status_code == 200
    d = r.json()
    assert len(d["results"]) > 0
    # No film -> VAD/NER skip; structural caption rules still produce findings.
    assert d["gaps"] == []
    assert d["ner"] is None
    for key in ("error_count", "warning_count", "flag_count"):
        assert isinstance(d[key], int)


def test_demo_fix_returns_result_with_source():
    r = client.post("/demo-fix", data={"gap_start": 39.1, "gap_end": 44.9})
    assert r.status_code == 200
    d = r.json()
    # Real watsonx draft when the key is present, else a fallback; either way
    # the gated-fix contract holds and the DCMP validator ran.
    assert d["draft_text"]
    assert "draft_source" in d
    assert isinstance(d["dcmp_valid"], bool)


def test_demo_summary_endpoint_shape():
    r = client.get("/demo-summary")
    assert r.status_code == 200
    d = r.json()
    assert d["model_id"] == "ibm/granite-3-8b-instruct"
    # summary present if watsonx configured, else error set — never both empty-silent.
    assert d["summary"] or d["error"]


def test_watsonx_vision_degrades_without_key():
    from src.watsonx_vision import draft_from_keyframes
    r = draft_from_keyframes(["x.jpg"], 0.0, 5.0, api_key="", project_id="")
    assert r["generated_text"] == ""
    assert r["error"]
    assert r["source"] == "watsonx-hosted Llama 3.2 Vision"


def test_report_summary_degrades_without_key():
    from src.report_summary import summarize_report
    r = summarize_report({"results": [], "gaps": [], "profile": "netflix",
                          "error_count": 0, "warning_count": 0, "flag_count": 0, "ner": None},
                         api_key="", project_id="")
    assert r["summary"] == ""
    assert r["error"]


def test_granite_speech_raises_on_missing_media():
    from src.granite_speech import transcribe
    with pytest.raises(RuntimeError):
        transcribe("does_not_exist.wav")


def test_safe_name_blocks_path_traversal():
    from src.app import _safe_name
    assert _safe_name("../../etc/passwd", "d.srt") == "passwd"
    assert _safe_name("/abs/path/x.vtt", "d.vtt") == "x.vtt"
    assert _safe_name("", "default.srt") == "default.srt"
    assert _safe_name(None, "default.srt") == "default.srt"
