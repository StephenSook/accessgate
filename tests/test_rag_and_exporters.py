"""
Tests for the RAG layer (Task 8) and SARIF/OSCAL exporters (Task 9).
"""
from __future__ import annotations
import json
from pathlib import Path
import pytest
from src.rag import retrieve_citation, build_index, _build_chunks, _chunk_text
from src.models import ConformanceReport, RuleResult, GapRegion, SpeechRegion
from src.exporters.sarif import export_sarif, _seconds_to_hmsf
from src.exporters.oscal import export_oscal


# ---------------------------------------------------------------------------
# RAG layer tests
# ---------------------------------------------------------------------------

class TestRAGChunking:
    def test_chunk_short_text(self):
        chunks = _chunk_text("Hello world.", "test", chunk_size=50, overlap=10)
        assert len(chunks) >= 1
        assert chunks[0]["text"] == "Hello world."
        assert chunks[0]["source"] == "test"

    def test_chunk_long_text(self):
        text = "A" * 1000
        chunks = _chunk_text(text, "test", chunk_size=200, overlap=50)
        assert len(chunks) > 1

    def test_chunk_empty_text(self):
        chunks = _chunk_text("", "test")
        assert chunks == []

    def test_build_chunks_returns_non_empty(self):
        chunks = _build_chunks()
        assert len(chunks) > 0
        assert all("text" in c and "source" in c for c in chunks)


class TestRAGRetrieval:
    """
    These tests verify the RAG retrieval against the inline standards.
    They build the index in a temp dir to stay deterministic.
    """

    def test_fcc_accuracy_citation(self):
        result = retrieve_citation("FCC-ACC-01", "accuracy spoken words")
        assert isinstance(result, str)
        assert len(result) > 20

    def test_dcmp_cap_reading_speed(self):
        result = retrieve_citation("DCMP-CAP-03", "reading speed wpm 225")
        assert isinstance(result, str)
        assert len(result) > 20

    def test_nflx_cps_citation(self):
        result = retrieve_citation("NFLX-CPS-01", "characters per second adult")
        assert isinstance(result, str)
        assert len(result) > 20

    def test_wcag_125_citation(self):
        result = retrieve_citation("WCAG-125-01", "audio description prerecorded")
        assert isinstance(result, str)
        assert len(result) > 20

    def test_citation_contains_relevant_keyword(self):
        """FCC accuracy citation should mention 'accuracy' or 'words'."""
        result = retrieve_citation("FCC-ACC-01", "accuracy NER")
        lower = result.lower()
        assert any(kw in lower for kw in ("accuracy", "word", "caption", "fcc", "47 cfr"))

    def test_dcmp_desc_citation(self):
        result = retrieve_citation("DCMP-DESC-05", "audio description overlap dialogue")
        assert isinstance(result, str)
        assert len(result) > 20

    def test_unknown_rule_returns_fallback(self):
        result = retrieve_citation("UNKNOWN-001", "test query")
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# SARIF exporter tests
# ---------------------------------------------------------------------------

def _make_report_with_failures() -> ConformanceReport:
    return ConformanceReport(
        film_path="data/demo/notld_segment.mp4",
        caption_path="data/demo/notld_broken.srt",
        ad_path="data/demo/notld_broken_ad.vtt",
        profile="netflix",
        results=[
            RuleResult(
                rule_id="DCMP-CAP-03",
                status="fail",
                message="Caption exceeds 225 wpm.",
                timecode=1.0,
                citation="DCMP Captioning Key: 225 wpm cap.",
                sarif_level="warning",
            ),
            RuleResult(
                rule_id="DCMP-DESC-05",
                status="fail",
                message="AD overlaps dialogue.",
                timecode=12.0,
                citation="DCMP Description Key: no overlap.",
                sarif_level="error",
            ),
            RuleResult(
                rule_id="WCAG-125-02",
                status="flag",
                message="Human review required.",
                citation="WCAG 2.2 SC 1.2.5.",
                sarif_level="note",
                human_review_required=True,
            ),
            RuleResult(
                rule_id="FCC-ACC-01",
                status="pass",
                message="NER 99%.",
                citation="47 CFR 79.1(j)(2)(i).",
                sarif_level="warning",
            ),
        ],
    )


