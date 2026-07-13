"""
Dialogue-gap detection and timing engine for AccessGate.
Load-Bearing Artifact #2 — survives API deletion.

Uses Silero VAD for speech region detection, then computes
dialogue-free gaps as the complement of speech regions.

Timing engine rule (AGENTS.md):
  - faster-whisper word_timestamps=True for ALL timing
  - This module handles VAD/gap detection only
  - Granite Speech is used separately for reference transcripts only
"""
from __future__ import annotations
import subprocess
import tempfile
import os
from pathlib import Path
from src.models import GapRegion, SpeechRegion, CaptionCue

# Minimum gap duration to report (seconds)
DEFAULT_MIN_GAP = 2.5
# Merge gaps separated by less than this (seconds)
DEFAULT_MERGE_BLIP = 0.3
# Sync tolerance for cue-to-speech overlap check (ms)
DEFAULT_SYNC_TOLERANCE_MS = 500


def _extract_audio_mono16k(video_path: str | Path, output_path: str) -> None:
    """Extract mono 16kHz WAV from any video/audio file using ffmpeg."""
    cmd = [
        "ffmpeg", "-y", "-i", str(video_path),
        "-ac", "1",           # mono
        "-ar", "16000",       # 16kHz
        "-vn",                # no video
        "-f", "wav",
        output_path
    ]
    result = subprocess.run(cmd, capture_output=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg failed extracting audio:\n{result.stderr.decode()}"
        )


def detect_speech_regions(audio_path: str | Path) -> list[SpeechRegion]:
    """
    Run Silero VAD on a 16kHz mono WAV file and return speech regions.
    Falls back to energy-based RMS detection if Silero fails.
    """
    import torch
    try:
        from silero_vad import load_silero_vad, get_speech_timestamps, read_audio
        model = load_silero_vad()
        wav = read_audio(str(audio_path), sampling_rate=16000)
        raw = get_speech_timestamps(
            wav, model,
            sampling_rate=16000,
            return_seconds=True,
            threshold=0.5,
            min_speech_duration_ms=250,
            min_silence_duration_ms=100,
        )
        return [SpeechRegion(start=r["start"], end=r["end"]) for r in raw]
    except Exception as e:
        # Fallback: energy-based RMS silence detection
        return _rms_speech_regions(str(audio_path))


def _rms_speech_regions(audio_path: str) -> list[SpeechRegion]:
    """
    Fallback energy-based speech detector.
    Chunks the audio into 30ms frames, marks frames above
    an RMS energy threshold as speech, merges adjacent speech frames.
    """
    import wave
    import struct
    import math

    regions: list[SpeechRegion] = []
    try:
        with wave.open(audio_path, "rb") as wf:
            n_channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            framerate = wf.getframerate()
            n_frames = wf.getnframes()

            frame_ms = 30
            frame_samples = int(framerate * frame_ms / 1000)
            threshold = 300  # RMS energy threshold

            speech_frames: list[bool] = []
            for _ in range(0, n_frames, frame_samples):
                raw = wf.readframes(frame_samples)
                if not raw:
                    break
                count = len(raw) // sampwidth
                fmt = {1: "B", 2: "h", 4: "i"}.get(sampwidth, "h")
                samples = struct.unpack(f"{count}{fmt}", raw[:count * sampwidth])
                # Take first channel if stereo
                samples = samples[::n_channels]
                rms = math.sqrt(sum(s * s for s in samples) / len(samples)) if samples else 0
                speech_frames.append(rms > threshold)

            # Merge adjacent speech frames into regions
            in_speech = False
            start = 0.0
            for i, is_speech in enumerate(speech_frames):
                t = i * frame_ms / 1000.0
                if is_speech and not in_speech:
                    start = t
                    in_speech = True
                elif not is_speech and in_speech:
                    regions.append(SpeechRegion(start=start, end=t))
                    in_speech = False
            if in_speech:
                regions.append(SpeechRegion(
                    start=start,
                    end=len(speech_frames) * frame_ms / 1000.0
                ))
    except Exception:
        pass
    return regions


