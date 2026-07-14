"""
OSCAL POA&M v1.1.2 exporter for AccessGate.

Produces a minimal valid OSCAL Plan of Action and Milestones document
for each failed rule in the ConformanceReport.

Schema: https://pages.nist.gov/OSCAL/reference/1.1.2/plan-of-action-and-milestones/
"""
from __future__ import annotations
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from src.models import ConformanceReport


def export_oscal(report: ConformanceReport, output_path: Path | None = None) -> dict:
    """
    Convert a ConformanceReport to an OSCAL POA&M v1.1.2 document.

    Returns the OSCAL dict. If output_path is given, writes to disk.
    """
    now = datetime.now(timezone.utc).isoformat()
    doc_uuid = str(uuid.uuid4())

    # Build POA&M items for failed and flagged results only
    poam_items = []
    for i, result in enumerate(report.results):
        if result.status not in ("fail", "flag"):
            continue

        item_uuid = str(uuid.uuid4())
        risk_uuid = str(uuid.uuid4())
        obs_uuid = str(uuid.uuid4())

        poam_items.append({
            "uuid": item_uuid,
            "title": f"{result.rule_id}: {result.status.upper()}",
            "description": result.message,
            "props": [
                {"name": "rule-id", "value": result.rule_id},
                {"name": "status", "value": result.status},
                {"name": "sarif-level", "value": result.sarif_level},
                {"name": "citation", "value": result.citation or ""},
                {"name": "timecode",
                 "value": str(result.timecode) if result.timecode is not None else ""},
                {"name": "human-review-required",
                 "value": str(result.human_review_required).lower()},
            ],
            "related-observations": [{"observation-uuid": obs_uuid}],
            "associated-risks": [{"risk-uuid": risk_uuid}],
        })

    # Observations section
    observations = []
    risks = []
    for item in poam_items:
        obs_uuid = item["related-observations"][0]["observation-uuid"]
        risk_uuid = item["associated-risks"][0]["risk-uuid"]
        title = item["title"]

        observations.append({
            "uuid": obs_uuid,
            "title": f"Observation: {title}",
            "description": next(
                (p["value"] for p in item["props"] if p["name"] == "citation"), ""
            ),
            "collected": now,
            "relevant-evidence": [
                {
                    "description": f"Detected by AccessGate conformance engine. {item['description'][:200]}"
                }
            ],
        })

        risks.append({
            "uuid": risk_uuid,
            "title": f"Risk: {title}",
            "description": item["description"],
            "statement": (
                "This non-conformance may prevent viewers with disabilities "
                "from accessing the program content as required by applicable standards."
            ),
            "status": "open",
            "characterizations": [
                {
                    "facets": [
                        {"name": "likelihood", "system": "https://accessgate.local/scoring", "value": "likely"},
                        {"name": "impact", "system": "https://accessgate.local/scoring", "value": "high"},
                    ]
                }
            ],
        })

    oscal_doc = {
        "plan-of-action-and-milestones": {
            "uuid": doc_uuid,
            "metadata": {
                "title": "AccessGate Conformance Pre-Check POA&M",
                "last-modified": now,
                "version": "1.0.0",
                "oscal-version": "1.1.2",
                "props": [
                    {"name": "film", "value": report.film_path},
                    {"name": "captions", "value": report.caption_path},
                    {"name": "profile", "value": report.profile},
                    {"name": "total-results", "value": str(len(report.results))},
                    {"name": "error-count", "value": str(report.error_count)},
                    {"name": "warning-count", "value": str(report.warning_count)},
                    {"name": "flag-count", "value": str(report.flag_count)},
                ],
            },
            "import-ssp": {
                "href": "#",
                "remarks": "AccessGate self-attested system description.",
            },
            "system-id": {
                "identifier-type": "https://accessgate.local/system",
                "id": "accessgate-conformance-engine",
            },
            "poam-items": poam_items,
            "observations": observations,
            "risks": risks,
        }
    }

    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(oscal_doc, f, indent=2)

    return oscal_doc
