"""
Rule registry loader for AccessGate.
Loads rules/rules_registry.yaml and provides access by rule ID.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional
import yaml

RULES_PATH = Path(__file__).parent.parent / "rules" / "rules_registry.yaml"


@dataclass
class Rule:
    id: str
    source: str
    check_type: Literal["automated", "automated_with_band", "human_judgment_flag"]
    inputs: list[str]
    logic: str
    sarif_level: Literal["error", "warning", "note"]


_registry: Optional[dict[str, Rule]] = None


def load_registry(path: Path = RULES_PATH) -> dict[str, Rule]:
    """Load all rules from the YAML registry. Cached after first call."""
    global _registry
    if _registry is not None:
        return _registry

    with open(path) as f:
        data = yaml.safe_load(f)

    _registry = {}
    for entry in data["rules"]:
        rule = Rule(
            id=entry["id"],
            source=entry["source"],
            check_type=entry["check_type"],
            inputs=entry["inputs"],
            logic=entry["logic"],
            sarif_level=entry["sarif_level"],
        )
        _registry[rule.id] = rule

    return _registry


def get_rule(rule_id: str) -> Rule:
    """Get a single rule by ID. Raises KeyError if not found."""
    registry = load_registry()
    if rule_id not in registry:
        raise KeyError(f"Rule '{rule_id}' not found in registry")
    return registry[rule_id]


def all_rules() -> list[Rule]:
    """Return all rules in registry order."""
    return list(load_registry().values())


def reset_registry() -> None:
    """Reset cached registry (for testing)."""
    global _registry
    _registry = None
