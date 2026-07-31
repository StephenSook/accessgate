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


def test_setup_docs_only_tell_a_judge_to_pull_models_the_code_loads():
    """Do not send someone to download gigabytes the product never touches.

    The setup instructions listed `ollama pull granite3.2:8b` while
    src/generative_fix.py loads only the vision and guardian models. A judge
    following the README spent a multi-gigabyte download on a model no shipped
    code opens. A rival lost points for the same shape of defect: docs that
    instruct something the code does not do.
    """
    code = "\n".join(
        p.read_text() for p in (REPO_ROOT / "src").rglob("*.py")
        if "__pycache__" not in p.parts
    )
    pull = re.compile(r"ollama pull ([a-z0-9.:\- ]+)")
    stale = []
    for doc in ("README.md", "AGENTS.md"):
        text = (REPO_ROOT / doc).read_text()
        for line in pull.findall(text):
            for model in line.split():
                # A model id carries a tag; bare words are prose, not ids.
                if ":" in model and model not in code:
                    stale.append(f"{doc} says pull {model!r}, which no src/ file loads")
    assert stale == [], "\n".join(stale)


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


# ---------------------------------------------------------------------------
# Declared-vs-imported.
#
# Twice now a module that src/ imports DIRECTLY reached a fresh clone only
# transitively, through whichever heavier package happened to pull it in:
# `soundfile` (caught by hand in a repo self-audit) and `requests`, which every
# watsonx call in src/ uses and which requirements.txt never listed. Both work
# on the author's machine and both are one dependency-bump away from a clone
# that cannot import the engine.
#
# Neither was caught by a test, which is why this exists. The hand-audit does
# not survive a tired night before a deadline.
# ---------------------------------------------------------------------------

# import name -> distribution name, where they differ.
_DIST_ALIASES = {
    "sklearn": "scikit-learn",
    "yaml": "pyyaml",
    "webvtt": "webvtt-py",
    "dotenv": "python-dotenv",
    "silero_vad": "silero-vad",
    "faster_whisper": "faster-whisper",
    "sentence_transformers": "sentence-transformers",
    "ffmpeg": "ffmpeg-python",
    "multipart": "python-multipart",
    "PIL": "pillow",
    "cv2": "opencv-python",
}

# Pulled in by a declared package and never imported by name in src/, or part of
# the standard library in the versions we support.
_STDLIB_OK = {
    "__future__", "abc", "argparse", "base64", "binascii", "collections",
    "contextlib", "copy", "csv", "dataclasses", "datetime", "difflib", "enum",
    "functools", "glob", "hashlib", "html", "io", "itertools", "json",
    "logging", "math", "os", "pathlib", "pickle", "random", "re", "shutil",
    "statistics", "string", "struct", "subprocess", "sys", "tempfile",
    "textwrap", "threading", "time", "traceback", "types", "typing",
    "unicodedata", "urllib", "uuid", "warnings", "wave", "xml", "zipfile",
    "concurrent", "email", "http", "socket", "ssl", "signal", "inspect",
    "importlib", "unittest", "asyncio", "queue", "secrets", "shlex", "stat",
    "gzip", "tarfile", "platform", "getpass", "operator", "bisect", "heapq",
    "decimal", "fractions", "numbers", "array", "weakref", "gc", "atexit",
    "codecs", "locale", "calendar", "zoneinfo", "sqlite3", "ctypes",
}


def _declared_distributions(*files: str) -> set[str]:
    """Distributions declared by the named requirements files.

    Defaults to requirements.txt ALONE, deliberately. Unioning it with
    requirements-deploy.txt was the first version of this helper and it made the
    assertion nearly vacuous: deleting `requests` from requirements.txt still
    passed, because the deploy subset happened to list it too. But
    requirements.txt is the full local stack the README tells a judge to
    install, so a module reachable only through the deploy subset is exactly the
    gap this is meant to catch.
    """
    declared: set[str] = set()
    for name in (files or ("requirements.txt",)):
        path = REPO_ROOT / name
        if not path.exists():
            continue
        for raw in path.read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            # strip extras and version pins: uvicorn[standard]>=0.34.0
            dist = re.split(r"[\[<>=!~; ]", line, maxsplit=1)[0]
            if dist:
                declared.add(dist.lower().replace("_", "-"))
    return declared


def _top_level_imports_in_src() -> set[str]:
    """Top-level module names src/ imports, including guarded ones.

    Parsed with `ast`, not a regex. The regex version of this scan reported a
    module named "the", because a docstring line beginning "from the ..." is
    indistinguishable from an import statement to a pattern that only looks at
    the start of a line. A checker that cries wolf on prose gets muted, and a
    muted checker protects nothing.

    Guarded imports count. `soundfile` sat inside a try and was still a real
    missing dependency the moment a judge set the flag that reaches it.
    """
    import ast

    found: set[str] = set()
    for path in (REPO_ROOT / "src").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import):
                found |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                # level > 0 is a relative import: our own code, not a package.
                if node.level == 0 and node.module:
                    found.add(node.module.split(".")[0])
    return found


def test_the_import_scan_is_not_vacuous():
    """A proof that cannot fail wears the credibility of one that can."""
    imports = _top_level_imports_in_src()
    assert len(imports) >= 15, f"import scan found almost nothing: {imports}"
    assert "requests" in imports, "expected src/ to import requests directly"
    assert len(_declared_distributions()) >= 10, "requirements parse looks broken"


def test_every_module_src_imports_directly_is_declared():
    """The load-bearing assertion."""
    declared = _declared_distributions()
    undeclared = []
    for module in sorted(_top_level_imports_in_src()):
        if module in _STDLIB_OK or module == "src":
            continue
        dist = _DIST_ALIASES.get(module, module).lower().replace("_", "-")
        if dist not in declared:
            undeclared.append(f"{module} (would need {dist!r})")
    assert undeclared == [], (
        "src/ imports these directly but no requirements file declares them, so a "
        "clone gets them only transitively, if at all:\n  " + "\n  ".join(undeclared)
    )
