"""
Which ruleset produced a report, recorded so it can be attributed.

Kept OUT of test_citations_are_never_fabricated.py deliberately. That file is
the one the README invites a judge to run with no setup, so it must import only
the standard library; these tests import from src/ and would have broken that
promise. Its own guard caught the violation when this was first written here,
which is the nicest possible demonstration that the guard works.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
from src.standards_registry import enrich_report_dict, ruleset_stamp


def test_the_ruleset_digest_is_real_and_derived_from_the_registry():
    import hashlib

    stamp = ruleset_stamp()
    assert stamp["digest"], "no ruleset digest produced"
    assert stamp["digest"].startswith("sha256:")

    registry = REPO_ROOT / "rules" / "rules_registry.yaml"
    expected = "sha256:" + hashlib.sha256(registry.read_bytes()).hexdigest()[:16]
    assert stamp["digest"] == expected, (
        "the stamp does not match a hash of the registry it names, so it is a "
        "declared version pretending to be a derived one"
    )


def test_editing_a_rule_changes_the_digest():
    """
    The property that makes this worth having.

    A stamp that survives a rule change is decoration. This proves the digest
    tracks the file rather than a constant someone must remember to bump.
    """
    import hashlib

    registry = REPO_ROOT / "rules" / "rules_registry.yaml"
    original = registry.read_bytes()
    before = ruleset_stamp()["digest"]
    try:
        registry.write_bytes(original + b"\n# a threshold changed\n")
        after = ruleset_stamp()["digest"]
    finally:
        registry.write_bytes(original)
    assert before != after, "editing the registry did not change the digest"
    assert ruleset_stamp()["digest"] == before, "registry not restored"


def test_every_served_report_carries_the_stamp():
    """All three served paths run through enrich_report_dict, so all three agree."""
    stamped = enrich_report_dict({"results": []})
    assert "ruleset" in stamped, (
        "enrich_report_dict no longer stamps the ruleset, so a served report "
        "cannot be attributed to the rules that produced it"
    )
    assert stamped["ruleset"]["digest"], stamped["ruleset"]


def test_the_stamp_does_not_overclaim_reproducibility():
    """
    Deliberate scope limit, pinned.

    We can prove which rules ran. We cannot prove the whole run reproduces
    bit-for-bit, because the generative layer is not deterministic. Claiming
    otherwise would be exactly the unverifiable assertion this suite exists to
    prevent, so the note must keep saying so.
    """
    note = ruleset_stamp()["note"].lower()
    assert "not a claim" in note and "bit-for-bit" in note, (
        "the ruleset stamp's note no longer limits its own claim; it must not "
        "be readable as a full-run reproducibility guarantee"
    )
