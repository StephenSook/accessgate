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
    ner_score = ner.get("ner_score")
    if ner_score is None:
        ner_line = "No caption-accuracy score."
    else:
        rel = "below" if ner_score < 0.98 else "at or above"
        ner_line = (
            f"NER caption accuracy {ner_score * 100:.1f}% ({rel} the 98% broadcast threshold; "
            f"reference-relative and flagged for human review, never auto-failed)."
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
        result["unsupported_figures"] = unsupported_figures(result["summary"], brief)
        logger.info("Granite report summary generated (%d chars).", len(result["summary"]))
        if result["unsupported_figures"]:
            logger.warning(
                "Report summary states figures absent from the brief: %s",
                result["unsupported_figures"],
            )
    except Exception as exc:  # noqa: BLE001
        result["error"] = str(exc)
        logger.warning("Granite report summary failed: %s", exc)

    return result


def unsupported_figures(summary: str, brief: str) -> list[str]:
    """
    Numbers the summary states that the brief never supplied.

    This is the one place in AccessGate where a model is asked to restate
    figures the engine computed, so it is the one place a figure could drift.
    The prompt already says not to invent findings; this checks rather than
    trusts, because "we told it not to" is not evidence that it did not.

    It reports, it does not rewrite. A summary is prose, so silently editing a
    number inside it would produce a sentence no model wrote and no human
    approved. Surfacing the discrepancy keeps the honest failure visible, which
    is the same reason a fallback draft here is marked rather than hidden.

    Deliberately permissive, because a false accusation is worse than a miss:
    a figure counts as supported if its digits appear anywhere in the brief, so
    "78.9%" is covered by the brief's "78.9", and ordinary prose numbers ("two
    or three sentences", "1 gap") never trip it.
    """
    import re

    # Digit runs, keeping decimals together. Strip trailing zeros so 78.90
    # and 78.9 compare equal.
    def norm(tok: str) -> str:
        return tok.rstrip("0").rstrip(".") if "." in tok else tok

    brief_tokens = {norm(t) for t in re.findall(r"\d+(?:\.\d+)?", brief)}
    # Small integers are ordinary English ("two or three", "1 gap") and the
    # threshold constants are stated in the prompt itself.
    always_ok = {"0", "1", "2", "3", "4", "5", "98", "100"}

    out: list[str] = []
    for tok in re.findall(r"\d+(?:\.\d+)?", summary or ""):
        n = norm(tok)
        if n in brief_tokens or n in always_ok or n in out:
            continue
        out.append(n)
    return out
