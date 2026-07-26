"""
Editor-native exporters for AccessGate.

SARIF/OSCAL speak to compliance tooling. These speak to the people who actually
fix the file: captioners and audio-description writers. AccessGate findings and
the gated AD fix export into files an editor can OPEN and USE, not just read:

  - export_ad_descriptions_vtt : the gated AD drafts as a WebVTT descriptions
    track (drop straight into an AD workflow / player descriptions cue).
  - export_findings_csv        : every flag as a triage row (timecode, rule,
    standard, message), CSV-formula-injection hardened.
  - export_findings_markers_vtt: every flag as a navigable WebVTT marker so an
    editor can jump to each problem cue on the timeline.

A file to use, not a report to read.
"""
from __future__ import annotations
import csv
import io
from pathlib import Path
from typing import Iterable, Optional

from src.models import ConformanceReport, FixResult, RuleResult

# rule_id -> standard family, resolved from the registry when available so the
# CSV's "standard" column matches the actual rule source, not a prefix guess.
try:
    from src.registry import all_rules
    _RULE_SOURCE = {r.id: r.source for r in all_rules()}
except Exception:  # registry import must never break an export
    _RULE_SOURCE = {}


def _vtt_ts(seconds: float) -> str:
    """Float seconds -> WebVTT timestamp HH:MM:SS.mmm."""
    seconds = max(0.0, float(seconds))
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


def _standard_for(rule_id: str) -> str:
    """Human standard family for a rule id (registry source, else prefix)."""
    if rule_id in _RULE_SOURCE:
        return _RULE_SOURCE[rule_id]
    prefix = rule_id.split("-")[0].upper()
    return {"DCMP": "DCMP", "FCC": "FCC 47 CFR 79.1", "WCAG": "WCAG 2.2",
            "NFLX": "Netflix TTSG"}.get(prefix, prefix)


def _csv_safe(value: object) -> str:
    """Neutralize CSV formula injection.

    A cell beginning with = + - @ (or a leading tab/CR) is treated as a formula
    by Excel/Sheets. Prefix such values with a single quote so they render as
    text. The csv module still handles quoting/escaping around this.
    """
    text = "" if value is None else str(value)
    if text and text[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + text
    return text


def _reportable(results: Iterable[RuleResult]) -> list[RuleResult]:
    """Only failures and flags are worth an editor's time (skip pass/skip)."""
    return [r for r in results if r.status in ("fail", "flag")]


def export_findings_csv(
    report: ConformanceReport, output_path: Optional[Path] = None
) -> str:
    """Every flagged finding as a triage CSV row. Formula-injection hardened."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "timecode_seconds", "timecode", "rule_id", "status", "level",
        "standard", "message", "human_review_required", "citation",
    ])
    for r in _reportable(report.results):
        tc = "" if r.timecode is None else f"{r.timecode:.3f}"
        tc_h = "" if r.timecode is None else _vtt_ts(r.timecode)
        writer.writerow([
            _csv_safe(tc), _csv_safe(tc_h), _csv_safe(r.rule_id),
            _csv_safe(r.status), _csv_safe(r.sarif_level),
            _csv_safe(_standard_for(r.rule_id)), _csv_safe(r.message),
            _csv_safe(r.human_review_required), _csv_safe(r.citation),
        ])
    out = buf.getvalue()
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(out, encoding="utf-8")
    return out


def export_findings_markers_vtt(
    report: ConformanceReport, output_path: Optional[Path] = None,
    marker_len: float = 2.0,
) -> str:
    """Flagged findings as navigable WebVTT markers (jump to each problem cue)."""
    lines = ["WEBVTT - AccessGate conformance findings", ""]
    n = 0
    for r in _reportable(report.results):
        if r.timecode is None:
            continue
        n += 1
        start = _vtt_ts(r.timecode)
        end = _vtt_ts(r.timecode + marker_len)
        lines.append(str(n))
        lines.append(f"{start} --> {end}")
        lines.append(f"[{r.rule_id}] {r.message}")
        lines.append("")
    out = "\n".join(lines).rstrip() + "\n"
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(out, encoding="utf-8")
    return out


def export_ad_descriptions_vtt(
    fixes: list[FixResult], output_path: Optional[Path] = None,
    accepted_only: bool = True,
) -> str:
    """Gated AD drafts as a WebVTT descriptions track, importable into an AD tool.

    Only fixes that passed the full gate (DCMP validator + Granite Guardian +
    fits the gap) are emitted as cues by default, so the exported track is
    safe-to-use, never an unscreened draft.
    """
    lines = [
        "WEBVTT - AccessGate audio description",
        "",
        ("NOTE Gated AD drafts (Granite Vision / watsonx-hosted vision) that "
         "passed the self-built DCMP structure validator and the Granite "
         "Guardian safety screen. Import into your audio-description track."),
        "",
    ]
    n = 0
    for fix in fixes:
        if accepted_only and not fix.accepted:
            continue
        n += 1
        start = _vtt_ts(fix.gap.start)
        end = _vtt_ts(fix.gap.end)
        lines.append(str(n))
        lines.append(f"{start} --> {end}")
        lines.append(fix.draft_text.strip().replace("\n", " "))
        lines.append("")
    out = "\n".join(lines).rstrip() + "\n"
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(out, encoding="utf-8")
    return out


def export_editor_bundle(
    report: ConformanceReport, output_dir: Path, stem: str,
    fixes: Optional[list[FixResult]] = None,
) -> dict[str, Path]:
    """Write the report-derived editor exports (and AD track if fixes given)."""
    output_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}
    csv_path = output_dir / f"{stem}_findings.csv"
    export_findings_csv(report, csv_path)
    written["findings_csv"] = csv_path
    markers_path = output_dir / f"{stem}_markers.vtt"
    export_findings_markers_vtt(report, markers_path)
    written["markers_vtt"] = markers_path
    if fixes:
        desc_path = output_dir / f"{stem}_descriptions.vtt"
        export_ad_descriptions_vtt(fixes, desc_path)
        written["descriptions_vtt"] = desc_path
    return written
