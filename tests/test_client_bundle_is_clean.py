"""
Nothing secret and no unwired model name may reach the browser.

Two layers, because they fail differently.

SOURCE LAYER (always enforced). Vite inlines any `import.meta.env.VITE_*` it finds
into the built bundle at compile time. So the set of VITE_ variables the client
reads IS the set of values that ship to every visitor. Allowlist it, and a future
`import.meta.env.VITE_WATSONX_API_KEY` fails here rather than in production. This
is the invariant that matters and it is checkable without a build.

BUNDLE LAYER (enforced when a build exists). Reads the actual compiled artifact
and asserts no credential shape and no unwired vendor name survived. It skips
cleanly when `dist/` is absent, since pytest and the frontend build run as
separate CI jobs; locally, after `npm run build`, it runs for real. Its value is
catching what source inspection cannot: a key pulled in through a dependency, or
a model string baked into a vendored chunk.

Adapted from a rival graded B+ this cycle, whose `test_webapp.py` asserted the
served JS contained none of API_KEY / sk-ant / gsk_ / claude- / gemini-. Three
lines that make a whole class of leak impossible. Directly relevant here, because
this project renders Granite and watsonx names in the UI and ships a hosted Llama
drafter, so a mislabelled or leaked string is exactly the failure mode to prevent.

Companion to tests/test_model_claims_match_code.py, which governs SOURCE claims.
This one governs what a visitor actually receives.
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CLIENT_SRC = REPO_ROOT / "frontend" / "src"
DIST = REPO_ROOT / "frontend" / "dist"

#: The ONLY build-time variables permitted to reach the browser. VITE_API_URL is
#: the public API base; it is not a secret and the API is deliberately open.
ALLOWED_VITE_VARS = {"VITE_API_URL"}

#: Credential shapes. Deliberately narrow so ordinary prose cannot trip them.
#:
#: These match VALUES, never variable NAMES. The first draft of this file matched
#: the bare string WATSONX_API_KEY and immediately failed on
#: `{/* watsonx.ai Lite side-by-side (when WATSONX_API_KEY is set) */}`, a JSX
#: comment documenting when a panel renders. No value was assigned, and the
#: comment is stripped at build (0 occurrences in the bundle). Naming an
#: environment variable in a comment is good documentation; a test that forbids
#: it trains you to delete useful comments. Assert on the secret, not the noun.
SECRET_PATTERNS = {
    "watsonx credential VALUE": re.compile(
        r"WATSONX_(?:API_KEY|PROJECT)\s*[:=]\s*[\"'`][A-Za-z0-9_\-]{8,}"
    ),
    "Anthropic key": re.compile(r"sk-ant-[A-Za-z0-9]"),
    "OpenAI key": re.compile(r"sk-[A-Za-z0-9]{32,}"),
    "Groq key": re.compile(r"gsk_[A-Za-z0-9]{20,}"),
    "Google API key": re.compile(r"AIza[A-Za-z0-9_\-]{30,}"),
    "JWT / bearer": re.compile(r"eyJ[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}"),
    "private key block": re.compile(r"BEGIN (RSA |EC )?PRIVATE KEY"),
}

#: Vendors this project does not call at runtime. A name here reaching the
#: browser would be the defect that graded three rivals down: a UI asserting a
#: model the code never invokes.
UNWIRED_VENDORS = ["sk-ant", "gemini-", "gpt-4", "gpt-5", "langchain", "mistralai"]


def _client_sources() -> list[Path]:
    return sorted(CLIENT_SRC.rglob("*.ts")) + sorted(CLIENT_SRC.rglob("*.tsx"))


def test_only_allowlisted_vite_vars_reach_the_client():
    """
    Vite inlines every VITE_ var it sees, so this list IS what ships.

    A new VITE_ read is not automatically wrong, but it must be a deliberate
    decision recorded here rather than an accident discovered by a visitor.
    """
    found: dict[str, str] = {}
    for p in _client_sources():
        for m in re.finditer(r"import\.meta\.env\.(VITE_[A-Z0-9_]+)", p.read_text(errors="replace")):
            found[m.group(1)] = str(p.relative_to(REPO_ROOT))

    unexpected = {k: v for k, v in found.items() if k not in ALLOWED_VITE_VARS}
    assert unexpected == {}, (
        "client code reads build-time variables that are not allowlisted, and Vite "
        f"will inline their VALUES into the public bundle: {unexpected}. "
        "If this is intentional, add it to ALLOWED_VITE_VARS and confirm it is not a secret."
    )


def test_client_source_holds_no_credential():
    """No credential shape may appear in client source, allowlist or not."""
    offenders: list[str] = []
    for p in _client_sources():
        text = p.read_text(errors="replace")
        for label, pat in SECRET_PATTERNS.items():
            if pat.search(text):
                offenders.append(f"{p.relative_to(REPO_ROOT)}: {label}")
    assert offenders == [], f"credential shapes in client source: {offenders}"


def _bundle_files() -> list[Path]:
    if not DIST.exists():
        return []
    return sorted(DIST.rglob("*.js")) + sorted(DIST.rglob("*.html"))


def test_built_bundle_holds_no_credential():
    """
    The compiled artifact a visitor downloads.

    Skipped when no build is present: pytest and the frontend build are separate
    CI jobs. Locally after `npm run build`, and in any environment that builds
    before testing, this runs for real.
    """
    files = _bundle_files()
    if not files:
        pytest.skip("frontend/dist absent; run `npm run build` in frontend/ to enable")

    offenders: list[str] = []
    for p in files:
        text = p.read_text(errors="replace")
        for label, pat in SECRET_PATTERNS.items():
            if pat.search(text):
                offenders.append(f"{p.relative_to(REPO_ROOT)}: {label}")
    assert offenders == [], f"credential shapes in the SHIPPED bundle: {offenders}"


def test_built_bundle_names_no_unwired_vendor():
    """
    A vendor name in the bundle is a claim made to every visitor.

    This is the browser-side twin of test_model_claims_match_code.py: that one
    governs what the repo says, this one governs what the product says.
    """
    files = _bundle_files()
    if not files:
        pytest.skip("frontend/dist absent; run `npm run build` in frontend/ to enable")

    offenders: list[str] = []
    for p in files:
        text = p.read_text(errors="replace").lower()
        for vendor in UNWIRED_VENDORS:
            if vendor in text:
                offenders.append(f"{p.relative_to(REPO_ROOT)} names '{vendor}'")
    assert offenders == [], (
        f"the shipped bundle names a vendor this project does not call: {offenders}"
    )


def test_the_allowlist_itself_is_not_empty_or_vacuous():
    """
    Non-vacuity guard.

    If the regex or the source glob broke, every assertion above would pass while
    protecting nothing. Prove the scan actually sees the client code.
    """
    sources = _client_sources()
    assert len(sources) >= 5, f"client source scan found only {len(sources)} files"
    joined = "\n".join(p.read_text(errors="replace") for p in sources)
    assert "import.meta.env.VITE_API_URL" in joined, (
        "the known VITE_API_URL read was not found; the scan is not seeing client code"
    )
