"""
Pytest configuration and shared fixtures for AccessGate tests.
"""
import pytest
from pathlib import Path

REPO_ROOT = Path(__file__).parent
DATA_DIR = REPO_ROOT / "data"
DEMO_DIR = DATA_DIR / "demo"
RULES_PATH = REPO_ROOT / "rules" / "rules_registry.yaml"
