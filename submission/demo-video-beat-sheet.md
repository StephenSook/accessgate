# AccessGate — Demo Video Beat Sheet

**Target:** 3 minutes maximum. Record on Mac (Cmd-Shift-5 or OBS). Upload as PUBLIC YouTube video.

---

## Beat-by-Beat Script

### 0:00 - 0:20 — HOOK (the human harm)

**Narration:**
"At Sundance 2026, only 16 of 90 films were watchable if you are blind. A blind viewer watching one of the other 74 films would experience this:"

**Screen:** Play 4-5 seconds of NOTLD with audio description VTT removed. Screen goes visually silent.

"That's the gap AccessGate was built to fix — before the film ships."

---

### 0:20 - 0:50 — THE BUYER AND THE HARM

**Narration:**
"Festivals and distributors reject non-compliant sidecar files using automated QC pipelines. Manual QC costs 9 to 14 dollars per minute. ADA Title II compliance deadlines arrive April 2027."

**Screen:** Show the notld_broken.srt and notld_broken_ad.vtt files side by side.

"These are the broken files we planted 10 violations into. Let's run the check."

---

### 0:50 - 1:40 — THE ENGINE (technical depth moment)

**Screen:** Drag notld_broken.srt into AccessGate frontend. Click RUN CHECK. Report appears.

**Narration:**
"AccessGate scored 23 rules across four standards: FCC 47 CFR 79.1(j)(2), WCAG 2.2, the DCMP Captioning Key, and the Netflix delivery profile. Every flag cites the exact standard text it came from — retrieved at runtime from a Granite Embedding index, never hardcoded."

**Screen:** Click DCMP-CAP-03 row to expand — show the verbatim citation in the blockquote.

"And the NER caption score: 94.1 percent, with a confidence band — flagged for human review, never auto-failed. Because ASR carries measured racial disparity that makes a hard fail unjust."

---

### 1:40 - 2:20 — THE GATED FIX (demo centerpiece, MUST LAND)

**Screen:** Click a failing gap on the conformance timeline. The GatedFixPanel slides in.

**Narration:**
"Click a failing audio-description gap on the timeline."

**Screen:** Click GENERATE FIX. Show the three-stage card animate through.

"Granite Vision drafts a description sized to fit the silent window. The DCMP structure validator re-checks it. Granite Guardian screens it for content safety. All three pass — and the row flips green."

**Screen:** Row turns green on the timeline.

"Delete every hosted AI API. The engine still runs and still produces a report. The same four self-built artifacts: the rule engine, the gap detector, the AD validator, and the trained caption classifier — all API-deletion proof."

---

### 2:20 - 2:40 — IBM BOB EVIDENCE (the meta-differentiator)

**Screen:** Show .bob/custom_modes.yaml + .bob/skills/conformance/SKILL.md in the editor.

**Narration:**
"Every line of product code was written through IBM Bob. We used a custom accessibility-compliance-engineer mode, a DCMP/FCC/Netflix rule-authoring skill, Plan-mode specs committed to the repo, two slash-review audits emitting SARIF and OSCAL, and the self-referential MCP loop — the product's own MCP server consumed by Bob during development."

**Screen:** Show security/review-audit-1.sarif and security/review-audit-2.oscal.json. Show Bobalytics screenshot.

---

### 2:40 - 3:00 — IMPACT AND HONEST CLAIM

**Screen:** Show the axe-core badge in the app header: A11Y 100%.

**Narration:**
"The accessibility tool passes its own accessibility audit."

**Screen:** Pull back to show the full app.

"AccessGate: conformance pre-check plus human-judgment flags. Local, open-source, and API-deletion-proof. github.com/StephenSook/accessgate."

---

## Pre-Recording Checklist

- [ ] Pre-generate the AD fix for the NOTLD gap at 67.2s-73.8s (run `python -m src.generative_fix`) so the demo is instant
- [ ] Verify Ollama is running: `ollama list` shows all 3 models
- [ ] Start FastAPI: `python -m uvicorn src.app:app --reload --port 8000`
- [ ] Start frontend dev server: `cd frontend && npm run dev`
- [ ] Open http://localhost:5173 in a clean Chrome window (no extensions)
- [ ] Have notld_broken.srt and notld_broken_ad.vtt ready on desktop for drag-drop
- [ ] Screen resolution: 1920x1080, browser zoom at 100%
- [ ] Record at 1080p60 for clean export
- [ ] Add captions to the final video (requirement: demo video must be captioned for an accessibility project)
- [ ] Set YouTube visibility to PUBLIC (not private, not unlisted — verify in incognito)

## After Recording

1. Trim to exactly 3:00 or under.
2. Add closed captions (YouTube auto-captions, then correct).
3. Title: "AccessGate — Film Accessibility Conformance Pre-Check (IBM AI Builders Challenge July 2026)"
4. Description: include GitHub URL and a one-paragraph summary.
5. Copy the YouTube URL into the BeMyApp submission form.
