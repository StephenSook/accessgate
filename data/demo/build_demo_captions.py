"""
Build realistic demo caption + audio-description sidecar files from the REAL
Night of the Living Dead cemetery-scene dialogue (public domain).

The reference transcript comes from the real film audio. The "vendor file under
test" is that real dialogue with a small set of realistic conformance defects
injected, so the engine demonstrably catches real-looking problems on real data
(not a synthetic fixture). Each injected defect is annotated below with the rule
it triggers.

Run: python data/demo/build_demo_captions.py
Outputs: data/demo/notld_broken.srt, data/demo/notld_broken_ad.vtt
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).parent
REF = HERE / "source" / "whisper_ref.json"


def ts_srt(t: float) -> str:
    h = int(t // 3600); m = int((t % 3600) // 60); s = t % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")


def ts_vtt(t: float) -> str:
    h = int(t // 3600); m = int((t % 3600) // 60); s = t % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


def build_captions(segments: list) -> str:
    """Degrade the real dialogue with realistic, rule-triggering defects."""
    cues = []
    for i, (start, end, text) in enumerate(segments):
        text = text.strip()

        # Defect 1 (NFLX-LEN-01, >42 char line): the "damned to hell" line is long.
        if "damned to hell" in text:
            text = "He shook his fist at me and said, boy, you will be damned straight to hell tonight!"

        # Defect 2 (DCMP-CAP-04 min-duration + high reading speed): compress a
        # long cue into a sub-2-second window.
        if "lost an hour" in text:
            end = start + 1.4  # 12 words in 1.4s -> ~514 wpm and under the 2s floor

        # Defect 3 (NER edition error, paraphrase vs reference): reword a line so
        # the caption diverges from the spoken reference.
        if text.startswith("Each year we spend"):
            text = "Annually we lay out a fair amount of cash on these particular items."

        # Defect 4 (FCC-SYN-01 sync drift): push a cue 2.3s ahead of its speech.
        if "coming to get you" in text:
            start = max(0.0, start - 2.3)
            end = end - 2.3

        # Defect 5 (DCMP-CAP-05 sound effect without a bracketed source): a wind
        # cue written as prose rather than [WIND HOWLING].
        if "Look, that comes one of them now" in text:
            text = "wind howling in the distance " + text

        cues.append((start, end, text))

    # Defect 6 (FCC-CMP-01 completeness): drop the "Which row is it in?" cue at
    # 3.6s so a spoken segment has zero caption coverage.
    cues = [c for c in cues if c[2] != "Which row is it in?"]

    out = []
    for idx, (start, end, text) in enumerate(cues, 1):
        out.append(f"{idx}\n{ts_srt(start)} --> {ts_srt(end)}\n{text}\n")
    return "\n".join(out)


def build_ad(segments: list) -> str:
    """Audio description timed into the REAL dialogue-free gaps, with defects."""
    # Real dialogue-free gaps in this segment (from the transcript):
    #   4.6-15.5 (11s), 37.8-53.9 (16s), 75.6-92.6 (17s)
    cues = [
        # Defect A (DCMP-DESC-01 past tense): AD should be present tense.
        (5.5, 9.0, "A sedan drove slowly along the winding cemetery road."),
        # Defect B (DCMP-DESC-03 jargon): "dolly shot" is production jargon.
        (39.0, 44.0, "In a slow dolly shot, the camera crept toward the gravestones."),
        # Clean present-tense description in the third gap.
        (77.0, 82.0, "Barbara steadies the wreath against the wind and steps back."),
    ]
    lines = ["WEBVTT", ""]
    for start, end, text in cues:
        lines.append(f"{ts_vtt(start)} --> {ts_vtt(end)}")
        lines.append(text)
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    data = json.loads(REF.read_text())
    segments = data["segments"]
    (HERE / "notld_broken.srt").write_text(build_captions(segments))
    (HERE / "notld_broken_ad.vtt").write_text(build_ad(segments))
    print("Wrote notld_broken.srt and notld_broken_ad.vtt from real dialogue.")


if __name__ == "__main__":
    main()
