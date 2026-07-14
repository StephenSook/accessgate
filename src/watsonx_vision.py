"""
watsonx-hosted vision drafting for the AccessGate generative fix.

Granite Vision 3.2 (local Ollama) is the primary drafter and the
API-deletion-proof path. On the hosted deployment there is no Ollama, so the
vision step runs on IBM watsonx instead, letting a judge trigger the gap fix
live on any uploaded clip without installing models. watsonx.ai in us-south
serves Llama 3.2 Vision (Meta) for multimodal image_chat; the local pipeline
keeps Granite Vision. This module is the watsonx path; it is clearly labeled as
such wherever its output surfaces (see /judges).

Verified against the watsonx chat API: POST /ml/v1/text/chat with a user
message whose content mixes a text part and image_url data-URI parts.
"""
from __future__ import annotations

import base64
import logging
import os
from typing import Optional

import requests

from src.watsonx_showcase import _iam_token, _DEFAULT_URL

logger = logging.getLogger(__name__)

MODEL_ID = "meta-llama/llama-3-2-11b-vision-instruct"
_CHAT_PATH = "/ml/v1/text/chat?version=2024-09-16"


def draft_from_keyframes(
    keyframe_paths: list[str],
    gap_start: float,
    gap_end: float,
    *,
    api_key: Optional[str] = None,
    project_id: Optional[str] = None,
    base_url: Optional[str] = None,
) -> dict:
    """
    Draft an audio-description line from film keyframes via watsonx vision.

    Returns a dict: {model_id, source, generated_text, error}. On any failure,
    generated_text is empty and error is set so the caller can fall back.
    """
    api_key = api_key or os.getenv("WATSONX_API_KEY", "")
    project_id = project_id or os.getenv("WATSONX_PROJECT", "")
    base_url = (base_url or os.getenv("WATSONX_URL", _DEFAULT_URL)).rstrip("/")

    duration = round(gap_end - gap_start, 1)
    max_words = max(4, int(duration / 60 * 150))  # 150 wpm AD cap
    result = {
        "model_id": MODEL_ID,
        "source": "watsonx-hosted Llama 3.2 Vision",
        "generated_text": "",
        "error": None,
    }

    if not api_key or not project_id or not keyframe_paths:
        result["error"] = "watsonx vision: missing api key, project, or keyframes"
        return result

    content = [{
        "type": "text",
        "text": (
            f"You are writing audio description for a blind film viewer. Describe what "
            f"happens in this {duration:.0f}-second dialogue-free moment in ONE sentence: "
            f"present tense, active voice, third person, objective, no more than {max_words} "
            f"words. Do not mention 'image', 'photo', 'frame', 'scene', or 'black-and-white'. "
            f"Describe the action and setting directly. Return only the description."
        ),
    }]
    # Llama 3.2 Vision accepts at most one image per prompt; use the middle
    # keyframe of the gap.
    mid = keyframe_paths[len(keyframe_paths) // 2]
    try:
        with open(mid, "rb") as f:
            img = base64.b64encode(f.read()).decode()
        content.append({"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + img}})
    except Exception as exc:  # noqa: BLE001
        result["error"] = f"keyframe read failed: {exc}"
        return result

    payload = {
        "model_id": MODEL_ID,
        "project_id": project_id,
        "messages": [{"role": "user", "content": content}],
        "max_tokens": 80,
        "temperature": 0.2,
    }
    try:
        token = _iam_token(api_key)
        resp = requests.post(
            base_url + _CHAT_PATH,
            json=payload,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=60,
        )
        resp.raise_for_status()
        text = resp.json()["choices"][0]["message"]["content"].strip().strip('"').strip()
        result["generated_text"] = text
        logger.info("watsonx vision drafted %d-word AD for gap %.1f-%.1fs", len(text.split()), gap_start, gap_end)
    except Exception as exc:  # noqa: BLE001
        result["error"] = str(exc)
        logger.warning("watsonx vision draft failed: %s", exc)

    return result