def compute_gaps(
    speech_regions: list[SpeechRegion],
    total_duration: float,
    min_gap: float = DEFAULT_MIN_GAP,
    merge_blip: float = DEFAULT_MERGE_BLIP,
) -> list[GapRegion]:
    """
    Compute dialogue-free gaps as the complement of speech regions.

    Algorithm:
      1. Sort speech regions by start time
      2. Build intervals between regions (and before first / after last)
      3. Merge adjacent gaps separated by < merge_blip seconds
      4. Filter gaps below min_gap seconds
    """
    if not speech_regions:
        if total_duration > min_gap:
            return [GapRegion(start=0.0, end=total_duration)]
        return []

    sorted_regions = sorted(speech_regions, key=lambda r: r.start)

    # Build candidate gap intervals
    candidates: list[tuple[float, float]] = []

    # Gap before first speech region
    if sorted_regions[0].start > 0:
        candidates.append((0.0, sorted_regions[0].start))

    # Gaps between consecutive speech regions
    for i in range(len(sorted_regions) - 1):
        gap_start = sorted_regions[i].end
        gap_end = sorted_regions[i + 1].start
        if gap_end > gap_start:
            candidates.append((gap_start, gap_end))

    # Gap after last speech region
    last_end = sorted_regions[-1].end
    if total_duration > last_end:
        candidates.append((last_end, total_duration))

    # Merge gaps separated by sub-merge_blip speech blips
    merged: list[tuple[float, float]] = []
    for start, end in candidates:
        if merged and (start - merged[-1][1]) < merge_blip:
            merged[-1] = (merged[-1][0], end)
        else:
            merged.append((start, end))

    # Filter by minimum duration
    gaps = [
        GapRegion(start=s, end=e)
        for s, e in merged
        if (e - s) >= min_gap
    ]
    return gaps


def get_audio_duration(audio_path: str | Path) -> float:
    """Return duration of an audio file in seconds using ffprobe."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(audio_path)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {result.stderr}")
    return float(result.stdout.strip())


def detect_gaps(
    video_path: str | Path,
    min_gap: float = DEFAULT_MIN_GAP,
    merge_blip: float = DEFAULT_MERGE_BLIP,
) -> tuple[list[GapRegion], list[SpeechRegion]]:
    """
    Main entry point: detect dialogue-free gaps in a video/audio file.

    Returns (gaps, speech_regions) tuple.
    Both lists are sorted by start time.
    API-deletion proof: only uses local Silero VAD + ffmpeg.
    """
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
        wav_path = tf.name

    try:
        _extract_audio_mono16k(video_path, wav_path)
        total_duration = get_audio_duration(wav_path)
        speech_regions = detect_speech_regions(wav_path)
        gaps = compute_gaps(speech_regions, total_duration, min_gap, merge_blip)
        return gaps, speech_regions
    finally:
        if os.path.exists(wav_path):
            os.unlink(wav_path)


def cue_overlaps_speech(
    cue: CaptionCue,
    speech_regions: list[SpeechRegion],
    tolerance_ms: int = DEFAULT_SYNC_TOLERANCE_MS,
) -> bool:
    """
    FCC-SYN-01: Returns True if this caption cue overlaps any speech region
    within the given tolerance window.

    A cue 'overlaps' a speech region if:
      cue.start <= region.end + tolerance AND cue.end >= region.start - tolerance
    """
    tol = tolerance_ms / 1000.0
    for region in speech_regions:
        if cue.start <= region.end + tol and cue.end >= region.start - tol:
            return True
    return False


def ad_overlaps_speech(
    ad_start: float,
    ad_end: float,
    speech_regions: list[SpeechRegion],
) -> bool:
    """
    DCMP-DESC-05: Returns True if an AD cue overlaps any detected speech region.
    No tolerance — any overlap is a violation.
    """
    for region in speech_regions:
        if ad_start < region.end and ad_end > region.start:
            return True
    return False
