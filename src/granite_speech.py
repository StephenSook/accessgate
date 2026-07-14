"""
Granite Speech 3.3-2b reference transcription for AccessGate.

Locked split (AGENTS.md): faster-whisper provides ALL timing and per-word
confidences; Granite Speech 3.3-2b provides the high-accuracy REFERENCE
transcript that feeds the NER caption-accuracy scorer. This module is that
reference source.

Granite Speech is a two-pass speech-language model (ibm-granite/granite-speech
-3.3-2b, Apache 2.0). It is heavy on CPU (~20x realtime), so it is lazy-loaded,
opt-in via ACCESSGATE_GRANITE_SPEECH=1, and chunked. When it is unavailable the
caller falls back to the faster-whisper reference rather than fabricating one.

API verified against the model card (huggingface.co/ibm-granite/granite-speech
-3.3-2b): AutoProcessor + AutoModelForSpeechSeq2Seq, chat template with an
<|audio|> user turn, processor(prompt, wav) -> model.generate -> decode.
"""
from __future__ import annotations

import logging
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

MODEL_ID = "ibm-granite/granite-speech-3.3-2b"
_SYSTEM_PROMPT = (
    "Knowledge Cutoff Date: April 2024.\nToday's Date: April 9, 2025.\n"
    "You are Granite, developed by IBM. You are a helpful AI assistant"
)
_USER_PROMPT = "<|audio|>can you transcribe the speech into a written format?"

# Lazy singletons so the ~6 GB model loads at most once per process.
_processor = None
_tokenizer = None
_model = None


def _load():
    global _processor, _tokenizer, _model
    if _model is not None:
        return _processor, _tokenizer, _model
    import torch  # noqa: F401
    from transformers import AutoProcessor, AutoModelForSpeechSeq2Seq

    _processor = AutoProcessor.from_pretrained(MODEL_ID)
    _tokenizer = _processor.tokenizer
    _model = AutoModelForSpeechSeq2Seq.from_pretrained(MODEL_ID, dtype=torch.bfloat16)
    _model.to("cpu")
    logger.info("Granite Speech %s loaded.", MODEL_ID)
    return _processor, _tokenizer, _model


def _extract_wav(media_path: str) -> str:
    """Extract 16 kHz mono wav from any media file via ffmpeg."""
    if media_path.lower().endswith(".wav"):
        return media_path
    out = Path(tempfile.mkdtemp()) / "audio_16k.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-i", media_path, "-ac", "1", "-ar", "16000", str(out)],
        check=True, capture_output=True,
    )
    return str(out)


def transcribe(media_path: str, chunk_secs: float = 20.0) -> str:
    """
    Transcribe a media file with Granite Speech 3.3-2b, chunked.

    Raises RuntimeError if dependencies or the media are unavailable, so callers
    can fall back to the faster-whisper reference.
    """
    if not media_path or not Path(media_path).exists():
        raise RuntimeError(f"Granite Speech: media not found: {media_path!r}")
    try:
        import torch
        import numpy as np
        import soundfile as sf
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"Granite Speech deps unavailable: {e}") from e

    wav_path = _extract_wav(media_path)
    data, sr = sf.read(wav_path, dtype="float32")
    if data.ndim > 1:
        data = data.mean(axis=1)
    if sr != 16000:
        raise RuntimeError(f"Granite Speech expects 16 kHz audio, got {sr}")

    processor, tokenizer, model = _load()
    prompt = tokenizer.apply_chat_template(
        [dict(role="system", content=_SYSTEM_PROMPT), dict(role="user", content=_USER_PROMPT)],
        tokenize=False, add_generation_prompt=True,
    )

    chunk_len = int(chunk_secs * sr)
    parts: list[str] = []
    for start in range(0, len(data), chunk_len):
        chunk = data[start:start + chunk_len]
        if len(chunk) < sr * 0.5:  # skip sub-500ms tails
            continue
        wav = torch.from_numpy(np.ascontiguousarray(chunk)).unsqueeze(0)
        inputs = processor(prompt, wav, device="cpu", return_tensors="pt").to("cpu")
        outputs = model.generate(**inputs, max_new_tokens=200, do_sample=False, num_beams=1)
        n_in = inputs["input_ids"].shape[-1]
        text = tokenizer.batch_decode(
            outputs[:, n_in:], add_special_tokens=False, skip_special_tokens=True
        )[0].strip()
        if text:
            parts.append(text)
        logger.info("Granite Speech chunk %.0f-%.0fs done.", start / sr, (start + len(chunk)) / sr)
    result = " ".join(parts).strip()
    if not result:
        raise RuntimeError("Granite Speech produced no transcript")
    return result
