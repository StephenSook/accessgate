"""
watsonx-hosted content-safety screen for the AccessGate generative fix.

Granite Guardian 3 2b (local Ollama) is the primary safety screen and the
API-deletion-proof path. On the hosted deployment there is no Ollama, so the
screen runs on IBM watsonx instead, using ibm/granite-guardian-3-8b — the same
Granite Guardian model family, hosted. This keeps the safety gate genuinely
wired on the judge-facing deploy rather than silently skipped.

Granite Guardian answers a risk question with "Yes" (risk present) or "No"
(no risk). We ask the harm/HAP risk and treat "No" as cleared.

Environment: WATSONX_API_KEY, WATSONX_PROJECT, WATSONX_URL (see watsonx_showcase).
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import requests

from src.watsonx_showcase import _iam_token, _DEFAULT_URL

logger = logging.getLogger(__name__)

MODEL_ID = "ibm/granite-guardian-3-8b"
_CHAT_PATH = "/ml/v1/text/chat?version=2024-09-16"


def screen_guardian_watsonx(
    draft: str,
    *,
    api_key: Optional[str] = None,
    project_id: Optional[str] = None,
    base_url: Optional[str] = None,
) -> dict:
    """
    Screen an audio-description draft for content safety via watsonx Granite
    Guardian.

    Returns a dict:
      cleared : bool   — True only if Guardian actually ran and found no risk
      ran     : bool   — True only if the model returned a parseable verdict
      reason  : str    — the model's raw verdict / risk note (empty when cleared)
      source  : str    — "Granite Guardian 3 8b (watsonx.ai)"
      error   : str|None
    """
    api_key = api_key or os.getenv("WATSONX_API_KEY", "")
    project_id = project_id or os.getenv("WATSONX_PROJECT", "")
    base_url = (base_url or os.getenv("WATSONX_URL", _DEFAULT_URL)).rstrip("/")

    result = {
        "cleared": False,
        "ran": False,
        "reason": "",
        "source": "Granite Guardian 3 8b (watsonx.ai)",
        "error": None,
    }

    if not api_key or not project_id:
        result["error"] = "WATSONX_API_KEY or WATSONX_PROJECT not set"
        result["reason"] = "Guardian did not run (watsonx not configured)"
        return result

    # Granite Guardian classifies the risk of a message directly. Sent through
    # the chat endpoint it answers "No" (no risk) or "Yes" (risk present).
    try:
        token = _iam_token(api_key)
        payload = {
            "model_id": MODEL_ID,
            "project_id": project_id,
            "messages": [{"role": "user", "content": draft}],
            "max_tokens": 5,
        }
        resp = requests.post(
            base_url + _CHAT_PATH,
            json=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=30,
        )
        resp.raise_for_status()
        verdict = resp.json()["choices"][0]["message"]["content"].strip()
        low = verdict.lower()
        # "No" => no risk => cleared. Anything starting with "yes" => risk.
        if low.startswith("no"):
            result["cleared"] = True
            result["ran"] = True
        elif low.startswith("yes"):
            result["cleared"] = False
            result["ran"] = True
            result["reason"] = f"Guardian flagged risk: {verdict}"
        else:
            # Unparseable verdict — do not claim it ran clean.
            result["ran"] = False
            result["reason"] = f"Guardian returned an unparseable verdict: {verdict!r}"
        logger.info("watsonx Guardian verdict for draft: %r -> cleared=%s", verdict, result["cleared"])
    except Exception as exc:  # noqa: BLE001
        result["error"] = str(exc)
        result["reason"] = f"Guardian could not run: {exc}"
        logger.warning("watsonx Guardian call failed: %s", exc)

    return result
