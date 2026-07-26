# IBM Bob usage log

An explicit, honest record of how IBM Bob was used to build AccessGate, for the
"Use of IBM Bob" judging axis. The claim is Bob as **primary, not exclusive**:
Bob authored the load-bearing product; a few late tasks were finished with other
tooling after Bob credits ran out, and that boundary is stated plainly below. The
same breakdown is served live at the `/judges` endpoint (accelerator tier).

## What Bob authored (primary)

| Area | Bob's contribution | Approx size |
|---|---|---|
| Conformance engine | The 23 rule evaluators, the NER-style caption scorer, the Silero VAD gap engine, and the SARIF/OSCAL exporters | ~4,900 lines across `src/` |
| Test suite | The pytest suite that cold-clone-verifies the engine | 195 tests, ~2,000 lines in `tests/` |
| Frontend | The React + Carbon web client (timeline, rule table, NER meter, gap markers) | ~2,400 lines |

## Bob features used (not just chat)

- **Custom mode** `accessibility-compliance-engineer` — `.bob/custom_modes.yaml`
- **Rule-authoring Skill** for DCMP / FCC / WCAG / Netflix conformance rules — `.bob/skills/conformance/SKILL.md`
- **Plan mode** — specs written before implementation for the engine and the gated fix loop
- **Parallel subagents** — used to build and review independent rule families concurrently
- **Two `/review` audits**, exported as machine-readable artifacts — `security/review-audit-1.sarif`, `security/review-audit-2.oscal.json`
- **Self-referential MCP loop** — Bob consumed AccessGate's own MCP server (`check_conformance`, `detect_gaps`, `score_captions`) during development, so the tool was dogfooded through Bob itself — `.bob/mcp.json`, `src/mcp_server/server.py`

## Honest boundary (finished with other tooling)

After Bob credits ran out, these were completed with other tooling: production
deployment (Render + Vercel + Expo), the Granite Speech reference wiring, the iOS
TestFlight / Android APK builds, later UI and honesty-page refinements, and the
editor-native exporters plus the `/judges` demo-transparency disclosure. None of
this changes that Bob authored the core engine, tests, and frontend; it is why the
claim is "primary," not "exclusive."

## Verify it

Every pointer above is a real file a judge can open in the repo, and the live
`/judges` endpoint returns the same accelerator-tier list. Nothing here is a badge.
