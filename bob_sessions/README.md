# bob_sessions

This directory holds exported IBM Bob session evidence for the AccessGate
project: the sessions in which Bob authored the conformance engine, the review
audits, and the Plan-mode specs.

## Contents

### Bobalytics (usage evidence)

Screenshots of the Bobalytics usage dashboard for the build sessions.
Format: `bobalytics-YYYY-MM-DD.png`

### Session exports

Bob sessions exported from the IBM Bob IDE.
Format: `session-YYYY-MM-DD-taskN-description.json`

Key sessions to export:
- The Task 2-12 build sessions (product code written through Bob)
- The two /review audit sessions
- The Plan-mode sessions for the conformance engine and gap-detection specs

---

## Evidence chain summary

| Evidence item | Location | Status |
|---|---|---|
| Custom mode | `.bob/custom_modes.yaml` | committed |
| Conformance skill | `.bob/skills/conformance/SKILL.md` | committed |
| Review audit 1 (SARIF) | `security/review-audit-1.sarif` | committed |
| Review audit 2 (OSCAL) | `security/review-audit-2.oscal.json` | committed |
| Self-referential MCP config | `.bob/mcp.json` | committed |
| Bobalytics screenshots | `bob_sessions/*.png` | pending capture |
| Session exports | `bob_sessions/session-*.json` | pending export |

---

## How to capture Bobalytics

1. Open the IBM Bob IDE.
2. Open the Bobalytics usage dashboard.
3. Screenshot the build session.
4. Save as `bobalytics-YYYY-MM-DD.png` in this directory.
