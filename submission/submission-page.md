# BeMyApp Submission Page — ready-to-paste copy

Fill the BeMyApp project page with the sections below. Every claim here is
verifiable in the repo or on the live site (that is the point). No em-dashes,
no marketing filler. Deadline: July 31, 2026, 11:59 PM ET.

Links:
- GitHub: https://github.com/StephenSook/accessgate
- Live app: https://accessgate-web.vercel.app (click LOAD DEMO)
- REST API: https://accessgate-api.onrender.com
- Judges transparency page: https://accessgate-api.onrender.com/judges
- Demo video: (paste public YouTube URL here)

Selected challenge: July Challenge — Reimagine Creative Industries with AI.

---

## Tagline (one line)

A local, explainable accessibility conformance pre-check for film caption and
audio-description files, with a gated generative fix. Built with IBM Bob.

## Problem statement

At Sundance 2026, only 16 of 90 feature films were watchable if you are blind or
Deaf, down from 26 in 2024. Festivals, distributors, and streaming platforms
reject non-compliant caption and audio-description files through automated QC,
and manual QC of audio description runs 9 to 14 dollars per minute. No
open-source tool checks both captions and audio description against WCAG 2.2,
FCC 47 CFR 79.1(j)(2), DCMP, and Netflix rules at once. ADA Title II deadlines
land in April 2027 and April 2028, so the backlog is about to grow.

## Solution description

AccessGate ingests a film plus its caption (.srt/.vtt) and audio-description
(.vtt) sidecars and scores them against 23 coded rules across those four
standards families. Every flag cites the exact standard text behind it,
retrieved at runtime from a Granite Embedding index rather than hardcoded. Each
result carries a timecode, a confidence value where relevant, and a
human-review flag. The output exports to SARIF 2.1.0 and OSCAL POA&M so it drops
into existing security and compliance pipelines.

The result is a conformance pre-check (automatable checks plus human-judgment
flags), not a certifier. That distinction is deliberate: it never auto-fails a
caption on speech-recognition evidence alone, because ASR carries measured
racial disparity (Koenecke et al., PNAS 2020: word error rate 0.35 for Black
speakers versus 0.19 for white speakers). Accuracy scores are reference-relative,
confidence-banded, and flagged for human review.

Click a failing audio-description gap and the gated fix loop runs: Granite Vision
drafts a description sized to the silent window, a self-built DCMP validator
re-checks its structure, Granite Guardian screens it for content safety, and the
row flips only when all three pass.

## AI approach and architecture

The engine is self-built and runs with every hosted AI API removed (the
"API-deletion test"). That self-built core is the substance:

- Timing engine: faster-whisper (word timestamps) plus Silero VAD detect speech
  regions and the dialogue-free gaps that audio description must fill.
- NER-style caption scorer: the Romero-Fresco / Ofcom (N - E - R) / N method
  with a confidence band and low-confidence-region flags. Load-bearing artifact.
- Error-type classifier: a scikit-learn model (macro-F1 0.95) that separates
  recognition errors from edition errors.
- 23-rule evaluator engine across FCC, WCAG, DCMP, and Netflix.
- RAG citation layer: standards embedded with Granite Embedding r2, retrieved at
  runtime so citations are grounded, never hardcoded.
- SARIF 2.1.0 and OSCAL POA&M v1.1.2 exporters (timecodes in property bags).
- A FastMCP server exposing the engine as tools.

IBM stack, wired in the shipped code (see the live /judges page for the same
breakdown, and the README table for a per-claim wiring column):

- Granite Speech 3.3-2b: high-accuracy reference transcript for the NER scorer
  (local transformers).
- Granite Vision 3.2 2b and Granite Guardian 3 2b: draft and safety-screen the
  generative fix (local Ollama).
- Granite Embedding r2: the RAG citation index.
- watsonx (granite-3-8b-instruct): a hosted audio-description line generated
  side by side with the local Granite path.
- IBM Bob: the primary development tool (see below).

We label every capability by tier (wired-live, integration, accelerator) on the
public /judges endpoint. The honest labeling is the point: a judge can grep any
claim against the code.

## How IBM Bob was used

IBM Bob wrote the engine and frontend product code end to end: it authored the
23 rule evaluators, the NER scorer, the timing engine, the RAG layer, the SARIF
and OSCAL exporters, and the React interface. Bob ran parallel subagents for the
caption, audio-description, and report paths, used a custom
accessibility-compliance-engineer mode, authored a conformance rule-authoring
Skill, produced Plan-mode specifications, and ran two /review passes that emitted
a SARIF audit and an OSCAL audit. Bob also consumed the project's own MCP server
during development, a self-referential loop. Evidence lives in `.bob/`,
`security/review-audit-*.{sarif,oscal.json}`, and the `plan/` specs.

## Real-world impact

The tool targets a real, dated bottleneck (the Sundance access gap and the ADA
Title II deadlines) with output that plugs into real pipelines (SARIF, OSCAL).
The bias-aware scoring rule is a genuine safeguard, not a slogan: it exists
because ASR under-serves the exact audiences accessibility work is meant to
serve. Small-but-real beats large-but-fake here: the demo runs on a real
public-domain film segment, analyzed by the real engine.
