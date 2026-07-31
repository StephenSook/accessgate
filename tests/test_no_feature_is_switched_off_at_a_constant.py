"""
No claimed feature may be disabled by a constant while the claim still stands.

WHY THIS TEST EXISTS, and why the existing claim-drift test is not enough.

A rival graded D+ this cycle ships this line:

    const AI_PROCESS_COUNT = 0;   // route.ts:72

with a comment directly above it reading, in translation, "change to 1 if you
want feed enrichment active again (needs extra Groq quota or paid Gemini)". Two
lines later, `papers.slice(0, AI_PROCESS_COUNT)` yields an empty list, so every
AI-generated summary, key result, fun fact and concept diagram their submission
advertises is dead for every real item. A live run returns `ai_processed: null`
on every card. The README, the UI and the submission all still claim the
features.

Nothing was faked. The model call is real and correct and sits right there in
the source. It simply never executes.

That is precisely why this needed a second test. Our claim-drift suite
(tests/test_model_claims_match_code.py) asserts that every model named on a
judge-facing surface appears in code we actually call. **It would PASS on this
rival**, because their Groq call genuinely exists in `src/`. Presence in source
is not reachability at runtime, and the gap between those two is exactly where
this defect lives.

The check here is deliberately mechanical and CI-safe: it does not need
credentials or a network, so it cannot be quietly skipped on the one run that
mattered.
"""

import ast
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"

#: Constant names that express "how much work to do". A zero here means a
#: feature stopped running. Matched on the whole name, not a substring, so
#: MIN_COVERAGE_RATIO is not mistaken for a work quantity.
QUANTITY = re.compile(
    r"^(?:[A-Z0-9_]*_)?(?:COUNT|SIZE|LIMIT|RETRIES|BATCH|OVERLAP|IN_BRIEF|DIM|TOKENS)$"
    r"|^(?:CHUNK_SIZE|BATCH_SIZE|FINDINGS_IN_BRIEF|RATE_LIMIT_RETRIES|MAX_INPUT_TOKENS)$"
)

#: A module-level switch that turns behaviour off, or swaps real work for a
#: stand-in. None of these exist today and none should appear without a
#: deliberate conversation, so the test names them rather than guessing.
KILL_SWITCH = re.compile(r"^(?:ENABLE|DISABLE|SKIP|MOCK|FAKE|STUB|BYPASS)_[A-Z0-9_]+$")


def _module_constants() -> dict[str, tuple[str, object]]:
    """Module-level NAME = <literal> assignments across src/, by qualified name."""
    found: dict[str, tuple[str, object]] = {}
    for path in sorted(SRC.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text())
        for node in tree.body:  # module level only, not inside functions
            if not isinstance(node, ast.Assign):
                continue
            try:
                value = ast.literal_eval(node.value)
            except (ValueError, SyntaxError):
                continue
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.isupper():
                    rel = str(path.relative_to(REPO_ROOT))
                    found[f"{rel}:{target.id}"] = (target.id, value)
    return found


def test_the_constant_scan_is_not_vacuous():
    """
    Guard the guard.

    If the AST walk stopped finding constants, every assertion below would pass
    over an empty mapping and protect nothing while reporting green. A proof
    that cannot fail is worse than no proof, because it wears the credibility of
    one.
    """
    consts = _module_constants()
    assert len(consts) >= 12, f"expected many module constants, found {len(consts)}"
    names = {n for _, (n, _) in consts.items()}
    assert "FINDINGS_IN_BRIEF" in names, names
    assert any(QUANTITY.match(n) for n in names), (
        f"the QUANTITY pattern matched none of {sorted(names)}; it has drifted "
        "from how this codebase names things and is protecting nothing"
    )


def test_no_work_quantity_is_zero():
    """
    The rival's exact defect: a work quantity set to zero.

    `AI_PROCESS_COUNT = 0` disabled every advertised AI feature while the docs,
    the UI and the submission all still claimed them.
    """
    offenders = []
    for qualified, (name, value) in _module_constants().items():
        if not QUANTITY.match(name):
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        if value <= 0:
            offenders.append(f"{qualified} = {value!r}")
    assert offenders == [], (
        "a work quantity is zero or negative, which silently disables the "
        f"feature it governs: {offenders}. If a feature is genuinely being "
        "turned off, remove its claim from the judge-facing surfaces in the "
        "same commit."
    )


def test_no_kill_switch_constant_exists():
    """
    A named mock/disable switch is how a demo path becomes the only path.

    None exists today. If one is ever added, it must be a deliberate decision
    made with the claim surfaces in view, not something inherited from a
    debugging session, so this fails loudly rather than tolerating it.
    """
    offenders = [
        f"{qualified} = {value!r}"
        for qualified, (name, value) in _module_constants().items()
        if KILL_SWITCH.match(name)
    ]
    assert offenders == [], (
        f"a disable/mock switch was introduced at module scope: {offenders}. "
        "Gate behaviour on an explicit environment variable with a documented "
        "default instead, so /health can report it and a judge can see it."
    )


def test_the_generative_gate_still_requires_every_check():
    """
    The acceptance invariant, pinned as source text.

    A generated audio-description line is accepted only when the deterministic
    DCMP validation passes, Granite Guardian actually RAN and cleared it, the
    line fits the measured gap, and the draft was not the offline fallback.
    Dropping any conjunct would let a fix flip a row green on weaker evidence
    than the UI claims, which is the same class of defect as switching a feature
    off at a constant: the claim outlives the mechanism.
    """
    text = (SRC / "generative_fix.py").read_text()
    for conjunct in (
        "dcmp_valid",
        "guardian_cleared",
        "guardian_ran",
        "fits_gap",
        "not is_fallback",
    ):
        assert conjunct in text, (
            f"the acceptance gate no longer mentions {conjunct!r}. If the gate "
            "was deliberately weakened, the /judges copy and README must be "
            "corrected in the same commit."
        )
