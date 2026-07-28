"""
Upload error handling on the judge-facing endpoints.

Every case here returned a bare HTTP 500 with no body before the fix, verified
live against the deployed API on 2026-07-27. The frontend renders that as the
literal string "/check failed: 500", so a judge who uploads their own caption
file, which the UI explicitly invites, concludes the engine is broken rather
than that their file is unsupported.
"""
from __future__ import annotations

import io

from fastapi.testclient import TestClient

from src.app import app

client = TestClient(app)


def _srt(body: bytes = b"1\n00:00:01,000 --> 00:00:03,000\nhello\n\n"):
    return ("captions.srt", io.BytesIO(body), "text/plain")


class TestUnsupportedFormatIsRejectedNotCrashed:
    def test_txt_caption_returns_422_naming_supported_formats(self):
        r = client.post(
            "/check-captions",
            files={"captions": ("notes.txt", io.BytesIO(b"not a caption file"), "text/plain")},
        )
        assert r.status_code == 422
        detail = r.json()["detail"]
        assert ".srt" in detail and ".vtt" in detail

    def test_unsupported_extension_on_check_returns_422(self):
        r = client.post(
            "/check",
            files={
                "film": ("film.mp4", io.BytesIO(b"\x00" * 16), "video/mp4"),
                "captions": ("subs.ass", io.BytesIO(b"[Script Info]"), "text/plain"),
            },
        )
        assert r.status_code == 422


class TestMalformedCaptionIsRejectedNotCrashed:
    def test_garbage_srt_returns_422_not_500(self):
        r = client.post(
            "/check-captions",
            files={"captions": _srt(b"\x00\x01\x02 not remotely a subtitle \xff")},
        )
        assert r.status_code != 500
        assert r.status_code == 422
        assert "Could not parse" in r.json()["detail"]

    def test_empty_srt_returns_422_not_500(self):
        r = client.post("/check-captions", files={"captions": _srt(b"")})
        assert r.status_code != 500


class TestOversizedUploadsAreRefused:
    def test_oversized_caption_returns_413(self):
        big = b"x" * (6 * 1024 * 1024)
        r = client.post("/check-captions", files={"captions": _srt(big)})
        assert r.status_code == 413
        assert "limit" in r.json()["detail"]


class TestValidCaptionStillWorks:
    def test_wellformed_srt_returns_a_report(self):
        r = client.post("/check-captions", files={"captions": _srt()})
        assert r.status_code == 200
        body = r.json()
        assert body["report_id"]
        assert len(body["results"]) > 0

    def test_report_id_resolves_afterwards(self):
        """The id used to be minted and never cached, so every export link 404'd."""
        r = client.post("/check-captions", files={"captions": _srt()})
        report_id = r.json()["report_id"]
        assert client.get(f"/report/{report_id}").status_code == 200


class TestCachesAreBounded:
    """Unbounded caches grow for the life of an instance across a judging window."""

    def test_report_cache_evicts_oldest_and_keeps_recent(self):
        from src.app import _report_cache, _remember, _CACHE_LIMIT
        _report_cache.clear()
        for i in range(_CACHE_LIMIT + 10):
            _remember(_report_cache, f"r{i}", {"report_id": f"r{i}"})
        assert len(_report_cache) == _CACHE_LIMIT
        assert "r0" not in _report_cache          # oldest evicted
        assert f"r{_CACHE_LIMIT + 9}" in _report_cache  # newest retained
        _report_cache.clear()


class TestApiRootIsNotA404:
    """The README lists the API host as a link; it must not answer with a 404."""

    def test_root_returns_an_index(self):
        from fastapi.testclient import TestClient
        from src.app import app
        r = TestClient(app).get("/")
        assert r.status_code == 200
        body = r.json()
        assert body["service"] == "AccessGate"
        # Point a judge at the things worth opening.
        assert body["start_here"]["transparency"] == "/judges"
        assert "GET  /judges" in body["endpoints"]
