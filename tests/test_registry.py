"""
Tests for the rule registry loader.
"""
import pytest
from src.registry import load_registry, get_rule, all_rules, reset_registry

EXPECTED_RULE_COUNT = 23

EXPECTED_IDS = {
    "FCC-ACC-01", "FCC-SYN-01", "FCC-CMP-01", "FCC-PLC-01",
    "WCAG-122-01", "WCAG-125-01", "WCAG-125-02",
    "DCMP-CAP-01", "DCMP-CAP-02", "DCMP-CAP-03", "DCMP-CAP-04",
    "DCMP-CAP-05", "DCMP-CAP-06",
    "DCMP-DESC-01", "DCMP-DESC-02", "DCMP-DESC-03", "DCMP-DESC-04",
    "DCMP-DESC-05", "DCMP-DESC-06", "DCMP-DESC-07",
    "NFLX-CPS-01", "NFLX-LEN-01", "NFLX-DUR-01",
}


def setup_function():
    reset_registry()


def test_registry_loads():
    registry = load_registry()
    assert isinstance(registry, dict)
    assert len(registry) == EXPECTED_RULE_COUNT


def test_all_rule_ids_present():
    registry = load_registry()
    assert set(registry.keys()) == EXPECTED_IDS


def test_each_rule_has_required_fields():
    for rule in all_rules():
        assert rule.id, f"Rule missing id"
        assert rule.source, f"Rule {rule.id} missing source"
        assert rule.check_type in ("automated", "automated_with_band", "human_judgment_flag"), \
            f"Rule {rule.id} has invalid check_type: {rule.check_type}"
        assert isinstance(rule.inputs, list) and len(rule.inputs) > 0, \
            f"Rule {rule.id} missing inputs"
        assert rule.logic, f"Rule {rule.id} missing logic"
        assert rule.sarif_level in ("error", "warning", "note"), \
            f"Rule {rule.id} has invalid sarif_level: {rule.sarif_level}"


def test_get_rule_known():
    rule = get_rule("FCC-ACC-01")
    assert rule.id == "FCC-ACC-01"
    assert rule.sarif_level == "warning"
    assert rule.check_type == "automated_with_band"


def test_get_rule_unknown_raises():
    with pytest.raises(KeyError):
        get_rule("NONEXISTENT-01")


def test_sarif_levels_valid():
    errors = [r for r in all_rules() if r.sarif_level == "error"]
    warnings = [r for r in all_rules() if r.sarif_level == "warning"]
    notes = [r for r in all_rules() if r.sarif_level == "note"]
    assert len(errors) > 0
    assert len(warnings) > 0
    assert len(notes) > 0
