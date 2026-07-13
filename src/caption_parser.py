"""
Unified caption parser for AccessGate.
Handles .srt and .vtt files, returning list[CaptionCue].
Uses webvtt-py for .vtt (exposes cue position/line settings)
and pysubs2 for .srt.
"""
from __future__ import annotations
from pathlib import Path
import re
import webvtt
import pysubs2
from src.models import CaptionCue


def parse_captions(path: str | Path) -> list[CaptionCue]:
    """
    Parse a caption file (.srt or .vtt) into a list of CaptionCue objects.
    Raises ValueError for unsupported formats.
    """
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix == ".vtt":
        return _parse_vtt(p)
    elif suffix == ".srt":
        return _parse_srt(p)
    else:
        raise ValueError(f"Unsupported caption format: {suffix!r}. Use .srt or .vtt")


def _timestamp_to_seconds(ts: str) -> float:
    """Convert HH:MM:SS.mmm or MM:SS.mmm to float seconds."""
    ts = ts.strip()
    # Remove any VTT cue settings that might be appended
    ts = ts.split()[0]
    parts = ts.replace(",", ".").split(":")
    if len(parts) == 3:
        h, m, s = parts
        return int(h) * 3600 + int(m) * 60 + float(s)
    elif len(parts) == 2:
        m, s = parts
        return int(m) * 60 + float(s)
    else:
        return float(parts[0])


def _text_to_lines(text: str) -> list[str]:
    """Split cue text into individual lines, stripping VTT voice spans."""
    # Strip <v Speaker> tags
    text = re.sub(r"<v[^>]*>", "", text)
    # Strip other HTML-like tags
    text = re.sub(r"<[^>]+>", "", text)
    lines = [line.strip() for line in text.strip().splitlines()]
    return [line for line in lines if line]


def _parse_vtt(path: Path) -> list[CaptionCue]:
    cues: list[CaptionCue] = []
    for i, cue in enumerate(webvtt.read(str(path))):
        lines = _text_to_lines(cue.text)
        text = "\n".join(lines)
        cues.append(CaptionCue(
            index=i + 1,
            start=_timestamp_to_seconds(cue.start),
            end=_timestamp_to_seconds(cue.end),
            text=text,
            lines=lines,
            position=getattr(cue, "position", None),
            line_setting=getattr(cue, "line", None),
            align=getattr(cue, "align", None),
        ))
    return cues


def _parse_srt(path: Path) -> list[CaptionCue]:
    subs = pysubs2.load(str(path), encoding="utf-8")
    cues: list[CaptionCue] = []
    for i, sub in enumerate(subs):
        # pysubs2 stores times in milliseconds
        start = sub.start / 1000.0
        end = sub.end / 1000.0
        # pysubs2 uses \N as its internal line separator
        raw_text = sub.text.replace(r"\N", "\n").replace(r"\n", "\n")
        lines = _text_to_lines(raw_text)
        text = "\n".join(lines)
        cues.append(CaptionCue(
            index=i + 1,
            start=start,
            end=end,
            text=text,
            lines=lines,
        ))
    return cues
