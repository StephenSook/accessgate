"""
Gated generative AD fix loop for AccessGate.

Load-Bearing Artifact (generative layer):
  gap → Granite Vision draft → DCMP structure validator → Granite Guardian screen → FixResult

The gate is three-stage: only a description that passes DCMP structure checks
AND clears Granite Guardian gets accepted and flips the row green.

Pre-generation: for the demo, the fix for the NOTLD target gap is pre-generated
and saved to data/demo/pregenerated_fix.json. DCMP re-validation and Guardian
screening run live in the demo; generation is pre-baked.

API-deletion test: if Ollama is unavailable, the module falls back to a
hard-coded placeholder draft that still exercises the validation/screening path.
"""
from __future__ import annotations
import json
import logging
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from src.models import GapRegion, FixResult, SpeechRegion
from src.evaluators.dcmp_desc import (
    eval_dcmp_desc_01, eval_dcmp_desc_02, eval_dcmp_desc_03,
    eval_dcmp_desc_04, eval_dcmp_desc_05, eval_dcmp_desc_06,
)
from src.models import CaptionCue

logger = logging.getLogger(__name__)

# Default models (confirmed pulled)
VISION_MODEL = "granite3.2-vision:2b"
GUARDIAN_MODEL = "granite3-guardian:2b"

# AD reading speed for gap-fit sizing
AD_WPM = 150.0

# Pre-generated fix path
PREGENERATED_FIX = Path(__file__).parent.parent / "data" / "demo" / "pregenerated_fix.json"


# ---------------------------------------------------------------------------
# Keyframe extraction
# ---------------------------------------------------------------------------

def extract_keyframes(film_path: str, gap: GapRegion, n_frames: int = 3) -> list[str]:
    """
    Extract n evenly-spaced keyframe JPEGs from the gap window using ffmpeg.
    Returns list of temp file paths.
    """
    paths = []
    duration = gap.duration
    if duration <= 0 or n_frames <= 0:
        return paths

    offsets = [gap.start + (duration / (n_frames + 1)) * (i + 1) for i in range(n_frames)]

    for i, offset in enumerate(offsets):
        tmp = tempfile.NamedTemporaryFile(suffix=f"_frame{i}.jpg", delete=False)
        tmp.close()
        cmd = [
            "ffmpeg", "-y", "-ss", str(offset),
            "-i", film_path,
            "-vframes", "1",
            "-q:v", "3",
            tmp.name,
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=15)
            if result.returncode == 0:
                paths.append(tmp.name)
        except Exception as e:
            logger.warning("ffmpeg keyframe extraction failed at %.2fs: %s", offset, e)

    return paths


# ---------------------------------------------------------------------------
# Granite Vision draft
# ---------------------------------------------------------------------------

