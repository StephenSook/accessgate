"""
watsonx-hosted natural-language intent compiler for the conformance review session.

A reviewer types a plain-English instruction ("dismiss every reading-speed flag
after two minutes as acceptable for this title"). This module asks IBM Granite
(ibm/granite-3-8b-instruct on watsonx.ai) to compile it into a small, STRUCTURED
intent (action + selector), never into free-form commands. The caller
(src/review_session.compile_nl) then re-grounds that intent against the report's
actual findings through the same deterministic selector, so Granite can only ever
narrow the action to findings the engine really produced. It can never invent a
rule id or a timecode.

This is the IBM AI runtime path for the review feature. If no watsonx key is
present (or the call fails) it returns None and the caller falls back to the
deterministic keyword compiler, so the feature runs with no cloud credentials.

Environment: WATSONX_API_KEY, WATSONX_PROJECT, WATSONX_URL (see watsonx_showcase).
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Optional

import requests

from src.watsonx_showcase import _iam_token, _DEFAULT_URL

logger = logging.getLogger(__name__)

MODEL_ID = "ibm/granite-3-8b-instruct"
_CHAT_PATH = "/ml/v1/text/chat?version=2024-09-16"

_SYSTEM = (
    "You compile a reviewer's plain-English instruction about film caption and "
    "audio-description conformance findings into a strict JSON intent. Respond "
    "with ONLY a JSON object, no prose, using exactly these keys:\n"
    '  "action": one of "accept","dismiss","flag","reset","show", or null\n'
    '  "family": one of "DCMP","FCC","WCAG","NFLX", or null\n'
    '  "level":  one of "error","warning","note", or null\n'
    '  "topic":  one of "reading-speed","over-long","duration","description", or null\n'
    '  "after":  a number of seconds, or null (only findings at/after this time)\n'
    '  "before": a number of seconds, or null (only findings at/before this time)\n'
    '  "reason": a short string, or null (why, for a dismiss)\n'
    "Use null for anything the instruction does not specify. Convert m:ss to seconds."
)


def _extract_json(text: str) -> Optional[dict]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?|\n?```$", "", text).strip()
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def compile_intent_watsonx(
    phrase: str,
    *,
    api_key: Optional[str] = None,
    project_id: Optional[str] = None,
    base_url: Optional[str] = None,
) -> Optional[dict]:
    """Compile a phrase to a structured intent dict via watsonx Granite.

    Returns the intent dict, or None if watsonx is not configured or the call
    fails / returns unparseable output (caller falls back to deterministic).
    """
    api_key = api_key or os.getenv("WATSONX_API_KEY", "")
    project_id = project_id or os.getenv("WATSONX_PROJECT", "")
    base_url = (base_url or os.getenv("WATSONX_URL", _DEFAULT_URL)).rstrip("/")

    if not api_key or not project_id:
        return None

    try:
        token = _iam_token(api_key)
        payload = {
            "model_id": MODEL_ID,
            "project_id": project_id,
            "messages": [
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": phrase},
            ],
            "max_tokens": 200,
            "temperature": 0,
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
        content = resp.json()["choices"][0]["message"]["content"]
        intent = _extract_json(content)
        if intent is None:
            logger.warning("watsonx NL intent unparseable: %r", content)
            return None
        logger.info("watsonx NL intent for %r -> %s", phrase, intent)
        return intent
    except Exception as exc:  # noqa: BLE001
        logger.warning("watsonx NL compile failed: %s", exc)
        return None
