"""
Shared Pydantic data models for AccessGate.
Every evaluator, scorer, and exporter uses these types.
"""
from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, Field, computed_field


class CaptionCue(BaseModel):
    """A single caption cue parsed from .srt or .vtt."""
    index: int
    start: float          # seconds
    end: float            # seconds
    text: str             # raw text with newlines
    lines: list[str]      # individual lines
    position: Optional[str] = None   # VTT cue position setting
    line_setting: Optional[str] = None  # VTT line setting
    align: Optional[str] = None      # VTT align setting

    @property
    def duration(self) -> float:
        return self.end - self.start

    @property
    def word_count(self) -> int:
        return len(self.text.split())

    @property
    def wpm(self) -> float:
        if self.duration <= 0:
            return 0.0
        return (self.word_count / self.duration) * 60.0

    @property
    def max_line_length(self) -> int:
        if not self.lines:
            return 0
        return max(len(line) for line in self.lines)

    @property
    def cps(self) -> float:
        """Characters per second (Netflix Timed Text Style Guide metric).

        Netflix reading speed counts all displayed characters including spaces
        and punctuation; only the line-break marker is excluded. Stripping
        spaces (as an earlier version did) undercounts CPS and lets over-speed
        captions pass, so we keep them.
        """
        char_count = len(self.text.replace("\n", ""))
        if self.duration <= 0:
            return 0.0
        return char_count / self.duration


class GapRegion(BaseModel):
    """A dialogue-free window where audio description can be placed."""
    start: float   # seconds
    end: float     # seconds

    @computed_field
    @property
    def duration(self) -> float:
        return self.end - self.start

    def max_words(self, wpm: float = 150.0) -> int:
        """Maximum words that fit in this gap at the given WPM."""
        return int((self.duration / 60.0) * wpm)

    def overlaps(self, start: float, end: float) -> bool:
        return self.start < end and self.end > start


class SpeechRegion(BaseModel):
    """A detected speech region from VAD."""
    start: float
    end: float


class RuleResult(BaseModel):
    """Result of evaluating a single rule against a file."""
    rule_id: str
    status: Literal["pass", "fail", "flag", "skip"]
    message: str
    timecode: Optional[float] = None      # seconds into the film
    citation: str = ""                     # RAG-retrieved verbatim source text
    sarif_level: Literal["error", "warning", "note"] = "warning"
    confidence: Optional[float] = None    # for banded checks
    human_review_required: bool = False


class NERScoreResult(BaseModel):
    """NER-style caption accuracy score with confidence band."""
    ner_score: float                        # point estimate 0–1
    band_low: float                         # worst-case
    band_high: float                        # best-case
    n_words: int                            # reference word count
    n_errors: int                           # total classified errors
    recognition_errors: int
    edition_errors: int
    asr_derived: bool = True               # True = reference came from ASR, not human gold
    low_confidence_regions: list[dict] = Field(default_factory=list)

    @computed_field
    @property
    def passes_98_threshold(self) -> bool:
        """
        True only if the ENTIRE confidence band is above 98%.
        Per the hard rule: never auto-fail on ASR evidence alone.
        Returns False (flag for review) if band straddles 98%.

        Must be @computed_field, not a bare @property: the frontend reads
        report.ner.passes_98_threshold to colour the NER metric, so it has to
        be serialized. As a plain property it was absent from the JSON and the
        indicator was pinned to amber even when the band cleared 98%.
        """
        return self.band_low >= 0.98

    @computed_field
    @property
    def straddles_threshold(self) -> bool:
        return self.band_low < 0.98 <= self.band_high


class ConformanceReport(BaseModel):
    """Full conformance pre-check report for one film + sidecar pair."""
    film_path: str
    caption_path: str
    ad_path: Optional[str] = None
    profile: Literal["dcmp", "netflix", "fcc"] = "netflix"
    results: list[RuleResult] = Field(default_factory=list)
    ner: Optional[NERScoreResult] = None
    gaps: list[GapRegion] = Field(default_factory=list)
    speech_regions: list[SpeechRegion] = Field(default_factory=list)

    @computed_field
    @property
    def error_count(self) -> int:
        return sum(1 for r in self.results if r.status == "fail" and r.sarif_level == "error")

    @computed_field
    @property
    def warning_count(self) -> int:
        return sum(1 for r in self.results if r.status == "fail" and r.sarif_level == "warning")

    @computed_field
    @property
    def flag_count(self) -> int:
        return sum(1 for r in self.results if r.status == "flag")


class FixResult(BaseModel):
    """Result of the gated generative AD fix loop."""
    gap: GapRegion
    draft_text: str
    draft_source: Optional[str] = None     # which model drafted (Granite Vision / watsonx / fallback)
    dcmp_valid: bool
    dcmp_issues: list[str] = Field(default_factory=list)
    guardian_cleared: bool
    guardian_ran: bool = True               # False = the safety screen could not run; never claim "passed"
    guardian_source: Optional[str] = None   # which Guardian ran (Ollama / watsonx), or None if it did not
    guardian_reason: Optional[str] = None
    accepted: bool
    word_count: int
    fits_gap: bool
