"""
Plain-English report summary via watsonx Granite (granite-3-8b-instruct).

Turns a conformance report into a two-to-three sentence executive summary a
post-production supervisor can act on. This is the Granite LANGUAGE model in the
stack (distinct from Granite Vision/Guardian and Granite Speech): it reasons
over the structured findings, it does not invent them. Gracefully returns an
error string if watsonx is not configured, so callers can omit the summary.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import requests

from src.watsonx_showcase import _iam_token, _DEFAULT_URL

logger = logging.getLogger(__name__)

MODEL_ID = "ibm/granite-3-8b-instruct"
_GENERATE_PATH = "/ml/v1/text/generation?version=2023-05-29"


def summarize_report(
    report: dict,
    *,
    api_key: Optional[str] = None,
    project_id: Optional[str] = None,
    base_url: Optional[str] = None,
) -> dict:
    """Return {summary, model_id, source, error} for a conformance report dict."""
    api_key = api_key or os.getenv("WATSONX_API_KEY", "")
    project_id = project_id or os.getenv("WATSONX_PROJECT", "")
    base_url = (base_url or os.getenv("WATSONX_URL", _DEFAULT_URL)).rstrip("/")

    result = {
        "summary": "",
        "model_id": MODEL_ID,
        "source": "watsonx Granite 3 8B Instruct",
        "error": None,
    }
    if not api_key or not project_id:
        result["error"] = "WATSONX_API_KEY or WATSONX_PROJECT not set"
        return result

    # Build a compact, factual brief for the model from the real findings.
    results = report.get("results", [])
    fails = [r for r in results if r.get("status") == "fail"]
    flags = [r for r in results if r.get("status") == "flag"]
    top = "; ".join(r.get("message", "")[:100] for r in (fails + flags)[:6])
    ner = report.get("ner") or {}
    ner_line = (
        f"NER caption accuracy {ner['ner_score'] * 100:.1f}% (below the 98% broadcast threshold, "
        f"flagged for human review not auto-failed)." if ner else "No caption-accuracy score."
    )
    brief = (
        f"Profile: {report.get('profile', 'netflix')}. "
        f"{report.get('error_count', 0)} errors, {report.get('warning_count', 0)} warnings, "
        f"{report.get('flag_count', 0)} human-review flags across FCC, WCAG, DCMP and Netflix rules. "
        f"{len(report.get('gaps', []))} dialogue-free gaps need audio description. "
        f"{ner_line} Key findings: {top}"
    )
    prompt = (
        "You are an accessibility QC lead briefing a post-production supervisor. "
        "In two or three plain sentences, summarize what must be fixed before this "
        "film can ship accessibly, and note that the accuracy score is flagged for "
        "human review rather than an automatic fail. Do not invent findings beyond "
        "the brief. Be direct and specific.\n\n"
        f"Brief: {brief}\n\nSummary:"
    )

    try:
        token = _iam_token(api_key)
        resp = requests.post(
            base_url + _GENERATE_PATH,
            json={
                "model_id": MODEL_ID,
                "project_id": project_id,
                "input": prompt,
                "parameters": {"decoding_method": "greedy", "max_new_tokens": 160, "repetition_penalty": 1.1},
            },
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=30,
        )
        resp.raise_for_status()
        result["summary"] = resp.json()["results"][0]["generated_text"].strip()
        logger.info("Granite report summary generated (%d chars).", len(result["summary"]))
    except Exception as exc:  # noqa: BLE001
        result["error"] = str(exc)
        logger.warning("Granite report summary failed: %s", exc)

    return result
