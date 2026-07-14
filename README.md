# ACCESSGATE

**A local, explainable conformance pre-check engine for film accessibility — click a failing audio-description gap, and Granite Vision drafts a fix, the DCMP validator re-checks it, Granite Guardian screens it, and the row flips green live on an interactive timeline.**

[![CI](https://github.com/StephenSook/accessgate/actions/workflows/test.yml/badge.svg)](https://github.com/StephenSook/accessgate/actions/workflows/test.yml)
[![Live demo](https://img.shields.io/badge/live%20demo-online-3fb950.svg)](https://accessgate-web.vercel.app)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/downloads/)
[![IBM AI Builders Challenge July 2026](https://img.shields.io/badge/IBM%20AI%20Builders-July%202026-054ada.svg)](https://lablab.ai)
[![174 tests](https://img.shields.io/badge/tests-174%20passing-3fb950.svg)](tests/)

Built for the **IBM AI Builders Challenge July 2026**, **Reimagine Creative Industries with AI** track.

> **"Only 16 of 90 Sundance 2026 films were watchable if you are blind. We fix the rest before they ship."**

The locked claim: **conformance pre-check: automatable checks plus human-judgment flags.** This is not a certifier.

---

## Live Demo

| Surface | URL |
|---|---|
| Web app | https://accessgate-web.vercel.app |
| REST API | https://accessgate-api.onrender.com |
| Health check | https://accessgate-api.onrender.com/health |
| Pre-computed demo report | https://accessgate-api.onrender.com/demo |
| GitHub | https://github.com/StephenSook/accessgate |

Open the web app and click **LOAD DEMO** to see the full conformance timeline, rule results table, NER score, and gap markers, no file upload needed. The demo runs on a Night of the Living Dead segment (United States public domain) whose caption and audio-description sidecars carry realistic conformance defects. Uploading your own caption file on the live site runs the same 23-rule engine on the hosted backend.

To run the full live engine with Ollama models locally, see [Build and Run](#build-and-run).

---

## The Problem

At Sundance 2026, only 16 of 90 feature films offered audio description — down from 26 in 2024. Festivals, distributors, and streaming platforms reject non-compliant caption and audio-description files using automated QC pipelines. Manual QC costs $9–$14/min for audio description. No open-source tool checks both caption and audio-description conformance against WCAG 2.2, FCC 47 CFR 79.1(j)(2), DCMP, and Netflix standards simultaneously. ADA Title II compliance deadlines arrive April 2027 and April 2028.

---

## What It Does

AccessGate ingests a film plus its caption (.srt/.vtt) and audio-description (.vtt) sidecar files, scores them against **23 coded rules** across four standards families, and returns a per-rule pass/fail report where every flag cites the exact standard text it came from — retrieved at runtime from a Granite Embedding index, never hardcoded.

Click a failing audio-description gap on the conformance timeline and the gated fix loop runs: Granite Vision drafts a description sized to fit the silent window, the DCMP structure validator re-checks it, Granite Guardian screens it for content safety, and the row flips green live.

**Delete every hosted AI API. The engine still runs and still produces a report.** That property, plus a deep and genuinely load-bearing IBM stack built through IBM Bob, is the differentiator.

---

## AccessGate in One Loop

> A film's caption file has a 44-character line, a 1.2-second cue, a 240-wpm burst, a sound effect without a source bracket, and a 2.1-second sync drift. Its audio-description file has a past-tense line, a jargon term, and an AD line overlapping dialogue. The NER caption score lands at 94.1% — below 98%, but ASR carries measured racial disparity (Koenecke et al., PNAS 2020: WER 0.35 for Black speakers vs 0.19 for white), so the band is flagged for human review, never auto-failed. Every flag cites the exact standard section that governs it. Click the failing AD gap at 67.2s — Granite Vision drafts a present-tense, active-voice, third-person description that fits the 6.6-second window. The DCMP validator passes it. Guardian clears it. The row flips green.

---

## Architecture

```mermaid
flowchart TB
    subgraph Input
        F["Film / Video"]
        CAP["Captions (.srt/.vtt)"]
        AD["Audio Description (.vtt)"]
    end

    subgraph TIMING["Timing Engine (self-built, API-deletion-proof)"]
        direction LR
        FW["faster-whisper\nword_timestamps=True"]
        VAD["Silero VAD\nspeech regions"]
        GAP["Gap Engine\ncomplement above 2.5s"]
        FW --> GAP
        VAD --> GAP
    end

    subgraph SCORE["Scoring Engine (self-built, API-deletion-proof)"]
        direction LR
        GS["Granite Speech 3.3-2b\nreference transcript"]
        NER["NER Scorer\n(N-E-R)/N + confidence band"]
        CLS["Error-Type Classifier\nmacro-F1 0.952"]
        GS --> NER
        CLS --> NER
    end

    subgraph RULES["23-Rule Evaluator Engine (self-built, API-deletion-proof)"]
        direction LR
        FCC["FCC 47 CFR 79.1"]
        WCAG["WCAG 2.2\nSC 1.2.2 / 1.2.5"]
        DCMP["DCMP Caption\n+ Description Keys"]
        NFLX["Netflix TTSG"]
        RAG["Granite Embedding r2\nRAG citations from standards"]
    end

    subgraph EXPORT
        SARIF["SARIF 2.1.0\n(timecodes in property bags)"]
        OSCAL["OSCAL POA&M v1.1.2"]
    end

    subgraph GENFIX["Gated Generative Fix (on gap click)"]
        direction LR
        GV["Granite Vision\ndraft AD description"]
        DCMPV["DCMP Structure\nValidator (self-built)"]
        GG["Granite Guardian\ncontent safety screen"]
        WX["watsonx.ai Lite\nhosted side-by-side"]
        GV --> DCMPV --> GG
        GV -.-> WX
    end

    subgraph UI["React + IBM Carbon SPA"]
        TL["Interactive Conformance\nTimeline"]
        TBL["Rule Results Table\n(expandable citations)"]
        PANEL["Gated Fix Panel\n(Stage 1-2-3-4)"]
        AXE["axe-core A11Y badge\n(app audits itself)"]
        LIVE["Live Caption Monitor\nWebSocket CPS/WPM"]
    end

    F --> TIMING
    CAP --> TIMING
    F --> SCORE
    TIMING --> RULES
    SCORE --> RULES
    AD --> RULES
    RULES --> EXPORT
    RULES --> UI
    UI -->|gap click| GENFIX
    GENFIX --> UI
```

---

## IBM Stack (what is actually wired)

Every row below is wired in the shipped code, not aspirational. The wiring column states exactly how, because honest labeling is the point: a judge can grep any claim. See the live `/judges` endpoint for the same breakdown.

| IBM Tool | Role | Wiring |
|---|---|---|
| **IBM Bob** | Wrote all engine and frontend product code; parallel subagents; custom mode; conformance Skill; Plan specs; two /review audits (SARIF + OSCAL); self-referential MCP loop | Primary development tool |
| **Granite Speech 3.3-2b** | High-accuracy reference transcript feeding the NER scorer | Wired, local `transformers` (`src/granite_speech.py`, opt-in `ACCESSGATE_GRANITE_SPEECH=1`; faster-whisper is the default reference because Granite Speech is ~20x realtime on CPU) |
| **Granite Vision 3.2 2b** | Drafts the AD fix on a failing gap | Wired, local Ollama (`src/generative_fix.py`) |
| **Granite Guardian 3 2b** | Screens generated AD for content safety before the row flips green | Wired, local Ollama (`src/generative_fix.py`) |
| **Granite Embedding r2** | Embeds the standards corpus so citations are retrieved at runtime, never hardcoded | Wired, `sentence-transformers` (`src/rag.py`; deterministic TF-IDF fallback if unavailable) |
| **watsonx.ai (granite-3-8b-instruct)** | Hosted AD-line generation, side-by-side with the local Granite path in the gated fix | Wired, hosted (`src/watsonx_showcase.py`) |
| **AI FactSheet model card** | Governance doc for the trained classifier: training data, evaluation, and ASR-disparity bias handling | `data/training/model_card.md` |

---

## Four Self-Built Load-Bearing Artifacts

Each passes the **API-deletion test** — remove every hosted AI API and each still runs.

1. **Conformance rule engine** — NER scorer (`(N-E-R)/N`, Romero-Fresco/Ofcom broadcast model), 98% threshold, confidence bands, never auto-fails on ASR alone per Koenecke et al. PNAS 2020
2. **Dialogue-gap detection and timing engine** — Silero VAD + silence detection, gap complement above 2.5s minimum, merged across sub-300ms blips
3. **Audio-description structure validator** — DCMP rules: word-count-fits-gap, no-overlap-with-dialogue, present-tense, active-voice, third-person, objectivity flags
4. **Caption error-type classifier** — supervised logistic regression on hand-labeled data, distinguishes recognition errors (ASR mishears) from edition errors (paraphrase/omission); **macro-F1: 0.952**

---

## Evaluation (measured, not asserted)

| Metric | Value | Source |
|---|---|---|
| Classifier macro-F1 | **0.952** | Held-out gold test set, 3-class |
| Rule engine: violations detected | **10 / 10** | `data/demo/notld_broken.srt` + `notld_broken_ad.vtt` degradation recipe |
| SARIF schema valid | **pass** | `@microsoft/sarif-multitool validate` in CI |
| axe-core A11Y score | **100%** | App audits its own UI on every load |
| Tests passing | **132** | `pytest` on Python 3.11 |

---

## How IBM Bob Was Used

| Evidence | Location |
|---|---|
| Custom mode (`accessibility-compliance-engineer`) | `.bob/custom_modes.yaml` |
| Conformance rule-authoring skill | `.bob/skills/conformance/SKILL.md` |
| Plan-mode specs | `plan/accessgate-master-plan.md` |
| /review audit 1 (SARIF, Account A) | `security/review-audit-1.sarif` |
| /review audit 2 (OSCAL POA&M, Account B) | `security/review-audit-2.oscal.json` |
| Self-referential MCP config | `.bob/mcp.json` |
| Bobalytics screenshots | `bob_sessions/` |

---

## Build and Run

```bash
# 1. Clone and install
git clone https://github.com/StephenSook/accessgate.git
cd accessgate
pip install -r requirements.txt

# 2. Pull Ollama models (requires Ollama running locally)
ollama pull granite3.2-vision:2b
ollama pull granite3-guardian:2b
ollama pull granite3.2:8b

# 3. Copy env template
cp .env.example .env  # fill in WATSONX_API_KEY + WATSONX_PROJECT if you have them

# 4. Run the conformance engine (CLI)
python -m src.engine data/demo/notld_broken.srt data/demo/notld_broken_ad.vtt

# 5. Run tests
pytest

# 6. Start the API server
uvicorn src.app:app --reload --port 8000

# 7. Start the frontend (separate terminal)
cd frontend && npm install && npm run dev
# Open http://localhost:5173

# 8. Lint SARIF export (validates against the vendored SARIF 2.1.0 schema)
python scripts/validate_sarif.py security/review-audit-1.sarif
```

---

## Repository Structure

```
accessgate/
├── src/
│   ├── engine.py              # Main CLI entry point
│   ├── models.py              # Pydantic data models
│   ├── registry.py            # Rule registry loader
│   ├── caption_parser.py      # SRT/VTT parser
│   ├── gap_engine.py          # Silero VAD gap detector
│   ├── ner_scorer.py          # NER-style caption scorer
│   ├── classifier.py          # Error-type classifier (macro-F1 0.952)
│   ├── rag.py                 # Granite Embedding RAG layer
│   ├── generative_fix.py      # Granite Vision -> DCMP -> Guardian fix loop
│   ├── app.py                 # FastAPI REST server + /demo endpoint
│   ├── live_monitor.py        # Sliding-window live caption monitor
│   ├── watsonx_showcase.py    # watsonx.ai Lite hosted showcase call
│   ├── evaluators/            # fcc.py, wcag.py, dcmp_caption.py, dcmp_desc.py, netflix.py
│   ├── exporters/             # sarif.py (2.1.0), oscal.py (POA&M v1.1.2)
│   └── mcp_server/            # FastMCP server (self-referential IBM Bob loop)
├── rules/rules_registry.yaml  # 23 rules across FCC / WCAG / DCMP / Netflix
├── standards/                 # Authoritative standards corpus + Granite Embedding index
├── data/
│   ├── demo/                  # notld_broken.srt, notld_broken_ad.vtt, demo_report.json
│   └── training/
│       ├── model_card.md      # IBM AI FactSheet for the classifier
│       └── label_schema.md    # Annotation schema
├── frontend/                  # Vite + React + IBM Carbon SPA
├── plan/                      # IBM Bob Plan-mode specs (committed)
├── security/                  # SARIF + OSCAL /review audit outputs
├── bob_sessions/              # IBM Bob session exports + Bobalytics screenshots
├── submission/                # Demo video beat sheet, SkillsBuild cert instructions
├── tests/                     # 132 passing tests
├── render.yaml                # Render deployment config (FastAPI backend)
├── AGENTS.md                  # Project policy spine (read every session)
└── .bob/                      # Custom mode, conformance skill, MCP config
```

---

## Selected Challenge Theme

**Reimagine Creative Industries with AI** — AccessGate reimagines the post-production accessibility step that determines whether blind and Deaf audiences can experience a film at all. It removes the manual QC bottleneck between a finished film and its full audience.

The same rule-engine-plus-gated-fix architecture generalizes to music rights conformance and dubbing QA.

---

## Real-World Impact

- ADA Title II compliance deadlines: April 26, 2027 (population 50,000+) and April 26, 2028 (smaller entities)
- India MIB mandated audio description and closed captions for theatrical films (O.M. 15.03.2024) and OTT platforms (06.02.2026)
- Netflix auto-QC rejects non-compliant timed-text files before human review
- Manual AD QC costs $9–$14/min — AccessGate reduces the pre-check step to seconds
- The accessibility tool passes its own accessibility audit (axe-core, A11Y 100%)

---

## Demo Assets

- **Night of the Living Dead (1968)** — US public domain (published without valid copyright notice). Source: archive.org/details/night-of-the-living-dead_1968
- **Big Buck Bunny** — CC BY 3.0. Attribution: (c) copyright 2008, Blender Foundation / www.bigbuckbunny.org

See [NOTICE](NOTICE) for full third-party attribution.

---

## SkillsBuild

Every team member has completed an IBM SkillsBuild learning activity. Certificate documentation is in `submission/`.

---

## License

MIT — see [LICENSE](LICENSE). See [NOTICE](NOTICE) for third-party media and training-data attribution.
