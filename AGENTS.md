# AGENTS.md

Project policy spine for AccessGate. IBM Bob reads this on every session.

## What AccessGate is

AccessGate is a local, explainable conformance pre-check engine for film accessibility. It scores a film's caption (.srt/.vtt) and audio-description (.vtt) sidecar files against coded rules from WCAG 2.2, FCC 47 CFR 79.1(j)(2), the DCMP Captioning and Description Keys, and a Netflix delivery profile, emits a per-rule pass/fail report with source citations plus SARIF and OSCAL exports, and offers a gated generative fix for a failing audio-description gap.

## Hard integrity constraints (do not violate)

- IBM Bob is the primary development tool: it authored the conformance engine, the test suite, and the frontend. Deployment, the Granite Speech wiring, and later honesty and UI refinements were finished with other tooling after Bob credits ran out. Do not claim Bob is the exclusive author of every line.
- The locked product claim is "conformance pre-check: automatable checks plus human-judgment flags." Never write "conformance checker" or "certifier" in code comments, UI strings, docs, or the README.
- Every rule the engine implements must cite its source (standard, section, verbatim short quote). Citations are retrieved from the parsed standard text via the RAG layer, never hardcoded from memory.
- Never auto-fail a caption on ASR evidence alone. ASR carries measured demographic disparity (Koenecke et al., PNAS 2020: average WER 0.35 for Black speakers vs 0.19 for white speakers across five commercial systems including IBM). ASR-derived accuracy is reference-relative and confidence-banded, and low-confidence regions are flagged for human review rather than penalized.
- Product UI stays generic and universal. Named personas belong only in pitch narration, never hardcoded into the product.
- All demo and training data is public domain, Creative Commons, or open-licensed and lawfully redistributable. No community-sourced subtitle files are used as a reference transcript.

## The timing engine rule

Base Granite Speech 3.3-2b does not emit timestamps. Use faster-whisper with word_timestamps=True for all timing (VAD windows, gap detection, sync checks, per-word confidence). Use Granite Speech 3.3-2b only for the high-accuracy reference transcript.

## Repo map

- `src/` — product code (engine, scorers, validators, MCP server)
- `src/evaluators/` — one file per rule family (fcc.py, wcag.py, dcmp_caption.py, dcmp_desc.py, netflix.py)
- `src/exporters/` — SARIF 2.1.0 and OSCAL POA&M v1.1.2 exporters
- `src/mcp_server/` — FastMCP server exposing check_conformance, detect_gaps, score_captions
- `rules/` — the rule registry (rules_registry.yaml) and parsed standards
- `standards/` — Docling-parsed source documents and Granite Embedding FAISS index
- `plan/` — Bob Plan-mode specs, committed
- `security/` — SARIF and OSCAL POA&M outputs from /review audits
- `bob_sessions/` — exported Bob task histories and Bobalytics screenshots
- `data/` — demo assets and NOTICE-tracked media; hand-labeled training data
- `frontend/` — Vite + Carbon single-page app

## Build and test commands

- Install: `pip install -r requirements.txt`
- Models: `ollama pull granite3.2-vision:2b granite3-guardian:2b granite3.2:8b`
- Run engine: `python -m src.engine <film> <captions> <ad>`
- Run tests: `pytest`
- Lint SARIF export: `npx @microsoft/sarif-multitool validate <file>.sarif`
- Frontend: `cd frontend && npm install && npm run dev`

## The four load-bearing self-built artifacts (protect these)

1. The conformance rule engine including the NER-style caption scorer.
2. The dialogue-gap detection and timing engine (Silero VAD plus silence detection).
3. The audio-description structure validator.
4. The trained caption error-type classifier (recognition vs edition errors) on hand-labeled data.

Each must survive an API-deletion test: with every hosted AI API removed, the engine still runs and still produces a report. Do not let any of these collapse into a hosted-API call.

## IBM Bob usage to document as evidence

Custom mode in .bob/custom_modes.yaml, Skill in .bob/skills/conformance/SKILL.md, Plan specs in plan/, two /review audits (SARIF plus OSCAL) in security/, exported bob_sessions/ with Bobalytics, and the self-referential MCP loop (the product's own MCP server exposing check_conformance, detect_gaps, score_captions, consumed by Bob during development).

## SARIF timecode rule

Timecodes go in a SARIF result's `properties` property bag — NOT in `region` fields. A SARIF region requires startLine, charOffset, or byteOffset. Violating this breaks schema validation.

## Submission deadline

July 31, 2026 at 11:59 PM ET. Submit July 30 evening. Never the final hour.
