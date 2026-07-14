# bob_sessions

This directory holds exported IBM Bob session evidence for the AccessGate project.

## Contents

### Bobalytics (spend evidence)

Screenshots of Bobalytics usage dashboards go here once captured.  
Format: `bobalytics-YYYY-MM-DD-accountN.png`

Files to add:
- `bobalytics-2026-07-17-account1.png` — primary builder account
- `bobalytics-2026-07-17-account2.png` — secondary account (used for review audit 2)

### Session exports

Bob sessions exported from the IBM Bob IDE go here.  
Format: `session-YYYY-MM-DD-taskN-description.json`

Key sessions to export and commit:
- The Task 2-12 build sessions (all product code written through Bob)
- The two /review audit sessions (one per account)
- The Plan-mode sessions for the conformance engine and gap detection specs

---

## Evidence chain summary

| Evidence item | Location | Status |
|---|---|---|
| Custom mode | `.bob/custom_modes.yaml` | committed |
| Conformance skill | `.bob/skills/conformance/SKILL.md` | committed |
| Plan-mode specs | `plan/accessgate-master-plan.md` | committed |
| Review audit 1 (SARIF) | `security/review-audit-1.sarif` | committed |
| Review audit 2 (OSCAL) | `security/review-audit-2.oscal.json` | committed |
| Self-referential MCP config | `.bob/mcp.json` | committed |
| Bobalytics screenshots | `bob_sessions/*.png` | pending capture |
| Session exports | `bob_sessions/session-*.json` | pending export |

---

## How to capture Bobalytics

1. Open IBM Bob IDE.
2. Navigate to Bobalytics dashboard (usage analytics).
3. Screenshot the current session showing per-mode coin usage.
4. Save as `bobalytics-YYYY-MM-DD-accountN.png` in this directory.
5. `git add bob_sessions/bobalytics-*.png && git commit -m "docs(bob): add Bobalytics screenshots for judging evidence"`
