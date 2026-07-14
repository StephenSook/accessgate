"""
End-to-end tests for the assembled conformance pipeline.

These exercise run_engine and the JSON contract the frontend depends on.
They deliberately run WITHOUT the heavy ML stack (no faster-whisper, no
Silero/torch, no sentence-transformers) so they reproduce the hosted deploy
environment: VAD and NER must degrade gracefully, the rule evaluators must
still produce real results, and the report must serialize the computed
error/warning/flag counts.

This is the coverage gap that let a broken `score_captions` import and a
768-vs-512 RAG dimension mismatch reach production while 172 unit tests
stayed green.
"""
from __future__ import annotations

import json
from pathlib import Path

from src.engine import run_engine

DEMO_SRT = Path(__file__).parent.parent / "data" / "demo" / "notld_broken.srt"


def test_run_engine_imports_and_runs_without_ml_stack(tmp_path):
    """run_engine must import cleanly and produce results even when VAD/NER
    are unavailable (the hosted deploy case)."""
    dummy_film = tmp_path / "film.mp4"
    dummy_film.write_bytes(b"\x00" * 512)  # not decodable -> VAD/NER skip

    report = run_engine(
        film_path=str(dummy_film),
        caption_path=str(DEMO_SRT),
        ad_path=None,
        profile="netflix",
    )

    # Real rule evaluation happened on the caption file.
    assert len(report.results) > 0
    assert any(r.status == "fail" for r in report.results)

    # VAD / NER degraded gracefully rather than crashing.
    assert report.ner is None
    assert report.gaps == []


def test_report_serializes_computed_counts(tmp_path):
    """The frontend metrics bar reads error_count/warning_count/flag_count from
    the JSON. They are computed fields and MUST be present in model_dump_json."""
    dummy_film = tmp_path / "film.mp4"
    dummy_film.write_bytes(b"\x00" * 512)

    report = run_engine(
        film_path=str(dummy_film),
        caption_path=str(DEMO_SRT),
        ad_path=None,
        profile="netflix",
    )

    payload = json.loads(report.model_dump_json())
    for key in ("error_count", "warning_count", "flag_count"):
        assert key in payload, f"{key} missing from serialized report"
        assert isinstance(payload[key], int)

    # Every result carries a non-placeholder citation retrieved from the RAG layer.
    for r in payload["results"]:
        assert r["citation"]
        assert not r["citation"].startswith("[Citation")
