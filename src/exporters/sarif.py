"""
SARIF 2.1.0 exporter for AccessGate.

Schema: https://docs.oasis-open.org/sarif/sarif/v2.1.0/errata01/os/schemas/sarif-schema-2.1.0.json

Critical: timecodes go in result.properties, NOT in region fields.
Region requires startLine, charOffset, or byteOffset per OASIS SARIF 2.1.0 Errata 01.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from src.models import ConformanceReport, RuleResult
from src.registry import all_rules

SARIF_SCHEMA = (
    "https://docs.oasis-open.org/sarif/sarif/v2.1.0/errata01/os/"
    "schemas/sarif-schema-2.1.0.json"
)

_SARIF_LEVEL_MAP = {
    "error": "error",
    "warning": "warning",
    "note": "note",
}

_STATUS_LEVEL_MAP = {
    "fail": None,       # use sarif_level from rule
    "flag": "note",     # flags are always notes
    "pass": "none",     # pass = suppressed result
    "skip": "none",
}


def export_sarif(report: ConformanceReport, output_path: Path | None = None) -> dict:
    """
    Convert a ConformanceReport to a SARIF 2.1.0 document.

    Returns the SARIF dict. If output_path is given, writes to disk.
    """
    # Build the tool.driver.rules array from the full registry
    rules = all_rules()
    driver_rules = []
    for rule in rules:
        driver_rules.append({
            "id": rule.id,
            "name": _rule_id_to_name(rule.id),
            "shortDescription": {"text": rule.logic},
            "helpUri": _source_to_uri(rule.source),
            "properties": {
                "check_type": rule.check_type,
                "sarif_level": rule.sarif_level,
                "source": rule.source,
            },
        })

    # Build results
    sarif_results = []
    for result in report.results:
        if result.status in ("pass", "skip"):
            continue  # only emit failures and flags

        level = _STATUS_LEVEL_MAP.get(result.status)
        if level is None:
            # Use the rule's sarif_level for actual failures
            level = _SARIF_LEVEL_MAP.get(result.sarif_level, "warning")
        if level == "none":
            continue

        sarif_result: dict = {
            "ruleId": result.rule_id,
            "level": level,
            "message": {"text": result.message},
            "locations": [
                {
                    "logicalLocations": [
                        {
                            "name": report.film_path,
                            "kind": "module",
                        }
                    ]
                }
            ],
            "properties": {},
        }

        # Timecodes go in properties, NOT in region fields
        if result.timecode is not None:
            sarif_result["properties"]["timecode"] = result.timecode
            sarif_result["properties"]["timecode_human"] = _seconds_to_hmsf(result.timecode)

        # Add citation and confidence
        if result.citation:
            sarif_result["properties"]["citation"] = result.citation
        if result.confidence is not None:
            sarif_result["properties"]["confidence"] = round(result.confidence, 4)
        if result.human_review_required:
            sarif_result["properties"]["humanReviewRequired"] = True

        sarif_results.append(sarif_result)

    sarif_doc = {
        "$schema": SARIF_SCHEMA,
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "AccessGate",
                        "informationUri": "https://github.com/stephensookra/accessgate",
                        "version": "1.0.0",
                        "rules": driver_rules,
                    }
                },
                "artifacts": [
                    {"location": {"uri": report.film_path}},
                    {"location": {"uri": report.caption_path}},
                ],
                "results": sarif_results,
                "invocations": [
                    {
                        "executionSuccessful": True,
                        "endTimeUtc": datetime.now(timezone.utc).isoformat(),
                    }
                ],
                "properties": {
                    "profile": report.profile,
                    "ner_score": report.ner.ner_score if report.ner else None,
                    "ner_band_low": report.ner.band_low if report.ner else None,
                    "ner_band_high": report.ner.band_high if report.ner else None,
                    "gap_count": len(report.gaps),
                    "total_errors": report.error_count,
                    "total_warnings": report.warning_count,
                    "total_flags": report.flag_count,
                },
            }
        ],
    }

    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(sarif_doc, f, indent=2)

    return sarif_doc


def _rule_id_to_name(rule_id: str) -> str:
    """Convert DCMP-CAP-01 → DcmpCap01 for camelCase SARIF name."""
    return "".join(part.capitalize() for part in rule_id.replace("-", "_").split("_"))


def _source_to_uri(source: str) -> str:
    if "WCAG" in source:
        return "https://www.w3.org/TR/WCAG22/"
    if "47 CFR" in source or "FCC" in source:
        return "https://www.ecfr.gov/current/title-47/chapter-I/subchapter-C/part-79"
    if "DCMP" in source:
        return "https://dcmp.org/learn/captioningkey"
    if "Netflix" in source:
        return "https://partnerhelp.netflixstudios.com/hc/en-us/articles/215758617"
    return ""


def _seconds_to_hmsf(seconds: float) -> str:
    """Convert float seconds to HH:MM:SS.mmm string."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"
