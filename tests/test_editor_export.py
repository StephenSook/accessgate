"""
Tests for the editor-native exporters (src/exporters/editor.py):
AD-fix -> WebVTT descriptions, findings -> CSV (formula-injection hardened),
findings -> WebVTT markers.
"""
from __future__ import annotations
import csv
import io

from src.models import ConformanceReport, RuleResult, GapRegion, FixResult
from src.exporters.editor import (
    export_findings_csv,
    export_findings_markers_vtt,
    export_ad_descriptions_vtt,
    export_editor_bundle,
    _csv_safe,
    _vtt_ts,
)


def _report() -> ConformanceReport:
    return ConformanceReport(
        film_path="film.mp4",
        caption_path="captions.srt",
        results=[
            RuleResult(rule_id="DCMP-CAP-01", status="fail", message="Line 44 chars",
                       timecode=44.0, sarif_level="error"),
            RuleResult(rule_id="NFLX-CPS-01", status="flag", message="Reading speed high",
                       timecode=120.5, sarif_level="warning", human_review_required=True),
            RuleResult(rule_id="WCAG-1-2-2", status="pass", message="ok", timecode=1.0),
            RuleResult(rule_id="FCC-79-1-A", status="fail",
                       message="=SUM(A1:A9) sync drift", timecode=None, sarif_level="warning"),
        ],
    )


class TestVttTimestamp:
    def test_format(self):
        assert _vtt_ts(0) == "00:00:00.000"
        assert _vtt_ts(67.2) == "00:01:07.200"
        assert _vtt_ts(3661.5) == "01:01:01.500"

    def test_negative_clamped(self):
        assert _vtt_ts(-5) == "00:00:00.000"


class TestCsvSafe:
    def test_neutralizes_formula_leads(self):
        for lead in ("=", "+", "-", "@"):
            assert _csv_safe(lead + "cmd").startswith("'" + lead)

    def test_plain_text_untouched(self):
        assert _csv_safe("Line 44 chars") == "Line 44 chars"

    def test_none_is_empty(self):
        assert _csv_safe(None) == ""


class TestFindingsCsv:
    def test_header_and_only_reportable_rows(self):
        out = export_findings_csv(_report())
        rows = list(csv.reader(io.StringIO(out)))
        assert rows[0][0] == "timecode_seconds"
        # 3 reportable (2 fail + 1 flag); the 'pass' row is excluded
        data = rows[1:]
        assert len(data) == 3
        rule_ids = {r[2] for r in data}
        assert "WCAG-1-2-2" not in rule_ids  # pass excluded
        assert {"DCMP-CAP-01", "NFLX-CPS-01", "FCC-79-1-A"} == rule_ids

    def test_formula_injection_neutralized_in_message(self):
        out = export_findings_csv(_report())
        # the =SUM(...) message must be quoted-out as text (leading ')
        assert "'=SUM(A1:A9) sync drift" in out
        assert "\n=SUM" not in out  # never a bare formula cell start

    def test_writes_file(self, tmp_path):
        p = tmp_path / "f.csv"
        export_findings_csv(_report(), p)
        assert p.exists() and "DCMP-CAP-01" in p.read_text()


class TestMarkersVtt:
    def test_valid_webvtt_and_navigable(self):
        out = export_findings_markers_vtt(_report())
        assert out.startswith("WEBVTT")
        assert "[DCMP-CAP-01] Line 44 chars" in out
        assert "00:00:44.000 --> 00:00:46.000" in out

    def test_findings_without_timecode_excluded(self):
        out = export_findings_markers_vtt(_report())
        # FCC rule had timecode=None -> no marker cue for it
        assert "FCC-79-1-A" not in out


class TestAdDescriptionsVtt:
    def _fix(self, accepted: bool) -> FixResult:
        return FixResult(
            gap=GapRegion(start=67.2, end=73.8),
            draft_text="A man walks slowly toward the boarded farmhouse.",
            dcmp_valid=True, guardian_cleared=accepted, accepted=accepted,
            word_count=8, fits_gap=True,
        )

    def test_accepted_fix_becomes_cue(self):
        out = export_ad_descriptions_vtt([self._fix(True)])
        assert out.startswith("WEBVTT")
        assert "00:01:07.200 --> 00:01:13.800" in out
        assert "A man walks slowly toward the boarded farmhouse." in out

    def test_unaccepted_fix_excluded_by_default(self):
        out = export_ad_descriptions_vtt([self._fix(False)])
        # header present but no cue
        assert "-->" not in out


class TestBundle:
    def test_writes_report_exports(self, tmp_path):
        written = export_editor_bundle(_report(), tmp_path, "notld")
        assert written["findings_csv"].exists()
        assert written["markers_vtt"].exists()
        assert "descriptions_vtt" not in written  # no fixes passed
