"""
Tests for the caption parser.
"""
import pytest
import tempfile
import os
from src.caption_parser import parse_captions


SRT_CONTENT = """\
1
00:00:01,000 --> 00:00:03,500
Hello world
this is line two

2
00:00:04,000 --> 00:00:06,000
A second caption here

3
00:00:07,100 --> 00:00:07,900
Short one
"""

VTT_CONTENT = """\
WEBVTT

1
00:00:01.000 --> 00:00:03.500
Hello world
this is line two

2
00:00:04.000 --> 00:00:06.000
A second caption here

3
00:00:07.100 --> 00:00:07.900
Short one
"""

LONG_LINE_SRT = """\
1
00:00:01,000 --> 00:00:05,000
This line is exactly 43 chars longggggg!!!

2
00:00:06,000 --> 00:00:08,000
Normal line
"""


def _write_temp(content: str, suffix: str) -> str:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False, encoding="utf-8")
    f.write(content)
    f.close()
    return f.name


def test_srt_cue_count():
    path = _write_temp(SRT_CONTENT, ".srt")
    try:
        cues = parse_captions(path)
        assert len(cues) == 3
    finally:
        os.unlink(path)


def test_srt_timecodes():
    path = _write_temp(SRT_CONTENT, ".srt")
    try:
        cues = parse_captions(path)
        assert abs(cues[0].start - 1.0) < 0.01
        assert abs(cues[0].end - 3.5) < 0.01
        assert abs(cues[1].start - 4.0) < 0.01
    finally:
        os.unlink(path)


def test_srt_lines():
    path = _write_temp(SRT_CONTENT, ".srt")
    try:
        cues = parse_captions(path)
        assert len(cues[0].lines) == 2
        assert cues[0].lines[0] == "Hello world"
        assert cues[0].lines[1] == "this is line two"
    finally:
        os.unlink(path)


def test_vtt_cue_count():
    path = _write_temp(VTT_CONTENT, ".vtt")
    try:
        cues = parse_captions(path)
        assert len(cues) == 3
    finally:
        os.unlink(path)


def test_vtt_timecodes():
    path = _write_temp(VTT_CONTENT, ".vtt")
    try:
        cues = parse_captions(path)
        assert abs(cues[0].start - 1.0) < 0.01
        assert abs(cues[0].end - 3.5) < 0.01
    finally:
        os.unlink(path)


def test_duration_property():
    path = _write_temp(SRT_CONTENT, ".srt")
    try:
        cues = parse_captions(path)
        assert abs(cues[0].duration - 2.5) < 0.01
    finally:
        os.unlink(path)


def test_max_line_length():
    path = _write_temp(LONG_LINE_SRT, ".srt")
    try:
        cues = parse_captions(path)
        line = cues[0].lines[0]
        assert len(line) == 42, f"Expected 42, got {len(line)!r}: {line!r}"
        assert cues[0].max_line_length == 42
    finally:
        os.unlink(path)


def test_unsupported_format():
    with pytest.raises(ValueError, match="Unsupported caption format"):
        parse_captions("file.ass")


def test_short_cue_duration():
    path = _write_temp(SRT_CONTENT, ".srt")
    try:
        cues = parse_captions(path)
        # Third cue is 0.8s — should be detectable
        assert abs(cues[2].duration - 0.8) < 0.02
    finally:
        os.unlink(path)
