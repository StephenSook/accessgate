# AccessGate

[![CI](https://github.com/StephenSook/accessgate/actions/workflows/test.yml/badge.svg)](https://github.com/StephenSook/accessgate/actions/workflows/test.yml)
[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![IBM AI Builders Challenge July 2026](https://img.shields.io/badge/IBM%20AI%20Builders-July%202026-054ada.svg)](https://lablab.ai)

> **"Only 16 of 90 Sundance 2026 films were watchable if you are blind. We fix the rest before they ship."**

AccessGate is a local, explainable **conformance pre-check engine** for film accessibility. It scores a film's caption (.srt/.vtt) and audio-description (.vtt) sidecar files against coded rules from WCAG 2.2, FCC 47 CFR 79.1(j)(2), the DCMP Captioning and Description Keys, and the Netflix delivery profile — then offers a gated generative fix for failing audio-description gaps.

**The locked claim:** "conformance pre-check: automatable checks plus human-judgment flags." This is not a certifier.

---

## Problem Statement

At Sundance 2026, only 16 of 90 feature films offered audio description — down from 26 in 2024 (Disability Belongs, citing the festival's own listings). Festivals, distributors, and streaming platforms (Netflix, Prime Video) reject non-compliant caption and audio-description files using automated QC pipelines. Manual QC costs $9–$14/min for audio description. There is no open-source tool that checks both caption and audio-description conformance against WCAG 2.2, FCC 47 CFR 79.1(j)(2), DCMP, and Netflix standards simultaneously. ADA Title II compliance deadlines arrive April 2027 and April 2028.

## Solution

AccessGate ingests a film plus its caption and audio-description sidecar files, scores them against 23 coded rules across four standards families, and returns a per-rule pass/fail report where every flag cites the exact standard text it came from. Click a failing audio-description gap and Granite Vision drafts a description sized to fit the silent window — the DCMP structure validator re-checks it, Granite Guardian screens it, and the row flips green live on an interactive conformance timeline.

Delete every hosted AI API and the engine still runs and still produces a report. That property — plus a deep and genuinely load-bearing IBM stack built through IBM Bob — is what distinguishes AccessGate from a wrapper.

## AI Approach and Architecture

```
Film + Sidecars
      │
      ▼
┌─────────────────────────────────────────────────────────┐
│  faster-whisper (word_timestamps) → VAD Gap Engine      │  Self-built artifact
│  Silero VAD → speech regions → gap complement           │  (API-deletion proof)
└─────────────────────────────────────────────────────────┘
      │ gaps + speech regions
      ▼
┌─────────────────────────────────────────────────────────┐
│  Granite Speech 4.1 2B → reference transcript           │  IBM Granite (local)
│  NER-style scorer (N-E-R)/N + trained classifier        │  Self-built + trained ML
└─────────────────────────────────────────────────────────┘
      │ NER score + confidence band
      ▼
┌─────────────────────────────────────────────────────────┐
│  23-rule evaluator engine (FCC / WCAG / DCMP / Netflix) │  Self-built artifact
│  RAG citations: Docling → Granite Embedding r2 → FAISS  │  IBM tools (load-bearing)
└─────────────────────────────────────────────────────────┘
      │ ConformanceReport
      ▼
┌─────────────────────────────────────────────────────────┐
│  SARIF 2.1.0 export + OSCAL POA&M v1.1.2 export        │  Structured reports
└─────────────────────────────────────────────────────────┘
      │ (on failing AD gap click)
      ▼
┌─────────────────────────────────────────────────────────┐
│  Granite Vision → draft description                     │  IBM Granite Vision
│  DCMP structure validator → re-check                   │  Self-built artifact
│  Granite Guardian → safety screen                      │  IBM Granite Guardian
│  → row flips green on timeline                         │
└─────────────────────────────────────────────────────────┘
```

### IBM Stack (every tool is load-bearing)

| IBM Tool | Load-Bearing Role | What Breaks Without It |
|---|---|---|
| **IBM Bob** | Writes ALL product code; subagents (parallel caption/AD/report tasks); custom mode; conformance Skill; Plan specs; two /review audits (SARIF + OSCAL); Bobalytics; self-referential MCP loop | The entry itself; both Bob-named awards |
| **Granite Speech 4.1 2B** | High-accuracy reference transcript feeding the NER scorer | No ASR ground truth for caption accuracy |
| **Granite Vision** | Drafts the AD fix on a failing gap | No generative-fix moment |
| **Granite 4.x language** | Plain-English rule rationales, DCMP language heuristics | Rationales become hardcoded |
| **Granite Guardian** | Screens generated AD before the row flips green | No safety gate on generated content |
| **Granite Embedding r2** | Embeds standards corpus so citations are retrieved, not hardcoded | Citations lose source provenance |
| **Docling** | Parses WCAG/FCC/DCMP/Netflix into the structured knowledge base | No grounded citations; rules hand-typed |
| **watsonx.governance / AI FactSheet** | Model card for the trained classifier documenting data, evaluation, and ASR-disparity bias handling | Loses IBM's celebrated governance story |
| **watsonx.ai Lite** | One hosted showcase inference call | Loses hosted-IBM showcase |

### Four Self-Built Load-Bearing Artifacts (all API-deletion proof)

1. **The conformance rule engine** — NER-style caption scorer (NER = (N-E-R)/N, Romero-Fresco/Ofcom model, 98% broadcast threshold, confidence bands, never auto-fail on ASR alone per Koenecke et al. PNAS 2020)
2. **The dialogue-gap detection and timing engine** — Silero VAD + silence detection, gap complement above 2.5s minimum, merged across sub-300ms blips
3. **The audio-description structure validator** — DCMP structural rules: word-count-fits-gap, no-overlap-with-dialogue, present-tense, active-voice, third-person, complete sentences, objectivity flags
4. **The trained caption error-type classifier** — supervised classifier on hand-labeled data distinguishing recognition errors (ASR mishears) from edition errors (meaning-preserving paraphrase/omission), feeding the NER scorer's E-vs-R decision

## Selected Challenge Theme

**Reimagine Creative Industries with AI** — AccessGate reimagines the post-production accessibility step that determines whether blind and Deaf audiences can experience a film at all. It removes the manual QC bottleneck between a finished film and its full audience.

## How IBM Bob Was Used

| Feature | Bob Mode | Artifact |
|---|---|---|
| Project architecture and plan specs | Plan mode | `plan/accessgate-master-plan.md` |
| Rule engine implementation | Code/Agent mode | `src/evaluators/` |
| Gap detection engine | Code/Agent mode | `src/gap_engine.py` |
| NER scorer + classifier | Code/Agent mode | `src/ner_scorer.py`, `src/classifier.py` |
| RAG layer (Docling + Granite Embedding) | Code/Agent mode | `src/rag.py` |
| Generative fix loop | Code/Agent mode | `src/generative_fix.py` |
| SARIF/OSCAL exporters | Code/Agent mode | `src/exporters/` |
| MCP server (self-referential loop) | Advanced mode + MCP Builder | `src/mcp_server/server.py` |
| Security audit #1 | `/review` (Account A) | `security/review-audit-1.sarif` |
| Security audit #2 | `/review` (Account B) | `security/review-audit-2.oscal.json` |
| Custom mode (accessibility-compliance-engineer) | Settings | `.bob/custom_modes.yaml` |
| Conformance rule-authoring skill | Skills | `.bob/skills/conformance/SKILL.md` |
| Frontend Carbon components | Code/Agent mode | `frontend/src/components/` |

## Build and Run

```bash
# Install dependencies
pip install -r requirements.txt

# Pull Ollama models
ollama pull granite3.2-vision:2b
ollama pull granite3-guardian:2b
ollama pull granite3.2:8b

# Run the conformance engine
python -m src.engine data/demo/notld_segment.mp4 data/demo/notld_broken.srt data/demo/notld_broken_ad.vtt

# Run tests
pytest

# Lint SARIF export
npx @microsoft/sarif-multitool validate output.sarif

# Start the frontend
cd frontend && npm install && npm run dev
```

## Why This Matters in the Context of Creative Industries and Accessibility

ADA Title II compliance deadlines arrive April 26, 2027 (public entities, population 50,000+) and April 26, 2028 (smaller entities). India's Ministry of Information and Broadcasting mandated audio description and closed captions for theatrical films (O.M. 15.03.2024) and OTT platforms (06.02.2026). Netflix auto-QC rejects non-compliant timed-text files before human review. The same self-built rule-engine-plus-gated-fix architecture generalizes to music rights conformance and dubbing QA.

AccessGate is local, open, and API-deletion-proof. The accessibility tool passes its own accessibility audit.

---

## Demo Assets

- **Night of the Living Dead (1968)** — US public domain (published without valid copyright notice). Source: archive.org/details/night-of-the-living-dead_1968. Primary caption-scoring asset.
- **Big Buck Bunny** — CC BY 3.0. Attribution: (c) copyright 2008, Blender Foundation / www.bigbuckbunny.org. AD-gap visual asset.

See [NOTICE](NOTICE) for full third-party attribution.

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
│   ├── generative_fix.py      # Granite Vision -> DCMP -> Guardian fix
│   ├── app.py                 # FastAPI REST server
│   ├── live_monitor.py        # Sliding-window live caption monitor
│   ├── watsonx_showcase.py    # watsonx.ai Lite hosted showcase call
│   ├── evaluators/            # One file per rule family
│   ├── exporters/             # SARIF 2.1.0 + OSCAL POA&M v1.1.2
│   └── mcp_server/            # FastMCP server (self-referential Bob loop)
├── rules/rules_registry.yaml  # 23 rules: FCC / WCAG / DCMP / Netflix
├── standards/                 # Docling-parsed source documents
├── data/
│   ├── demo/                  # notld_broken.srt + notld_broken_ad.vtt
│   └── training/
│       ├── model_card.md      # AI FactSheet for the classifier
│       └── label_schema.md    # Annotation schema
├── frontend/                  # Vite + React + IBM Carbon SPA
├── plan/                      # Bob Plan-mode specs
├── security/                  # SARIF + OSCAL /review audit outputs
├── bob_sessions/              # Exported Bob sessions + Bobalytics
├── tests/                     # 172 passing tests
├── AGENTS.md                  # Project policy spine (read every session)
└── .bob/                      # Custom mode, conformance skill, MCP config
```

---

## SkillsBuild

Every team member has completed an IBM SkillsBuild learning activity.
Certificate documentation is available in `submission/skillsbuild-certificates.pdf`.

---

## License

MIT — see [LICENSE](LICENSE). See [NOTICE](NOTICE) for third-party media and training-data attribution.
