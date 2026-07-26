"""Reproducibility helper for the "real machine captions" evaluation.

Transcribes the public-domain Night of the Living Dead audio with faster-whisper
(no injected defects) and writes an .srt. Running the 23-rule engine on this file
shows AccessGate catching real, naturally-occurring caption defects, the kind that
plague every auto-generated caption track, not a hand-authored degradation recipe.

    python scripts/transcribe_real_captions.py
    python -m src.engine data/demo/notld_segment_16k.wav data/demo/notld_real_autocaption.srt
"""
from faster_whisper import WhisperModel

AUDIO = "data/demo/notld_segment_16k.wav"
OUT = "data/demo/notld_real_autocaption.srt"


def _ts(t: float) -> str:
    h, m, s, ms = int(t // 3600), int((t % 3600) // 60), int(t % 60), int(round((t - int(t)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def main() -> None:
    model = WhisperModel("tiny", device="cpu", compute_type="int8")
    segments, _ = model.transcribe(AUDIO, word_timestamps=False)
    cues = [f"{i}\n{_ts(s.start)} --> {_ts(s.end)}\n{s.text.strip()}" for i, s in enumerate(segments, 1)]
    with open(OUT, "w") as f:
        f.write("\n\n".join(cues) + "\n")
    print(f"Wrote {len(cues)} real machine-caption cues to {OUT}")


if __name__ == "__main__":
    main()
