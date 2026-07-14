"""
AccessGate MCP server — self-referential loop.

Exposes three tools via FastMCP stdio transport:
  - check_conformance(film_path, caption_path, ad_path?) -> ConformanceReport JSON
  - detect_gaps(film_path, min_duration?) -> list of GapRegion dicts
  - score_captions(caption_path, reference_transcript) -> NERScoreResult dict

Register in .bob/mcp.json so IBM Bob can call these tools during development.
This is the self-referential loop: the product's own engine consumed by the tool
that built it.

Run standalone: python src/mcp_server/server.py
"""
from __future__ import annotations
import json
import logging
from pathlib import Path

from fastmcp import FastMCP

logger = logging.getLogger(__name__)

mcp = FastMCP(
    "accessgate",
    instructions=(
        "AccessGate conformance pre-check engine. "
        "Use check_conformance to run a full report, detect_gaps to find "
        "dialogue-free windows, or score_captions for caption accuracy."
    ),
)


@mcp.tool()
def check_conformance(
    film_path: str,
    caption_path: str,
    ad_path: str = "",
    profile: str = "netflix",
) -> dict:
    """
    Run the full AccessGate conformance pre-check pipeline on a film and its sidecar files.

    Parameters
    ----------
    film_path:     Path to the video file (MP4, MKV, etc.)
    caption_path:  Path to the caption sidecar (.srt or .vtt)
    ad_path:       Path to the audio description sidecar (.vtt), optional
    profile:       Conformance profile: "netflix" | "dcmp" | "fcc" (default: "netflix")

    Returns
    -------
    ConformanceReport as a JSON-serializable dict with:
      - results: list of per-rule pass/fail/flag results with citations
      - ner: NER caption accuracy score with confidence band
      - gaps: detected dialogue-free windows
      - error_count, warning_count, flag_count
    """
    from src.engine import run_engine

    report = run_engine(
        film_path=film_path,
        caption_path=caption_path,
        ad_path=ad_path if ad_path else None,
        profile=profile,
    )
    return json.loads(report.model_dump_json())


@mcp.tool()
def detect_gaps(
    film_path: str,
    min_duration: float = 2.5,
) -> list[dict]:
    """
    Detect dialogue-free gaps in a film using Silero VAD.

    Parameters
    ----------
    film_path:     Path to the video/audio file
    min_duration:  Minimum gap duration in seconds (default: 2.5)

    Returns
    -------
    List of gap regions, each with:
      - start: gap start time (seconds)
      - end: gap end time (seconds)
      - duration: gap length (seconds)
      - max_words: maximum AD words that fit at 150 wpm
    """
    from src.gap_engine import detect_gaps as _detect_gaps

    # detect_gaps returns (gaps, speech_regions) and its keyword is min_gap.
    gaps, _speech = _detect_gaps(film_path, min_gap=min_duration)
    return [
        {
            "start": g.start,
            "end": g.end,
            "duration": g.duration,
            "max_words": g.max_words(wpm=150.0),
        }
        for g in gaps
    ]


@mcp.tool()
def score_captions(
    caption_path: str,
    reference_transcript: str,
) -> dict:
    """
    Score caption accuracy using the NER-style scorer.

    Parameters
    ----------
    caption_path:         Path to the caption file (.srt or .vtt)
    reference_transcript: Reference transcript text (from Granite Speech or human gold)

    Returns
    -------
    NER score result with:
      - ner_score: point estimate (0.0–1.0)
      - band_low, band_high: confidence band (worst/best case)
      - passes_98_threshold: True if entire band >= 0.98
      - straddles_threshold: True if band crosses 0.98
      - human_review_required: True when straddles (never auto-fail on ASR alone)
      - low_confidence_regions: word-level regions flagged for human review
    """
    from src.caption_parser import parse_captions
    from src.ner_scorer import score_ner

    cues = parse_captions(Path(caption_path))
    hypothesis = " ".join(c.text.replace("\n", " ") for c in cues)

    result = score_ner(
        reference=reference_transcript,
        hypothesis=hypothesis,
        word_confidences=[],  # no ASR confidence available without film
    )
    return {
        "ner_score": result.ner_score,
        "band_low": result.band_low,
        "band_high": result.band_high,
        "n_words": result.n_words,
        "recognition_errors": result.recognition_errors,
        "edition_errors": result.edition_errors,
        "passes_98_threshold": result.passes_98_threshold,
        "straddles_threshold": result.straddles_threshold,
        "human_review_required": result.straddles_threshold or not result.passes_98_threshold,
        "low_confidence_regions": result.low_confidence_regions,
        "asr_derived": result.asr_derived,
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    mcp.run()
