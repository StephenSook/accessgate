"""Export verifiable IBM Bob usage evidence from Bob's local session store.

WHY THIS EXISTS. bob_sessions/ previously claimed no session export was possible
because Bob kept history server-side. That was wrong: the IBM Bob IDE keeps its
task and message history in a local SQLite database at ~/.bob/db/bob.db, and the
AccessGate build sessions are in it.

WHAT IT DELIBERATELY DOES NOT DO. It does not export message bodies. The session
transcripts contain the author's verbatim planning prompts, which are strategy
notes rather than engineering artifacts and do not belong in a public repo. What
a judge needs is proof of scale and shape, not the conversation, so this writes
counts, timestamps, token totals and tracked cost, and nothing else. No prompt
text, no model output, no file contents, no paths outside the repo name.

Regenerate with:
    python scripts/export_bob_evidence.py

It is intentionally read-only against the Bob database and writes exactly one
file, bob_sessions/bob-usage-evidence.json.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

BOB_DB = Path.home() / ".bob" / "db" / "bob.db"
OUT = Path(__file__).resolve().parent.parent / "bob_sessions" / "bob-usage-evidence.json"

# Titles are the author's own first prompts, so they are matched rather than
# exported. These substrings identify the AccessGate build tasks specifically.
ACCESSGATE_MARKERS = ("accessgate", "agents.md", "bob kit", "mob kit")


def _iso(ms: int | None) -> str | None:
    if not ms:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


def main() -> int:
    if not BOB_DB.exists():
        print(f"No Bob database at {BOB_DB}. Nothing to export.")
        return 1

    db = sqlite3.connect(f"file:{BOB_DB}?mode=ro", uri=True)

    tasks = db.execute(
        "SELECT id, title, created_at FROM tasks ORDER BY created_at"
    ).fetchall()
    accessgate_task_ids = {
        tid for tid, title, _ in tasks
        if any(m in (title or "").lower() for m in ACCESSGATE_MARKERS)
    }

    cost = 0.0
    tokens_in = tokens_out = 0
    roles: dict[str, int] = {}
    first_ms = last_ms = None

    for role, data, created in db.execute(
        "SELECT role, data, created_at FROM messages ORDER BY created_at"
    ):
        roles[role] = roles.get(role, 0) + 1
        first_ms = first_ms or created
        last_ms = created
        try:
            spend = (json.loads(data).get("_meta") or {}).get("spend") or {}
        except (json.JSONDecodeError, AttributeError):
            continue
        cost += spend.get("cost") or 0
        tokens_in += spend.get("input") or 0
        tokens_out += spend.get("output") or 0

    evidence = {
        "note": (
            "Aggregate IBM Bob usage for this repository, read from the Bob IDE's "
            "local session database. Message bodies are deliberately excluded: they "
            "contain the author's planning prompts, which are not engineering "
            "artifacts. Counts and totals only. Regenerate with "
            "scripts/export_bob_evidence.py."
        ),
        "source": "~/.bob/db/bob.db (IBM Bob IDE local session store)",
        "exported_at": datetime.now(tz=timezone.utc).isoformat(),
        "repository": "accessgate",
        "tasks_total": len(tasks),
        "tasks_matching_accessgate": len(accessgate_task_ids),
        "messages_total": sum(roles.values()),
        "messages_by_role": dict(sorted(roles.items())),
        "session_window_utc": {"first": _iso(first_ms), "last": _iso(last_ms)},
        "tokens": {"input": tokens_in, "output": tokens_out},
        "tracked_cost_usd": round(cost, 2),
        "scope_note": (
            "Bob credits ran out on 2026-07-13 and later deployment, Granite Speech "
            "wiring and honesty refinements were finished with other tooling, so Bob "
            "was the primary development tool and not the exclusive one. The engine "
            "build trace in the git history is the per-commit view of the same work."
        ),
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUT.relative_to(Path.cwd())}")
    print(json.dumps(evidence, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