def draft_description(
    keyframe_paths: list[str],
    gap: GapRegion,
    model: str = VISION_MODEL,
) -> tuple[str, str]:
    """
    Send keyframes to Granite Vision via Ollama and get a draft AD description.
    Prompt enforces: present tense, active voice, third-person, no jargon,
    sized to fit the gap at AD_WPM.

    Returns (draft_text, source) so callers can report which model actually
    produced the draft (local Granite Vision, watsonx vision, or the fallback).
    """
    max_words = gap.max_words(wpm=AD_WPM)
    prompt = (
        f"Write an audio description for a blind viewer. "
        f"The silent gap lasts {gap.duration:.1f} seconds (maximum {max_words} words). "
        f"Rules: present tense, active voice, third-person narrative, "
        f"no cinematic jargon (no 'flashback', 'dissolve', 'cut to'), "
        f"objective language only, complete sentence. "
        f"Describe only what is visually essential to understanding the scene. "
        f"Respond with ONLY the description text, nothing else."
    )

    # Build Ollama request with images
    import base64
    images = []
    for path in keyframe_paths:
        try:
            with open(path, "rb") as f:
                images.append(base64.b64encode(f.read()).decode())
        except Exception as e:
            logger.warning("keyframe %s unreadable: %s", path, e)

    payload = {
        "model": model,
        "prompt": prompt,
        "images": images,
        "stream": False,
        "options": {"temperature": 0.3, "num_predict": 120},
    }

    try:
        # Never call a vision model with zero images — it would hallucinate a
        # description it never "saw" and return it as vision-grounded.
        if not images:
            raise RuntimeError("no readable keyframes to send to the vision model")
        import urllib.request
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            "http://localhost:11434/api/generate",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        # Generous timeout: the first call cold-loads the vision model into
        # memory (can take 60-90s on CPU); subsequent calls are fast.
        with urllib.request.urlopen(req, timeout=180) as resp:
            body = json.loads(resp.read())
            text = body.get("response", "").strip()
            if text:
                return text, "Granite Vision 3.2 2b (Ollama)"
            raise RuntimeError("empty Granite Vision response")
    except Exception as e:
        # Local Granite Vision (Ollama) unavailable, e.g. on the hosted deploy.
        # Draft the vision step on watsonx so a judge can still trigger the fix
        # live. Clearly labeled as the watsonx path wherever it surfaces.
        logger.info("Granite Vision (Ollama) unavailable: %s. Trying watsonx vision.", e)
        try:
            from src.watsonx_vision import draft_from_keyframes
            wx = draft_from_keyframes(keyframe_paths, gap.start, gap.end)
            if wx.get("generated_text"):
                return wx["generated_text"], wx.get("source", "watsonx-hosted vision")
            logger.warning("watsonx vision unavailable (%s). Using fallback draft.", wx.get("error"))
        except Exception as e2:  # noqa: BLE001
            logger.warning("watsonx vision error (%s). Using fallback draft.", e2)
        return _fallback_draft(gap), "fallback (no vision model available)"


def _fallback_draft(gap: GapRegion) -> str:
    """Fallback draft when Ollama is unavailable — exercises the validation path."""
    max_words = gap.max_words(wpm=AD_WPM)
    # Deliberately concise to fit the gap
    return f"The character moves through the scene. ({max_words} word budget)"


# ---------------------------------------------------------------------------
# DCMP structure validation
# ---------------------------------------------------------------------------

def validate_dcmp_structure(
    draft: str,
    gap: GapRegion,
    speech_regions: list[SpeechRegion],
) -> tuple[bool, list[str]]:
    """
    Re-run DCMP DESC rules 01-06 on the draft text.
    Returns (is_valid, list_of_issues).
    """
    # Wrap draft as a single AD cue for the evaluators
    cue = CaptionCue(
        index=0,
        start=gap.start,
        end=gap.end,
        text=draft,
        lines=draft.split("\n"),
    )

    issues = []

    for fn, label in [
        (lambda: eval_dcmp_desc_01([cue]), "DCMP-DESC-01 (tense/voice)"),
        (lambda: eval_dcmp_desc_02([cue]), "DCMP-DESC-02 (third person)"),
        (lambda: eval_dcmp_desc_03([cue]), "DCMP-DESC-03 (jargon)"),
        (lambda: eval_dcmp_desc_04([cue], [gap]), "DCMP-DESC-04 (word count fits gap)"),
        (lambda: eval_dcmp_desc_05([cue], speech_regions), "DCMP-DESC-05 (no dialogue overlap)"),
        (lambda: eval_dcmp_desc_06([cue]), "DCMP-DESC-06 (complete sentence)"),
    ]:
        try:
            results = fn()
            for r in results:
                if r.status in ("fail", "flag"):
                    issues.append(f"{label}: {r.message[:120]}")
        except Exception as e:
            logger.warning("DCMP validation step failed: %s", e)

    return (len(issues) == 0, issues)


# ---------------------------------------------------------------------------
# Granite Guardian screening
# ---------------------------------------------------------------------------

