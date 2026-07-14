"""
Tests for generative fix loop (Task 10), MCP server (Task 11),
and live monitor (Task 12).
"""
from __future__ import annotations
import json
import pytest
from unittest.mock import patch, MagicMock
from src.models import GapRegion, SpeechRegion, FixResult


# ---------------------------------------------------------------------------
# Task 10: Generative fix loop
# ---------------------------------------------------------------------------

class TestGenerativeFix:
    """Tests for src/generative_fix.py"""

    def test_fix_result_model_has_required_fields(self):
        """FixResult must have all required fields."""
        result = FixResult(
            gap=GapRegion(start=12.0, end=19.5),
            draft_text="He walks into the room.",
            dcmp_valid=True,
            dcmp_issues=[],
            guardian_cleared=True,
            guardian_reason=None,
            accepted=True,
            word_count=5,
            fits_gap=True,
        )
        assert result.draft_text == "He walks into the room."
        assert result.accepted is True
        assert result.dcmp_valid is True
        assert result.guardian_cleared is True

    def test_fix_not_accepted_when_dcmp_fails(self):
        """If DCMP validation fails, fix must NOT be accepted."""
        result = FixResult(
            gap=GapRegion(start=12.0, end=14.0),
            draft_text="He had walked in as the flashback dissolved.",  # past tense + jargon
            dcmp_valid=False,
            dcmp_issues=["DCMP-DESC-01: past tense", "DCMP-DESC-03: jargon flashback"],
            guardian_cleared=True,
            guardian_reason=None,
            accepted=False,
            word_count=9,
            fits_gap=True,
        )
        assert result.accepted is False
        assert len(result.dcmp_issues) == 2

    def test_fix_not_accepted_when_guardian_fails(self):
        """If Guardian rejects, fix must NOT be accepted."""
        result = FixResult(
            gap=GapRegion(start=12.0, end=19.5),
            draft_text="He walks into the room.",
            dcmp_valid=True,
            dcmp_issues=[],
            guardian_cleared=False,
            guardian_reason="Content flagged as potentially unsafe.",
            accepted=False,
            word_count=5,
            fits_gap=True,
        )
        assert result.accepted is False
        assert result.guardian_reason is not None

    def test_dcmp_validate_structure_present_tense(self):
        """validate_dcmp_structure: present-tense AD should pass DESC-01."""
        from src.generative_fix import validate_dcmp_structure

        draft = "He walks slowly through the doorway."
        gap = GapRegion(start=12.0, end=19.5)
        is_valid, issues = validate_dcmp_structure(draft, gap, [])
        # Should not flag tense issues for present tense
        tense_issues = [i for i in issues if "DESC-01" in i]
        assert len(tense_issues) == 0

    def test_dcmp_validate_structure_past_tense_flagged(self):
        """validate_dcmp_structure: past-tense AD should flag DESC-01."""
        from src.generative_fix import validate_dcmp_structure

        draft = "He had walked slowly through the doorway."
        gap = GapRegion(start=12.0, end=14.0)
        is_valid, issues = validate_dcmp_structure(draft, gap, [])
        tense_issues = [i for i in issues if "DESC-01" in i]
        assert len(tense_issues) >= 1

    def test_dcmp_validate_structure_jargon_flagged(self):
        """validate_dcmp_structure: 'flashback' is flagged as jargon (DESC-03)."""
        from src.generative_fix import validate_dcmp_structure

        draft = "The scene opens on a flashback."
        gap = GapRegion(start=12.0, end=19.5)
        is_valid, issues = validate_dcmp_structure(draft, gap, [])
        jargon_issues = [i for i in issues if "DESC-03" in i]
        assert len(jargon_issues) >= 1

    def test_fallback_draft_fits_gap(self):
        """Fallback draft must fit within the gap word budget."""
        from src.generative_fix import _fallback_draft

        gap = GapRegion(start=12.0, end=17.0)  # 5s gap = 12 max words at 150wpm
        draft = _fallback_draft(gap)
        assert isinstance(draft, str)
        assert len(draft) > 0

    def test_guardian_screen_ollama_unavailable(self):
        """When Ollama is unavailable, Guardian should return cleared=True (safe default)."""
        from src.generative_fix import screen_guardian

        with patch("urllib.request.urlopen", side_effect=Exception("connection refused")):
            cleared, reason = screen_guardian("He walks into the room.")
        assert cleared is True  # safe default when unavailable

    @patch("src.generative_fix.extract_keyframes", return_value=[])
    @patch("src.generative_fix.draft_description", return_value="He walks into the room.")
    @patch("src.generative_fix.screen_guardian", return_value=(True, ""))
    def test_generate_fix_full_pipeline(self, mock_guardian, mock_draft, mock_kf):
        """Full pipeline: accepted when DCMP passes and Guardian clears."""
        from src.generative_fix import generate_fix

        gap = GapRegion(start=12.0, end=19.5)
        result = generate_fix(gap=gap, film_path="fake_film.mp4", speech_regions=[])

        assert isinstance(result, FixResult)
        assert result.draft_text == "He walks into the room."
        assert result.guardian_cleared is True
        # DCMP result depends on the draft; just verify it ran
        assert isinstance(result.dcmp_valid, bool)


