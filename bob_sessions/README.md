# bob_sessions

Evidence that IBM Bob was the primary development tool for AccessGate, and an
honest account of which parts of that evidence are in this repo and which are not.

## The build trace (the part you can verify yourself)

Bob authored the engine core on **2026-07-13, 19:53 to 20:40 ET**: eight commits,
47 minutes, first data model to a running FastAPI service with a generative fix
loop. The test count is carried in each commit subject, so the trace re-derives
from a clone with no trust required:

```bash
git log --reverse --format='%ad %s' --date=format:'%H:%M'
```

| Time (ET) | Commit | Subject | Tests |
|---|---|---|---|
| 19:40 | `539905e` | repo foundation, Bob artifacts, rule registry, README, AGENTS.md | - |
| 19:53 | `d825caf` | data models, rule registry loader | 6 |
| 19:57 | `c08b279` | caption parser (SRT+VTT) | 9 |
| 19:58 | `2bb704e` | VAD gap engine + NER scorer | 22 |
| 20:09 | `14c1b7f` | all 23 rule evaluators, degradation recipe verified | 108 |
| 20:23 | `afda272` | trained caption error-type classifier, macro-F1 0.952 | 108 |
| 20:34 | `69d24f9` | RAG layer (Granite Embedding), main engine, SARIF/OSCAL exporters | 154 |
| 20:40 | `df1a5df` | generative fix loop (Vision + DCMP + Guardian), MCP server, FastAPI | 172 |

37 commits landed that day. Bob credits ran out later on 2026-07-13, which is why
commits after this window shift to deployment, the Granite Speech wiring, and
honesty and UI refinements finished with other tooling. Bob was the **primary**
development tool, not the exclusive one, which is what the July rules require.

The same trace is served as structured JSON at `/judges` under `bob_usage`.

## Evidence chain

| Evidence item | Location | Status |
|---|---|---|
| Custom mode (`accessibility-compliance-engineer`) | `.bob/custom_modes.yaml` | committed |
| Conformance rule-authoring skill | `.bob/skills/conformance/SKILL.md` | committed |
| /review audit 1 (SARIF, `tool.driver.name` is `IBM Bob`) | `security/review-audit-1.sarif` | committed |
| /review audit 2 (OSCAL POA&M) | `security/review-audit-2.oscal.json` | committed |
| Self-referential MCP config | `.bob/mcp.json` | committed |
| Bobalytics usage screenshot | `bob_sessions/bobalytics-usage.png` | committed |
| Engine build trace | git history, 2026-07-13 19:53 to 20:40 ET | committed |
| Bob session transcripts | not available, see below | not in repo |

## Why there are no session exports

Bob keeps conversation history **server-side**, not on disk. Its local
application storage (`~/Library/Application Support/IBM Bob/User/globalStorage/`)
contains feature flags, login state and editor state, and its extension storage
directory is empty. There is no local task or session store to export from, so
no `session-*.json` file exists to commit.

This directory previously listed session exports as "pending export", which
implied a file was coming. It is not, and the git build trace above is the
better evidence anyway: a judge can re-derive it from a clone instead of trusting
a document we exported about ourselves.

## Scope note on the self-referential MCP loop

`.bob/mcp.json` registers AccessGate's own MCP server with Bob and pre-authorises
all three tools (`check_conformance`, `detect_gaps`, `score_captions`), and the
server itself is at `src/mcp_server/server.py`. Both halves are in this repo.
What is **not** in this repo is a transcript of Bob invoking those tools, for the
reason above. The honest reading is a wired capability, not a logged event.
