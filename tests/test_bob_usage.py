"""The /judges bob_usage section must stay true to the repo it describes.

The build trace is the one piece of IBM Bob evidence a judge can re-derive from
a clone rather than take on trust, which only holds if the commits it names are
real. These tests check the trace against actual `git log` output and check that
the honesty caveats (no session transcripts, MCP wiring is a capability not a
logged event) have not quietly drifted back into overclaims.
"""

import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.app import _BOB_BUILD_TRACE, _bob_usage, app

REPO_ROOT = Path(__file__).resolve().parent.parent


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    ).stdout


def _has_build_trace_history() -> bool:
    """True only if the commits the trace names are actually reachable here.

    Being inside a git repo is NOT enough, which is how this first went red on
    CI: actions/checkout defaults to a depth-1 shallow clone, so `rev-parse
    --git-dir` succeeded, these tests ran, and every `cat-file` failed on a
    history that held one commit. CI now checks out with fetch-depth: 0 so the
    trace is genuinely verified there; this guard exists for the other cases
    (a source tarball, or a shallow clone someone makes by hand).
    """
    try:
        _git("rev-parse", "--git-dir")
        for entry in _BOB_BUILD_TRACE:
            _git("cat-file", "-e", f"{entry['commit']}^{{commit}}")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


needs_git = pytest.mark.skipif(
    not _has_build_trace_history(),
    reason="build-trace commits unreachable (source tarball or shallow clone)",
)


class TestBuildTraceIsReal:
    @needs_git
    def test_every_commit_in_the_trace_exists(self):
        for entry in _BOB_BUILD_TRACE:
            sha = entry["commit"]
            # cat-file raises CalledProcessError if the object is unknown.
            kind = _git("cat-file", "-t", sha).strip()
            assert kind == "commit", f"{sha} is a {kind}, not a commit"

    @needs_git
    def test_subjects_and_times_match_git(self):
        """A reworded commit subject must fail here, not mislead a judge."""
        for entry in _BOB_BUILD_TRACE:
            sha = entry["commit"]
            subject = _git("log", "-1", "--format=%s", sha).strip()
            # The trace drops the conventional-commit prefix and any trailing
            # test count, so assert on the distinctive middle rather than equality.
            core = entry["subject"].split(",")[0].strip()
            assert core.lower() in subject.lower(), (
                f"{sha} subject drifted: trace says {core!r}, git says {subject!r}"
            )
            when = _git("log", "-1", "--format=%ad", "--date=format:%H:%M", sha).strip()
            assert when == entry["time_et"], (
                f"{sha} time drifted: trace says {entry['time_et']}, git says {when}"
            )

    @needs_git
    def test_trace_commits_are_in_chronological_order(self):
        times = [e["time_et"] for e in _BOB_BUILD_TRACE]
        assert times == sorted(times)

    @needs_git
    def test_test_counts_in_the_trace_never_go_backwards(self):
        counts = [e["tests"] for e in _BOB_BUILD_TRACE if e["tests"] is not None]
        assert counts == sorted(counts), f"test counts not monotonic: {counts}"

    @needs_git
    def test_commits_that_day_matches_git(self):
        day = _git("log", "--format=%ad", "--date=short")
        actual = day.count("2026-07-13")
        assert _bob_usage()["build_trace"]["commits_that_day"] == actual


class TestBobArtifactsExist:
    def test_every_claimed_artifact_is_actually_present(self):
        for artifact in _bob_usage()["artifacts_in_repo"]:
            path = REPO_ROOT / artifact["where"]
            assert path.exists(), f"claimed Bob artifact missing: {artifact['where']}"


class TestHonestyCaveatsHold:
    def test_no_session_transcript_is_claimed(self):
        """bob_sessions/ holds no session export; nothing may imply otherwise."""
        exports = list((REPO_ROOT / "bob_sessions").glob("session-*.json"))
        assert exports == [], (
            "a session export appeared; update _bob_usage()['not_in_repo'], which "
            "currently tells judges none exists"
        )
        assert "server-side" in _bob_usage()["not_in_repo"]

    def test_mcp_claim_is_capability_not_logged_event(self):
        body = TestClient(app).get("/judges").json()
        mcp = [
            item for item in body["tiers"]["accelerator"]
            if "MCP" in item["name"]
        ]
        assert mcp, "the MCP accelerator entry disappeared"
        note = mcp[0].get("note", "")
        assert "not a logged event" in note, (
            "the MCP entry must not claim Bob was observed invoking the tools"
        )

    def test_ad_descriptions_export_is_not_claimed_as_wired(self):
        """export_ad_descriptions_vtt exists but no surface calls it."""
        body = TestClient(app).get("/judges").json()
        editor = [
            item for item in body["tiers"]["wired_live"]
            if "Editor-native exports" in item["name"]
        ]
        assert editor, "the editor-exports entry disappeared"
        assert "WebVTT AD track" not in editor[0]["name"], (
            "the AD track is not produced by any shipped surface; do not list it "
            "as a wired export"
        )
        assert "not counted as wired" in editor[0].get("note", "")


class TestJudgesEndpointServesIt:
    def test_bob_usage_is_present_and_populated(self):
        body = TestClient(app).get("/judges").json()
        assert "bob_usage" in body
        trace = body["bob_usage"]["build_trace"]
        assert len(trace["commits"]) == len(_BOB_BUILD_TRACE)
        assert trace["commits"][-1]["tests"] == 172

    def test_role_states_primary_not_exclusive(self):
        role = TestClient(app).get("/judges").json()["bob_usage"]["role"]
        assert "not exclusive" in role
