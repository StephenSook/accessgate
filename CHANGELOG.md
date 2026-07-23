# Changelog

All notable changes to AccessGate are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/). This project was built for the
IBM AI Builders Challenge (July 2026) with IBM Bob as the primary development tool.

## 2026-07-20: Accessibility validated by a real screen-reader user

- Shipped a screen-reader heading outline (Upload, Conformance results, timeline,
  rule results) and a skip-to-content link, both in direct response to feedback
  from an audio-description user who tested the live app with the JAWS screen
  reader and reported it "very accessible" with all controls correctly labeled.
- Documented that outcome validation in the README (Real-World Impact), anonymized
  and with consent on file.

## 2026-07-19: Screen-reader accessibility for the results flow

- Added an aria-live status region that announces run start and completion with
  the result summary, so LOAD DEMO is no longer silent to a screen reader, plus a
  main landmark and a focusable results heading that receives focus after a run.
- Added a `scope_boundaries` section to the live `/judges` honesty endpoint,
  documenting what AccessGate does not check (audio-description final-mix loudness,
  semantic sufficiency), a boundary surfaced by a real audio-description user.
- Added that user's audio-description quality quote to the README Problem section.

## 2026-07-17: Judge Quick Access

- Added a task-oriented Judge Quick Access evidence map at the top of the README:
  try it with no setup, see every claim wired, verify honesty live, reproduce it.

## 2026-07-16: Framing and honesty

- Sharpened the defensible intersection claim (open, explainable, both caption and
  audio description, cited to the exact standard clause, with a gated generative fix).
- Named the deployment slot (who runs it Monday), added the Bob contribution metric,
  and untracked internal scaffolding from the public repository.

## 2026-07-14 to 2026-07-15: Mobile surfaces and reproducibility

- Shipped the mobile app: an original AccessGate icon, an Android APK (direct
  download plus install QR), and an iOS TestFlight build (public link, approved).
- Fixed the engine CLI argument order and shipped the demo audio so the command
  line reproduces the demo's three gaps exactly.
- Verified the engine on Python 3.11 and 3.12.

## 2026-07-13: Engine, IBM stack, and surfaces (foundation)

- Conformance engine: 23 coded rules across FCC 47 CFR 79.1, WCAG 2.2, the DCMP
  Captioning and Description Keys, and a Netflix delivery profile, where every flag
  cites the exact standard text it came from.
- Silero VAD dialogue-gap engine and an NER-style caption scorer that never
  auto-fails on ASR evidence alone (ASR carries measured demographic disparity,
  Koenecke et al., PNAS 2020).
- Trained caption error-type classifier (macro-F1 0.952 on a held-out set),
  documented as a separate reproducible artifact with an AI FactSheet model card.
- RAG citation layer on a Granite Embedding index, plus SARIF 2.1.0 and OSCAL
  POA&M v1.1.2 exporters.
- Gated generative fix loop: Granite Vision drafts a description, a self-built DCMP
  structure validator checks it, Granite Guardian screens it, and only then does
  the row flip green.
- watsonx.ai wiring for the hosted Granite path (fix drafting and the executive
  summary), a self-referential MCP server, and a FastAPI backend.
- Web frontend (Vite plus Carbon): conformance timeline, rule results table, video
  player, and waveform display.
- GitHub Actions CI (Python tests, frontend build, SARIF lint, secret scan) and two
  IBM Bob `/review` audits exported as SARIF and OSCAL POA&M.
