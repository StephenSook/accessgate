"""
Guards on the recovered Bob attribution evidence.

Two independent risks, both of which have already bitten this repository once:

  1. PUBLISHING TOO MUCH. The Bob store holds the author's verbatim planning
     prompts and absolute filesystem paths carrying a username. A counts-only
     aggregate must be provably counts-only, not counts-only by intention.
  2. THE NUMBERS DRIFTING FROM THE ARTIFACT. bob_sessions/README.md quotes this
     JSON in prose. Today a hero paragraph elsewhere in this repo claimed a
     "44-character line" while the engine reported 45, so the rule now is that
     a number stated in prose is pinned to the artifact it came from.
"""

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
EVIDENCE = REPO_ROOT / "bob_sessions" / "bob-attribution-recovered.json"
README = REPO_ROOT / "bob_sessions" / "README.md"


def _load() -> dict:
    return json.loads(EVIDENCE.read_text())


def test_evidence_file_exists_and_is_tracked():
    """It lives under a `bob_sessions/*.json` ignore rule and needs an exception."""
    assert EVIDENCE.exists(), "recovered attribution evidence is missing"
    import subprocess

    out = subprocess.run(
        ["git", "check-ignore", str(EVIDENCE.relative_to(REPO_ROOT))],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    assert out.returncode != 0, (
        "bob-attribution-recovered.json is gitignored, so a judge's clone would not "
        "receive it. Add a ! exception in .gitignore."
    )


def test_no_absolute_paths_or_username_leak():
    raw = EVIDENCE.read_text()
    assert "/Users/" not in raw, "absolute filesystem path leaked into Bob evidence"
    assert "stephensookra" not in raw.lower(), "username leaked into Bob evidence"


def test_no_contribution_text_or_prompt_bodies():
    """
    The `contribution_text` column and any message body must never be emitted.

    Every string in the payload is either explanatory prose we wrote, a
    repo-relative path, a tool name, a repo/branch, or a timestamp. Code
    fragments would show up as braces, semicolons or import statements in the
    data sections.
    """
    d = _load()
    data_strings = (
        list(d["rows_by_path"]) + list(d["rows_by_tool"]) + d["repositories"] + d["branches"]
    )
    for s in data_strings:
        assert "\n" not in s, f"multi-line value suggests captured content: {s!r}"
        for marker in ("{", "}", ";", "import ", "def ", "const ", "=>"):
            assert marker not in s, f"code fragment leaked into evidence: {s!r}"


def test_paths_are_repo_relative_and_real():
    """
    A recovered path that does not exist in the repo would mean the carve
    misparsed a boundary, which is exactly the bug that first produced
    'App.tsxStephenSook/accessgate' as a repository name.
    """
    d = _load()
    for path in d["rows_by_path"]:
        assert not path.startswith("/"), f"path is absolute: {path}"
        assert (REPO_ROOT / path).exists(), f"recovered path is not a real file: {path}"


def test_repository_and_branch_parsed_cleanly():
    d = _load()
    assert d["repositories"] == ["StephenSook/accessgate"], d["repositories"]
    assert d["branches"] == ["main"], d["branches"]


def test_counts_are_internally_consistent():
    d = _load()
    assert sum(d["rows_by_tool"].values()) == d["attribution_rows_recovered"]
    assert sum(d["rows_by_path"].values()) == d["attribution_rows_recovered"]


def test_readme_numbers_match_the_artifact():
    """
    Pins the prose to the JSON. This is the check that would have caught the
    '11 vs 8' discrepancy this file briefly carried.
    """
    d = _load()
    text = README.read_text()

    for tool, count in d["rows_by_tool"].items():
        row = re.search(rf"\|\s*`{re.escape(tool)}`\s*\|\s*(\d+)\s*\|", text)
        assert row, f"{tool} is not in the README table"
        assert int(row.group(1)) == count, (
            f"README says {row.group(1)} {tool} records, artifact says {count}"
        )

    created = d["runtime_log_events"]["attribution_create"]
    assert f"**{created} `attribution: create` events**" in text, (
        f"README does not state the artifact's attribution_create count ({created})"
    )


def test_completeness_caveat_is_present():
    """
    The carve recovers a floor, not a total. Presenting it as complete would be
    the same overclaim this evidence exists to correct.
    """
    d = _load()
    assert "FLOOR, NOT A TOTAL" in d["completeness"].upper()