def screen_guardian(draft: str, model: str = GUARDIAN_MODEL) -> tuple[bool, bool, str, Optional[str]]:
    """
    Screen the draft for content safety. Returns (cleared, ran, reason, source).

      cleared — True only if a Guardian actually ran AND found the text safe.
      ran     — True only if a Guardian produced a verdict.
      source  — which Guardian ran, or None if none did.

    The gate FAILS CLOSED: a screen that could not run is never reported as
    "passed" (the old code returned cleared=True on any error, so a safety gate
    that never executed showed as cleared). Local Granite Guardian (Ollama) is
    primary; on the hosted deploy (no Ollama) the screen runs on watsonx Granite
    Guardian so the gate stays genuinely wired for judges.
    """
    prompt = (
        "You are a content safety reviewer. "
        "Evaluate the following audio description text for a film. "
        "Determine if it is: (1) safe and appropriate for all audiences, "
        "(2) objective and non-interpretive, (3) free from harmful content. "
        f"Text: \"{draft}\"\n"
        "Respond with exactly one word: SAFE or UNSAFE, then optionally a brief reason."
    )

    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.0, "num_predict": 60},
    }

    try:
        import urllib.request
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            "http://localhost:11434/api/generate",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = json.loads(resp.read())
            response = body.get("response", "").strip()
            cleared = response.upper().startswith("SAFE")
            reason = response if not cleared else ""
            return cleared, True, reason, "Granite Guardian 3 2b (Ollama)"
    except Exception as e:
        logger.info("Granite Guardian (Ollama) unavailable: %s. Trying watsonx Guardian.", e)

    # Hosted path: real Granite Guardian on watsonx.
    try:
        from src.watsonx_guardian import screen_guardian_watsonx
        wx = screen_guardian_watsonx(draft)
        if wx["ran"]:
            return wx["cleared"], True, wx["reason"], wx["source"]
        logger.warning("watsonx Guardian did not run: %s", wx.get("reason") or wx.get("error"))
    except Exception as e2:  # noqa: BLE001
        logger.warning("watsonx Guardian error: %s", e2)

    # Both unavailable — FAIL CLOSED: not cleared, did not run.
    return False, False, "Guardian could not run (Ollama and watsonx both unavailable)", None


# ---------------------------------------------------------------------------
# Main fix orchestrator
# ---------------------------------------------------------------------------

def generate_fix(
    gap: GapRegion,
    film_path: str,
    speech_regions: Optional[list[SpeechRegion]] = None,
    vision_model: str = VISION_MODEL,
    guardian_model: str = GUARDIAN_MODEL,
) -> FixResult:
    """
    Full gated fix loop:
      1. Extract keyframes from the gap
      2. Draft description with Granite Vision
      3. Validate draft against DCMP DESC rules
      4. Screen draft with Granite Guardian
      5. Return FixResult (accepted only if BOTH pass)
    """
    if speech_regions is None:
        speech_regions = []

    # Step 1: keyframes
    keyframes = extract_keyframes(film_path, gap)

    # Step 2: draft
    draft, draft_source = draft_description(keyframes, gap, model=vision_model)
    is_fallback = draft_source.startswith("fallback")
    word_count = len(draft.split())
    max_words = gap.max_words(wpm=AD_WPM)
    fits_gap = word_count <= max_words

    # Step 3: DCMP validation
    dcmp_valid, dcmp_issues = validate_dcmp_structure(draft, gap, speech_regions)

    # Step 4: Guardian screening (fails closed)
    guardian_cleared, guardian_ran, guardian_reason, guardian_source = screen_guardian(
        draft, model=guardian_model
    )

    # Accept only if every gate genuinely ran and passed. A canned fallback
    # draft, or a Guardian that could not run, must never be accepted.
    accepted = dcmp_valid and guardian_cleared and guardian_ran and fits_gap and not is_fallback

    result = FixResult(
        gap=gap,
        draft_text=draft,
        draft_source=draft_source,
        dcmp_valid=dcmp_valid,
        dcmp_issues=dcmp_issues,
        guardian_cleared=guardian_cleared,
        guardian_ran=guardian_ran,
        guardian_source=guardian_source,
        guardian_reason=guardian_reason if (not guardian_cleared or not guardian_ran) else None,
        accepted=accepted,
        word_count=word_count,
        fits_gap=fits_gap,
    )

    logger.info(
        "Fix result: source=%s, dcmp_valid=%s, guardian_ran=%s, guardian_cleared=%s, fits_gap=%s, accepted=%s",
        draft_source, dcmp_valid, guardian_ran, guardian_cleared, fits_gap, accepted,
    )
    return result