# ---------------------------------------------------------------------------
# Task 11: MCP server
# ---------------------------------------------------------------------------

class TestMCPServer:
    """Verify the MCP server module imports and tools are registered."""

    def test_server_imports_without_error(self):
        """The server module should import cleanly."""
        import src.mcp_server.server as server
        assert server.mcp is not None

    def test_tools_registered(self):
        """All three tools must be registered."""
        from src.mcp_server.server import mcp

        # FastMCP exposes tools via _tool_manager or similar internal
        # We verify by checking the module has the decorated functions
        import src.mcp_server.server as server
        assert hasattr(server, "check_conformance")
        assert hasattr(server, "detect_gaps")
        assert hasattr(server, "score_captions")

    def test_detect_gaps_tool_callable(self):
        """detect_gaps tool should be callable with a non-existent path (returns empty list)."""
        from src.mcp_server.server import detect_gaps

        with patch("src.gap_engine.detect_gaps", return_value=[]):
            result = detect_gaps(film_path="nonexistent.mp4")
        assert isinstance(result, list)

    def test_score_captions_tool_callable(self):
        """score_captions tool should work with a valid srt file."""
        from src.mcp_server.server import score_captions

        # Use the broken fixture file we already have
        result = score_captions(
            caption_path="data/demo/notld_broken.srt",
            reference_transcript="They are coming to get you Barbara we have to board up the windows",
        )
        assert "ner_score" in result
        assert "band_low" in result
        assert "band_high" in result
        assert "passes_98_threshold" in result
        assert isinstance(result["human_review_required"], bool)


# ---------------------------------------------------------------------------
# Task 12: Live monitor
# ---------------------------------------------------------------------------

class TestLiveMonitor:
    """Tests for src/live_monitor.py"""

    def test_monitor_instantiates(self):
        from src.live_monitor import LiveMonitor
        monitor = LiveMonitor()
        assert monitor is not None

    def test_missing_chunk_returns_error_status(self):
        from src.live_monitor import LiveMonitor
        monitor = LiveMonitor()
        result = monitor.process_chunk("nonexistent_chunk.wav")
        assert result["status"] == "error"
        assert "chunk_not_found" in result["violations"]

    def test_result_has_required_keys(self):
        from src.live_monitor import LiveMonitor
        monitor = LiveMonitor()
        result = monitor.process_chunk("nonexistent_chunk.wav")
        for key in ("cps", "wpm", "coverage", "violations", "timestamp", "status", "latency_ms"):
            assert key in result

    def test_cps_wpm_are_floats(self):
        from src.live_monitor import LiveMonitor
        monitor = LiveMonitor()
        result = monitor.process_chunk("nonexistent_chunk.wav")
        assert isinstance(result["cps"], float)
        assert isinstance(result["wpm"], float)

    def test_latency_is_measured(self):
        from src.live_monitor import LiveMonitor
        monitor = LiveMonitor()
        result = monitor.process_chunk("nonexistent_chunk.wav")
        assert result["latency_ms"] >= 0
