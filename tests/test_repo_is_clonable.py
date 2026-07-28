"""A judge's clone must not be missing something the repo tells them to look at.

Two rival submissions in this challenge were graded down for exactly this class of
defect, so it is worth a test rather than a habit:

  - One shipped a README with an MIT badge and no LICENSE file, and Docker
    instructions naming a service that its own compose profile never starts.
  - One had a bare `models/` line in .gitignore that silently excluded a source
    package from all 36 of its commits. Every documented run path failed on a
    fresh clone with ModuleNotFoundError, and its whole test suite was
    uncollectable, because the directory existed only on the author's machine.

Both are invisible locally and fatal remotely: the author's working tree has the
file, the clone does not. These tests read the repo the way a judge's clone sees
it, through `git ls-files` and `git check-ignore`, never through the filesystem.
"""

import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# Docs a judge is actually pointed at. Anything these reference has to survive a clone.
JUDGE_FACING_DOCS = ["README.md", "AGENTS.md", "bob_sessions/README.md"]


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    ).stdout


def _is_git_checkout() -> bool:
    try:
        _git("rev-parse", "--git-dir")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


needs_git = pytest.mark.skipif(not _is_git_checkout(), reason="not a git checkout")


@needs_git
def test_no_source_directory_is_gitignored():
    """The bare-pattern trap: `models/` also matches `app/models/`.

    Our .gitignore carries bare patterns of the same shape (dist/, build/,
    plan/), so assert directly that nothing under a source root is excluded.
    __pycache__ is expected and allowed.
    """
    offenders = []
    for root in ("src", "frontend/src", "mobile/src", "tests"):
        root_path = REPO_ROOT / root
        if not root_path.is_dir():
            continue
        for d in root_path.rglob("*"):
            if not d.is_dir() or "node_modules" in d.parts or "__pycache__" in d.parts:
                continue
            result = subprocess.run(
                ["git", "check-ignore", "-v", str(d)],
                cwd=REPO_ROOT, capture_output=True, text=True,
            )
            if result.returncode == 0:
                offenders.append(result.stdout.strip())
    assert offenders == [], (
        "a source directory is gitignored, so it is missing from every clone:\n"
        + "\n".join(offenders)
    )


@needs_git
def test_every_python_package_under_src_is_tracked():
    """A package that exists locally but was never committed is the fatal case."""
    tracked = set(_git("ls-files").splitlines())
    missing = [
        str(init.relative_to(REPO_ROOT))
        for init in (REPO_ROOT / "src").rglob("__init__.py")
        if "__pycache__" not in init.parts
        and str(init.relative_to(REPO_ROOT)) not in tracked
    ]
    assert missing == [], f"untracked package markers, absent from any clone: {missing}"


@needs_git
def test_judge_facing_docs_do_not_reference_gitignored_paths():
    """Do not send a judge to a directory their clone will not contain.

    AGENTS.md pointed at `plan/` for Bob's Plan specs while `plan/` is gitignored
    and untracked, so a judge following that line found nothing. Same shape as a
    README promising a LICENSE that was never committed.
    """
    tracked = set(_git("ls-files").splitlines())
    # Two forms, because the real bug was in the second one. AGENTS.md said
    # "Plan specs in plan/" as bare prose, so a backtick-only pattern missed it.
    # Verified by re-running this test against the pre-fix tree: backticks alone
    # passed, which is a test that would have shipped false confidence.
    patterns = [
        re.compile(r"`([A-Za-z0-9_][A-Za-z0-9_./-]*/[A-Za-z0-9_./-]*)`"),  # `src/foo`
        re.compile(r"(?<![\w/`])([a-z][a-z0-9_-]{2,}/)(?![\w`])"),          # bare plan/
    ]
    offenders = []
    for doc in JUDGE_FACING_DOCS:
        doc_path = REPO_ROOT / doc
        if not doc_path.exists():
            continue
        text = doc_path.read_text()
        candidates = {m.rstrip("/") for p in patterns for m in p.findall(text)}
        for candidate in sorted(candidates):
            if candidate.startswith(("http", "~", "/")) or " " in candidate:
                continue
            # Only judge paths that exist here. Anything absent locally is either
            # illustrative or someone else's, and is not this test's business.
            if not (REPO_ROOT / candidate).exists():
                continue
            is_tracked = candidate in tracked or any(
                t.startswith(candidate + "/") for t in tracked
            )
            if not is_tracked:
                offenders.append(f"{doc} references untracked {candidate!r}")
    assert offenders == [], (
        "judge-facing docs point at paths missing from a clone:\n" + "\n".join(offenders)
    )


@needs_git
def test_license_exists_if_the_readme_advertises_one():
    readme = (REPO_ROOT / "README.md").read_text()
    if re.search(r"License:?\s*MIT|MIT License", readme):
        assert (REPO_ROOT / "LICENSE") .exists(), (
            "README advertises an MIT license but no LICENSE file is present"
        )
        assert "LICENSE" in set(_git("ls-files").splitlines())


@needs_git
def test_no_platform_locked_frontend_dependency():
    """A win32-only dep as a hard requirement aborts `npm ci` on a judge's Mac.

    A rival shipped `@next/swc-win32-x64-msvc` as a non-optional dependency, so
    installation failed with EBADPLATFORM before a single file compiled.
    """
    import json

    pkg = json.loads((REPO_ROOT / "frontend" / "package.json").read_text())
    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
    locked = [
        name for name in deps
        if re.search(r"win32|darwin|linux|msvc|-x64|-arm64", name)
    ]
    assert locked == [], f"platform-locked hard dependency breaks other machines: {locked}"