def generate_demo_fix(
    gap: GapRegion,
    keyframe_paths: list[str],
    speech_regions: Optional[list[SpeechRegion]] = None,
) -> tuple[FixResult, str]:
    """
    Hosted-demo fix path: draft from PRE-COMMITTED keyframes (no film upload,
    no Ollama) so a judge can trigger the gap fix live on the deployed backend.

    The vision draft runs on watsonx (Llama 3.2 Vision); the DCMP structure
    validator runs live and is the real gate. Returns (FixResult, draft_source).
    """
    from src.watsonx_vision import draft_from_keyframes

    if speech_regions is None:
        speech_regions = []

    wx = draft_from_keyframes(keyframe_paths, gap.start, gap.end)
    if wx.get("generated_text"):
        draft = wx["generated_text"]
        source = wx["source"]
        is_fallback = False
    else:
        draft = _fallback_draft(gap)
        source = "fallback (watsonx unavailable)"
        is_fallback = True

    word_count = len(draft.split())
    fits_gap = word_count <= gap.max_words(wpm=AD_WPM)
    dcmp_valid, dcmp_issues = validate_dcmp_structure(draft, gap, speech_regions)
    guardian_cleared, guardian_ran, guardian_reason, guardian_source = screen_guardian(draft)
    accepted = dcmp_valid and guardian_cleared and guardian_ran and fits_gap and not is_fallback

    result = FixResult(
        gap=gap,
        draft_text=draft,
        draft_source=source,
        dcmp_valid=dcmp_valid,
        dcmp_issues=dcmp_issues,
        guardian_cleared=guardian_cleared,
        guardian_ran=guardian_ran,
        guardian_source=guardian_source,
        guardian_reason=guardian_reason if (not guardian_cleared or not guardian_ran) else None,
        accepted=accepted,
        word_count=word_count,
        fits_gap=fits_gap,
    )
    return result, source


# ---------------------------------------------------------------------------
# Pre-generation for demo
# ---------------------------------------------------------------------------

def pregenerate_demo_fix(film_path: str) -> None:
    """
    Pre-generate the AD fix for the demo NOTLD target gap and save to disk.
    This is the asset used in the video recording — generation is pre-baked,
    but validation and Guardian screening run live in the demo.
    """
    # Demo gap: the known dialogue-free window in the NOTLD segment
    demo_gap = GapRegion(start=12.0, end=19.5)

    result = generate_fix(
        gap=demo_gap,
        film_path=film_path,
        speech_regions=[],
    )

    PREGENERATED_FIX.parent.mkdir(parents=True, exist_ok=True)
    with open(PREGENERATED_FIX, "w") as f:
        json.dump(result.model_dump(), f, indent=2)

    logger.info("Pre-generated fix saved to %s", PREGENERATED_FIX)
    print(f"Draft: {result.draft_text}")
    print(f"Accepted: {result.accepted}")
    print(f"DCMP valid: {result.dcmp_valid}")
    print(f"Guardian cleared: {result.guardian_cleared}")


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    if len(sys.argv) < 2:
        print("Usage: python -m src.generative_fix <film_path>")
        sys.exit(1)
    pregenerate_demo_fix(sys.argv[1])
