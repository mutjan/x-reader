"""Tests for prompts/scoring_config.json structure validation.

Validates PROMPT-03: penalty_rules field exists with proper structure
(7+ rules, each with name/keywords/penalty/max_grade).
"""
import json
import os

import pytest


CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "prompts", "scoring_config.json"
)


def test_penalty_rules_exist():
    """PROMPT-03: scoring_config.json must contain penalty_rules with proper structure"""
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        config = json.load(f)
    assert "penalty_rules" in config, "penalty_rules key missing from scoring_config.json"
    rules = config["penalty_rules"]
    assert isinstance(rules, list), "penalty_rules must be a list"
    assert len(rules) >= 7, f"Expected at least 7 penalty rules, found {len(rules)}"
    required_fields = {"name", "keywords", "penalty", "max_grade"}
    for i, rule in enumerate(rules):
        assert required_fields.issubset(rule.keys()), \
            f"Rule {i} missing fields: {required_fields - rule.keys()}"
        assert isinstance(rule["keywords"], list), f"Rule {i} keywords must be a list"
        assert isinstance(rule["penalty"], int), f"Rule {i} penalty must be an int"
        assert rule["penalty"] <= 0, f"Rule {i} penalty should be negative or 0, got {rule['penalty']}"
        assert rule["max_grade"] in ("S", "A+", "A", "B", "C"), \
            f"Rule {i} invalid max_grade: {rule['max_grade']}"
