"""
Build the demo caption + audio-description sidecars for AccessGate.

The dialogue is the REAL Night of the Living Dead cemetery scene (US public
domain), transcribed from the film. These are formatted as a realistic vendor
caption file: mostly well-formed (<=32 char lines, >=2s, sane reading speed),
timed to the real speech, with a small set of deliberate conformance defects so
the engine visibly catches real-looking problems. Each defect is annotated with
the rule it triggers. The OUTPUT report is produced by the real engine on the
real film; only this INPUT fixture is crafted (as any QC test file must be).

AD cues are timed into the real Silero-VAD dialogue-free gaps (39.1-44.9,
45.7-49.6, 157.7-160.3).

Run: python data/demo/build_demo_captions.py
"""
from __future__ import annotations

from pathlib import Path

HERE = Path(__file__).parent


def ts_srt(t: float) -> str:
    h, m, s = int(t // 3600), int((t % 3600) // 60), t % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")


def ts_vtt(t: float) -> str:
    h, m, s = int(t // 3600), int((t % 3600) // 60), t % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


# (start, end, text) — \n marks a line break. Most cues are clean; the ones
# tagged DEFECT carry one deliberate, realistic conformance violation.
CAPTION_CUES = [
    (0.5, 3.0, "There's nothing wrong\nwith the radio."),
    (3.5, 6.0, "It must have been\na station."),
    (15.5, 18.5, "Well, there's no one\naround here."),
    (28.0, 31.0, "It's late. You've\ngotten up earlier."),
    # DEFECT NFLX-LEN-01 + DCMP-CAP-01: a single 46-char line, over both limits.
    (31.5, 34.5, "I already lost a whole hour of sleep on this."),
    # DEFECT DCMP-CAP-04: 0.8s display, under the 2-second minimum.
    (36.9, 37.7, "There it is."),
    (50.5, 53.5, "I wonder what happened\nto last year's."),
    (54.0, 57.0, "Each year we spend\ngood money on these."),
    # DEFECT NER edition error: paraphrase of the spoken "we come out here".
    (57.5, 60.5, "We drive all the way out\nand it's vanished."),
    # DEFECT DCMP-CAP-05: sound effect written as prose, no [BRACKETS].
    (63.5, 66.5, "wind rushes through\nthe bare trees"),
    (92.5, 95.0, "Church was this\nmorning, remember?"),
    (119.0, 122.0, "I haven't seen you\nin church lately."),
    # DEFECT FCC-SYN-01: spoken at 155.0s, caption pushed 2.4s early.
    (152.6, 155.0, "They're coming to get\nyou, Barbara."),
    (158.6, 161.0, "Stop it. You're\nignorant."),
    (163.8, 166.5, "Stop it. You're acting\nlike a child."),
    # DEFECT DCMP-CAP-03 + NFLX-CPS-01: 11 words in 1.0s, far over reading speed.
    (168.6, 169.6, "Look here comes one of them right now, come on hurry."),
]

# AD cues timed into the real VAD gaps.
AD_CUES = [
    # DEFECT DCMP-DESC-01: past tense ("drove"); DCMP requires present tense.
    (39.6, 44.4, "A sedan drove slowly along the cemetery road."),
    # DEFECT DCMP-DESC-03: production jargon ("dolly shot").
    (46.0, 49.2, "In a dolly shot, the camera creeps toward the graves."),
    # Clean, present tense, fits the 2.6s gap.
    (157.9, 160.1, "A figure lurches out from behind the trees."),
]


def build_srt() -> str:
    out = []
    for i, (start, end, text) in enumerate(CAPTION_CUES, 1):
        out.append(f"{i}\n{ts_srt(start)} --> {ts_srt(end)}\n{text}\n")
    return "\n".join(out)


def build_vtt() -> str:
    lines = ["WEBVTT", ""]
    for start, end, text in AD_CUES:
        lines += [f"{ts_vtt(start)} --> {ts_vtt(end)}", text, ""]
    return "\n".join(lines)


def main() -> None:
    (HERE / "notld_broken.srt").write_text(build_srt())
    (HERE / "notld_broken_ad.vtt").write_text(build_vtt())
    print(f"Wrote {len(CAPTION_CUES)} caption cues and {len(AD_CUES)} AD cues from real dialogue.")


if __name__ == "__main__":
    main()