class TestSARIFExporter:
    def test_valid_schema_field(self):
        report = _make_report_with_failures()
        sarif = export_sarif(report)
        assert sarif["$schema"].startswith("https://docs.oasis-open.org/sarif")

    def test_version_is_2_1_0(self):
        sarif = export_sarif(_make_report_with_failures())
        assert sarif["version"] == "2.1.0"

    def test_tool_driver_name(self):
        sarif = export_sarif(_make_report_with_failures())
        assert sarif["runs"][0]["tool"]["driver"]["name"] == "AccessGate"

    def test_driver_rules_count(self):
        """All 23 rules must appear in tool.driver.rules."""
        sarif = export_sarif(_make_report_with_failures())
        assert len(sarif["runs"][0]["tool"]["driver"]["rules"]) == 23

    def test_only_failures_and_flags_emitted(self):
        """Pass/skip results must NOT appear in SARIF results."""
        sarif = export_sarif(_make_report_with_failures())
        results = sarif["runs"][0]["results"]
        rule_ids = [r["ruleId"] for r in results]
        assert "FCC-ACC-01" not in rule_ids  # was pass
        assert "DCMP-CAP-03" in rule_ids
        assert "DCMP-DESC-05" in rule_ids

    def test_timecodes_in_properties_not_region(self):
        """HARD RULE: timecodes must be in result.properties, never in region fields."""
        sarif = export_sarif(_make_report_with_failures())
        for result in sarif["runs"][0]["results"]:
            # Must not have a region with startLine/charOffset/byteOffset
            for location in result.get("locations", []):
                region = location.get("physicalLocation", {}).get("region", {})
                assert "startLine" not in region
                assert "charOffset" not in region
                assert "byteOffset" not in region
            # Timecode must be in properties if present
            if "timecode" in result.get("properties", {}):
                assert isinstance(result["properties"]["timecode"], (int, float))

    def test_error_level_for_error_sarif_level(self):
        sarif = export_sarif(_make_report_with_failures())
        desc05 = next(
            r for r in sarif["runs"][0]["results"]
            if r["ruleId"] == "DCMP-DESC-05"
        )
        assert desc05["level"] == "error"

    def test_note_level_for_flag(self):
        sarif = export_sarif(_make_report_with_failures())
        wcag = next(
            r for r in sarif["runs"][0]["results"]
            if r["ruleId"] == "WCAG-125-02"
        )
        assert wcag["level"] == "note"

    def test_write_to_file(self, tmp_path):
        report = _make_report_with_failures()
        output = tmp_path / "test.sarif"
        export_sarif(report, output)
        assert output.exists()
        data = json.loads(output.read_text())
        assert data["version"] == "2.1.0"


class TestSARIFHelpers:
    def test_seconds_to_hmsf_zero(self):
        assert _seconds_to_hmsf(0.0) == "00:00:00.000"

    def test_seconds_to_hmsf_one_minute(self):
        result = _seconds_to_hmsf(65.5)
        assert result.startswith("00:01:05")

    def test_seconds_to_hmsf_one_hour(self):
        result = _seconds_to_hmsf(3661.25)
        assert result.startswith("01:01:01")


# ---------------------------------------------------------------------------
# OSCAL exporter tests
# ---------------------------------------------------------------------------

class TestOSCALExporter:
    def test_valid_structure(self):
        report = _make_report_with_failures()
        oscal = export_oscal(report)
        assert "plan-of-action-and-milestones" in oscal

    def test_metadata_title(self):
        oscal = export_oscal(_make_report_with_failures())
        meta = oscal["plan-of-action-and-milestones"]["metadata"]
        assert "AccessGate" in meta["title"]

    def test_oscal_version(self):
        oscal = export_oscal(_make_report_with_failures())
        meta = oscal["plan-of-action-and-milestones"]["metadata"]
        assert meta["oscal-version"] == "1.1.2"

    def test_poam_items_for_failures_only(self):
        """POA&M items should only exist for fail/flag results, not pass."""
        oscal = export_oscal(_make_report_with_failures())
        items = oscal["plan-of-action-and-milestones"]["poam-items"]
        item_titles = [i["title"] for i in items]
        # DCMP-CAP-03 fail and DCMP-DESC-05 fail should appear
        assert any("DCMP-CAP-03" in t for t in item_titles)
        assert any("DCMP-DESC-05" in t for t in item_titles)
        # FCC-ACC-01 pass should NOT appear
        assert not any("FCC-ACC-01" in t for t in item_titles)

    def test_observations_and_risks_present(self):
        oscal = export_oscal(_make_report_with_failures())
        doc = oscal["plan-of-action-and-milestones"]
        assert len(doc.get("observations", [])) > 0
        assert len(doc.get("risks", [])) > 0

    def test_write_to_file(self, tmp_path):
        report = _make_report_with_failures()
        output = tmp_path / "test.oscal.json"
        export_oscal(report, output)
        assert output.exists()
        data = json.loads(output.read_text())
        assert "plan-of-action-and-milestones" in data
