#!/usr/bin/env python3
"""
Recover IBM Bob's own line-level attribution records, and emit a sanitized aggregate.

WHY THIS EXISTS. Bob records its own edits in an `attribution_logs` table keyed by
file URI, repository, branch and the tool it used. That is the strongest available
proof of authorship on this project, because it is the tool logging itself rather
than anyone describing it afterwards.

On 2026-07-29 a machine crash restarted the Bob IDE and the local session store
came back empty. The database was never vacuumed, so the deleted rows still sit in
freed SQLite pages. This script carves them back out.

WHAT IT DELIBERATELY DOES NOT PUBLISH. The same rule as
`export_bob_evidence.py`: counts and shapes, never content.
  - Absolute paths are stripped to repository-relative form, so the author's
    username never reaches the repo (`tests/test_repo_is_clonable.py` enforces this).
  - The `contribution_text` column, the actual code Bob wrote, is NOT emitted. It
    is already in the repository as code; duplicating it here would add nothing and
    risks carrying fragments of surrounding context.
  - Nothing from `messages` is touched, so no planning prompts can leak.

HONESTY NOTE CARRIED INTO THE OUTPUT. Carving recovers what survived in freed
pages, which is a FLOOR and not a total. Bob's runtime logs record more attribution
events than the number of rows recoverable here, and the output says so rather than
presenting the carved count as complete.

Usage:  python scripts/recover_bob_attribution.py [--write]
Without --write it prints the aggregate and changes nothing.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BOB_DB = Path.home() / ".bob" / "db" / "bob.db"
BOB_LOGS = Path.home() / ".bob" / "logs"
OUT = REPO_ROOT / "bob_sessions" / "bob-attribution-recovered.json"

# The columns are stored adjacently with NO delimiter:
#     <id><file_uri><repo_name><branch_name><tool_name>
# so the parse has to be anchored on something unambiguous. A non-greedy URI is
# not enough: it lets the trailing filename bleed into the repo group, which
# yields nonsense like "App.tsxStephenSook/accessgate". Anchoring the URI to a
# source-file extension fixes the boundary, because every attributed path ends
# in one and a repo name never does.
ROW_RE = re.compile(
    r"(?P<uri>file:///\S*?\.(?:tsx|ts|jsx|js|py|json|md|ya?ml|css|html|toml|txt))"
    r"(?P<repo>[A-Za-z0-9_-]+/[A-Za-z0-9_.-]+?)"
    r"(?P<branch>main|master)"
    r"(?P<tool>[a-z_]+)"
)

KNOWN_TOOLS = {
    "apply_diff",
    "search_and_replace",
    "spawn_subagent",
    "write_to_file",
    "insert_content",
    "edit_file",
}


def _rel(uri: str) -> str | None:
    """Repository-relative path, or None if the URI is outside this repo."""
    marker = "IBM%20July/"
    if marker not in uri:
        return None
    tail = uri.split(marker, 1)[1]
    # %20 is the only escape that appears in these paths.
    tail = tail.replace("%20", " ")
    return tail or None


def carve_rows(db: Path) -> list[dict]:
    """Carve attribution rows out of a COPY of the database. Never writes to it."""
    if not db.exists():
        return []
    with tempfile.TemporaryDirectory() as td:
        copy = Path(td) / "bob.db"
        shutil.copy2(db, copy)
        for suffix in ("-wal", "-shm"):
            side = db.with_name(db.name + suffix)
            if side.exists():
                shutil.copy2(side, copy.with_name(copy.name + suffix))
        raw = subprocess.run(
            ["strings", "-n", "20", str(copy)],
            capture_output=True, text=True, check=False,
        ).stdout

    rows: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for m in ROW_RE.finditer(raw):
        tool = m.group("tool")
        # Carved text runs on, so a tool name may have trailing bytes glued to it.
        tool = next((t for t in KNOWN_TOOLS if tool.startswith(t)), None)
        if tool is None:
            continue
        rel = _rel(m.group("uri"))
        if rel is None:
            continue
        key = (rel, tool)
        if key in seen:
            continue
        seen.add(key)
        rows.append({"path": rel, "repo": m.group("repo"), "branch": m.group("branch"), "tool": tool})
    return rows


def log_event_counts(logs_dir: Path) -> dict:
    """
    Count attribution events in Bob's runtime logs.

    The logs survived the wipe. Only event counts and the time window are read;
    no message content is touched.
    """
    out = {"attribution_create": 0, "attribution_index": 0, "log_files": 0,
           "first_ts": None, "last_ts": None, "task_ids": 0}
    if not logs_dir.exists():
        return out
    tasks: set[str] = set()
    stamps: list[str] = []
    for path in sorted(logs_dir.rglob("*.log")):
        out["log_files"] += 1
        for line in path.read_text(errors="replace").splitlines():
            try:
                rec = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            mod = rec.get("module", "")
            if mod == "attribution: create":
                out["attribution_create"] += 1
            elif mod == "attribution: index":
                out["attribution_index"] += 1
            if rec.get("taskId"):
                tasks.add(rec["taskId"])
            if rec.get("ts"):
                stamps.append(rec["ts"])
    out["task_ids"] = len(tasks)
    if stamps:
        out["first_ts"], out["last_ts"] = min(stamps), max(stamps)
    return out


def build(rows: list[dict], logs: dict) -> dict:
    by_tool = Counter(r["tool"] for r in rows)
    by_path = Counter(r["path"] for r in rows)
    repos = sorted({r["repo"] for r in rows})
    branches = sorted({r["branch"] for r in rows})
    return {
        "note": (
            "IBM Bob's own line-level attribution records for this repository, recovered "
            "from freed pages of the Bob IDE's local session database after a crash-restart "
            "emptied it on 2026-07-29. Bob writes these rows itself when it edits a file, so "
            "they are the tool logging its own authorship rather than a description of it. "
            "Counts and repository-relative paths only: the contribution_text column (the code "
            "Bob wrote) is deliberately excluded, because that code is already in this "
            "repository. Regenerate with scripts/recover_bob_attribution.py."
        ),
        "source": "freed pages of ~/.bob/db/bob.db, plus event counts from ~/.bob/logs/",
        "recovered_at": datetime.now(timezone.utc).isoformat(),
        "repositories": repos,
        "branches": branches,
        "attribution_rows_recovered": len(rows),
        "rows_by_tool": dict(sorted(by_tool.items(), key=lambda kv: -kv[1])),
        "rows_by_path": dict(sorted(by_path.items(), key=lambda kv: -kv[1])),
        "runtime_log_events": logs,
        "completeness": (
            "A FLOOR, NOT A TOTAL. Carving recovers only what survived in freed pages, and "
            "Bob's runtime logs record more attribution events than there are rows recoverable "
            "here. Treat this as corroboration of the git build trace, which is the primary "
            "evidence and re-derives from a clone with no trust required."
        ),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="write the aggregate to bob_sessions/")
    args = ap.parse_args()

    rows = carve_rows(BOB_DB)
    logs = log_event_counts(BOB_LOGS)
    payload = build(rows, logs)

    if not rows and not logs["log_files"]:
        print("No Bob attribution data found on this machine. Nothing written.", file=sys.stderr)
        return 1

    text = json.dumps(payload, indent=2) + "\n"
    if args.write:
        OUT.write_text(text)
        print(f"wrote {OUT.relative_to(REPO_ROOT)}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
