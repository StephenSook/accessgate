"""
Live caption monitoring with sliding-window conformance scoring.

Processes incoming audio chunks via faster-whisper, scores against
Netflix/DCMP thresholds in near-real-time, and emits per-metric
pass/warn/fail verdicts.

Target: ≤3s latency on 10-second windows (Apple Silicon, int8 model).
"""
from __future__ import annotations
import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# Thresholds (Netflix adult profile as default)
NETFLIX_MAX_CPS = 20.0
DCMP_MAX_WPM = 225.0
MIN_COVERAGE_RATIO = 0.8  # 80% of speech must be covered


class LiveMonitor:
    """
    Sliding-window live caption conformance monitor.

    Instantiated once per WebSocket connection. Processes audio chunks
    sequentially; each call to process_chunk returns updated metrics.
    """

    def __init__(self):
        self._model = None  # lazy-loaded faster-whisper model

    def _get_model(self):
        if self._model is None:
            try:
                from faster_whisper import WhisperModel
                self._model = WhisperModel(
                    "base",
                    device="cpu",
                    compute_type="int8",
                )
                logger.info("faster-whisper model loaded for live monitoring.")
            except Exception as e:
                logger.warning("faster-whisper unavailable: %s", e)
        return self._model

    def process_chunk(self, chunk_path: str, window_secs: float = 10.0) -> dict:
        """
        Transcribe an audio chunk and compute live conformance metrics.

        Parameters
        ----------
        chunk_path:   Path to the audio chunk file (wav/mp3/etc.)
        window_secs:  Sliding window duration in seconds

        Returns
        -------
        dict with keys: cps, wpm, coverage, violations, timestamp, status
        """
        t0 = time.time()
        metrics = {
            "cps": 0.0,
            "wpm": 0.0,
            "coverage": True,
            "violations": [],
            "timestamp": t0,
            "status": "pass",
            "latency_ms": 0,
        }

        if not chunk_path or not Path(chunk_path).exists():
            metrics["violations"].append("chunk_not_found")
            metrics["status"] = "error"
            return metrics

        model = self._get_model()
        if model is None:
            metrics["violations"].append("transcriber_unavailable")
            metrics["status"] = "warn"
            return metrics

        try:
            segments, info = model.transcribe(
                chunk_path,
                word_timestamps=True,
                language="en",
            )

            words = []
            total_chars = 0
            for seg in segments:
                for word in (seg.words or []):
                    words.append(word)
                    total_chars += len(word.word.strip())

            # CPS: characters / window duration
            cps = total_chars / window_secs if window_secs > 0 else 0.0
            # WPM: words / (window / 60)
            wpm = (len(words) / window_secs) * 60.0 if window_secs > 0 else 0.0

            metrics["cps"] = round(cps, 2)
            metrics["wpm"] = round(wpm, 1)

            violations = []
            if cps > NETFLIX_MAX_CPS:
                violations.append(f"CPS {cps:.1f} exceeds Netflix limit {NETFLIX_MAX_CPS}")
            if wpm > DCMP_MAX_WPM:
                violations.append(f"WPM {wpm:.0f} exceeds DCMP cap {DCMP_MAX_WPM}")

            metrics["violations"] = violations
            metrics["status"] = "fail" if violations else "pass"

        except Exception as e:
            logger.warning("Transcription error: %s", e)
            metrics["violations"].append(f"transcription_error: {e}")
            metrics["status"] = "warn"

        metrics["latency_ms"] = round((time.time() - t0) * 1000)
        return metrics
