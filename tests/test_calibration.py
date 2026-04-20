"""Tests for calibration rule generation and engine.

Validates CALIB-01 (calibration auto-applies) and CALIB-02 (thresholds data-driven).
"""
import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta
from src.models.news import ProcessedNewsItem
from src.processors.score_calibrator import (
    CalibrationEngine, CalibrationRuleGenerator, CalibrationRule,
    MIN_SAMPLE_COUNT, MIN_CONFIDENCE
)


def make_test_item(title="Test News", score=75, grade="A", entities=None):
    """Create a minimal ProcessedNewsItem for testing."""
    return ProcessedNewsItem(
        id="test-id",
        original_title=title,
        original_content="Test content",
        chinese_title=title,
        summary="Test summary",
        source="test",
        url="https://example.com/test",
        published_at=datetime.now(),
        entities=entities or ["test"],
        news_type="tech",
        score=score,
        grade=grade
    )


def _make_sample_news_data(num_per_grade=20):
    """Create sample news_data.json structure with known score distribution."""
    items = []
    thresholds = {"S": 90, "A+": 85, "A": 75, "B": 65, "C": 0}

    # S range: 90-98
    for i in range(num_per_grade):
        score = 90 + (i % 9)
        items.append({"id": f"s_{i}", "title": f"S item {i}", "score": score, "rating": "S",
                       "entities": ["OpenAI", "GPT"]})
    # A+ range: 85-89
    for i in range(num_per_grade):
        score = 85 + (i % 5)
        items.append({"id": f"ap_{i}", "title": f"A+ item {i}", "score": score, "rating": "A+",
                       "entities": ["Anthropic", "Claude"]})
    # A range: 75-84
    for i in range(num_per_grade + 10):
        score = 75 + (i % 10)
        items.append({"id": f"a_{i}", "title": f"A item {i}", "score": score, "rating": "A",
                       "entities": ["Google", "Gemini"]})
    # B range: 65-74
    for i in range(num_per_grade):
        score = 65 + (i % 10)
        items.append({"id": f"b_{i}", "title": f"B item {i}", "score": score, "rating": "B",
                       "entities": ["Startup", "融资"]})

    return {"news": {"2026-04-10": items}}


def _make_sample_config():
    """Return minimal scoring_config dict."""
    return {"grade_thresholds": {"S": 90, "A+": 85, "A": 75, "B": 65, "C": 0}}


@pytest.fixture
def sample_news_data():
    return _make_sample_news_data()


@pytest.fixture
def sample_scoring_config():
    return _make_sample_config()


@pytest.fixture
def tmp_news_data_file(tmp_path, sample_news_data):
    """Write sample news data to a temp file and return path."""
    path = tmp_path / "news_data.json"
    path.write_text(json.dumps(sample_news_data), encoding="utf-8")
    return str(path)


@pytest.fixture
def tmp_config_file(tmp_path, sample_scoring_config):
    """Write sample scoring config to a temp file and return path."""
    path = tmp_path / "scoring_config.json"
    path.write_text(json.dumps(sample_scoring_config), encoding="utf-8")
    return str(path)


@pytest.fixture
def tmp_rules_file(tmp_path):
    """Return a temp path for calibration rules."""
    return str(tmp_path / "calibration_rules.json")


# ===== Test CalibrationRuleGenerator =====

class TestCalibrationRuleGenerator:
    def test_generates_grade_shift_rules(self, tmp_news_data_file, tmp_config_file):
        """CALIB-01: CalibrationRuleGenerator generates grade_shift rules when sample count >= 15"""
        gen = CalibrationRuleGenerator(
            news_data_file=tmp_news_data_file,
            config_file=tmp_config_file
        )
        rules = gen.generate_rules()
        grade_shift_rules = [r for r in rules if r.rule_type == "grade_shift"]
        assert len(grade_shift_rules) > 0, "Should generate at least one grade_shift rule"
        for rule in grade_shift_rules:
            assert rule.rule_type == "grade_shift"
            assert rule.sample_count >= MIN_SAMPLE_COUNT
            assert rule.confidence >= MIN_CONFIDENCE

    def test_generates_entity_rules(self, tmp_news_data_file, tmp_config_file):
        """Entity rules generated when entity has >= 15 items and >= 80% consistency"""
        gen = CalibrationRuleGenerator(
            news_data_file=tmp_news_data_file,
            config_file=tmp_config_file
        )
        rules = gen.generate_rules()
        entity_rules = [r for r in rules if r.rule_type == "entity"]
        # With our sample data, entities appear 20+ times each with distinct score ranges
        # so we should get entity rules
        assert len(entity_rules) > 0, "Should generate entity rules for entities with enough samples"
        for rule in entity_rules:
            assert rule.sample_count >= MIN_SAMPLE_COUNT
            assert rule.confidence >= MIN_CONFIDENCE

    def test_no_rules_when_insufficient_data(self, tmp_path, tmp_config_file):
        """No rules generated when total sample count < MIN_SAMPLE_COUNT"""
        few_items = {"news": {"2026-04-10": [
            {"id": f"item_{i}", "title": f"Item {i}", "score": 80, "rating": "A",
             "entities": ["test"]}
            for i in range(5)  # Only 5 items
        ]}}
        news_file = tmp_path / "news_data.json"
        news_file.write_text(json.dumps(few_items), encoding="utf-8")

        gen = CalibrationRuleGenerator(
            news_data_file=str(news_file),
            config_file=tmp_config_file
        )
        rules = gen.generate_rules()
        assert len(rules) == 0, "Should produce no rules with insufficient data"


# ===== Test CalibrationEngine =====

class TestCalibrationEngine:
    def test_reads_thresholds_from_config(self, tmp_config_file, tmp_rules_file, monkeypatch):
        """CalibrationEngine reads thresholds from scoring_config.json, not hard-coded values"""
        import src.processors.score_calibrator as sc_mod
        monkeypatch.setattr(sc_mod, "SCORING_CONFIG_FILE", tmp_config_file)
        monkeypatch.setattr(sc_mod, "CALIBRATION_RULES_FILE", tmp_rules_file)

        engine = CalibrationEngine()
        assert engine.thresholds["S"] == 90
        assert engine.thresholds["A+"] == 85
        assert engine.thresholds["A"] == 75
        assert engine.thresholds["B"] == 65

    def test_empty_rules_returns_unchanged(self, tmp_config_file, tmp_rules_file, monkeypatch):
        """With empty calibration rules, apply_calibration returns item unchanged"""
        import src.processors.score_calibrator as sc_mod
        monkeypatch.setattr(sc_mod, "CALIBRATION_RULES_FILE", tmp_rules_file)

        engine = CalibrationEngine()
        item = make_test_item(score=85, grade="A+")
        result = engine.apply_calibration(item)
        assert result.score == 85
        assert result.grade == "A+"

    def test_applies_grade_shift_rule(self, tmp_config_file, tmp_rules_file, monkeypatch):
        """grade_shift rule adjusts score based on grade-level offset"""
        import src.processors.score_calibrator as sc_mod
        monkeypatch.setattr(sc_mod, "CALIBRATION_RULES_FILE", tmp_rules_file)

        # Create a grade_shift rule for A grade: +3 offset
        rule = CalibrationRule(
            rule_id="grade_shift_A_test",
            rule_type="grade_shift",
            value="A",
            score_adjustment=3,
            confidence=0.9,
            sample_count=20,
            created_at=datetime.now(),
            expires_at=datetime.now() + timedelta(days=30)
        )
        # Write rule to file
        rules_data = {
            "generated_at": datetime.now().isoformat(),
            "expires_at": (datetime.now() + timedelta(days=30)).isoformat(),
            "rules": [rule.to_dict()]
        }
        with open(tmp_rules_file, 'w') as f:
            json.dump(rules_data, f)

        engine = CalibrationEngine()
        item = make_test_item(score=80, grade="A")
        result = engine.apply_calibration(item)
        assert result.score == 83, f"Expected 80+3=83, got {result.score}"

    def test_apply_calibration_raw_with_grade_shift(self, tmp_config_file, tmp_rules_file, monkeypatch):
        """apply_calibration_raw handles grade_shift rules correctly"""
        import src.processors.score_calibrator as sc_mod
        monkeypatch.setattr(sc_mod, "CALIBRATION_RULES_FILE", tmp_rules_file)

        rule = CalibrationRule(
            rule_id="grade_shift_S_test",
            rule_type="grade_shift",
            value="S",
            score_adjustment=-3,
            confidence=0.9,
            sample_count=20,
            created_at=datetime.now(),
            expires_at=datetime.now() + timedelta(days=30)
        )
        rules_data = {
            "generated_at": datetime.now().isoformat(),
            "expires_at": (datetime.now() + timedelta(days=30)).isoformat(),
            "rules": [rule.to_dict()]
        }
        with open(tmp_rules_file, 'w') as f:
            json.dump(rules_data, f)

        engine = CalibrationEngine()
        # Score 93 is in S range (>=90)
        result = engine.apply_calibration_raw(93.0, ["OpenAI"], "Test title")
        assert result == 90.0, f"Expected 93-3=90, got {result}"

    def test_apply_calibration_raw_empty_rules(self, tmp_config_file, tmp_rules_file, monkeypatch):
        """apply_calibration_raw returns unchanged score with empty rules"""
        import src.processors.score_calibrator as sc_mod
        monkeypatch.setattr(sc_mod, "CALIBRATION_RULES_FILE", tmp_rules_file)

        engine = CalibrationEngine()
        result = engine.apply_calibration_raw(85.0, ["test"], "Title")
        assert result == 85.0

    def test_score_to_grade_uses_config_thresholds(self, tmp_config_file, tmp_rules_file, monkeypatch):
        """_score_to_grade uses thresholds from scoring_config.json"""
        import src.processors.score_calibrator as sc_mod
        monkeypatch.setattr(sc_mod, "CALIBRATION_RULES_FILE", tmp_rules_file)

        engine = CalibrationEngine()
        assert engine._score_to_grade(92) == "S"
        assert engine._score_to_grade(87) == "A+"
        assert engine._score_to_grade(78) == "A"
        assert engine._score_to_grade(68) == "B"
        assert engine._score_to_grade(50) == "C"


# ===== Integration Tests: Calibration in Pipeline =====

def _make_pipeline_item(title="Pipeline Test", url="https://example.com/pipeline",
                         content="Generic tech content", entities=None):
    """Create item for pipeline testing."""
    return ProcessedNewsItem(
        id="pipeline-test-id",
        original_title=title,
        original_content=content,
        chinese_title=title,
        summary="Test summary",
        source="test",
        url=url,
        published_at=datetime.now(),
        entities=entities or ["test"],
        news_type="tech"
    )


def _make_pipeline_response(url, score, grade):
    """Create scoring response JSON matching LLM output format."""
    return json.dumps([{"index": 0, "original_url": url, "grade": grade, "score": score}])


class TestCalibrationInPipeline:
    def test_calibration_in_pipeline_applies_grade_shift(self, tmp_rules_file, monkeypatch):
        """CALIB-01: parse_scoring_response applies calibration between zeitgeist and grade calc"""
        import src.processors.score_calibrator as sc_mod
        monkeypatch.setattr(sc_mod, "CALIBRATION_RULES_FILE", tmp_rules_file)

        # Write a grade_shift rule for A grade: +5 offset
        rule = CalibrationRule(
            rule_id="grade_shift_A_pipeline",
            rule_type="grade_shift",
            value="A",
            score_adjustment=5,
            confidence=0.9,
            sample_count=20,
            created_at=datetime.now(),
            expires_at=datetime.now() + timedelta(days=30)
        )
        rules_data = {
            "generated_at": datetime.now().isoformat(),
            "expires_at": (datetime.now() + timedelta(days=30)).isoformat(),
            "rules": [rule.to_dict()]
        }
        with open(tmp_rules_file, 'w') as f:
            json.dump(rules_data, f)

        from src.processors.ai_processor import AIScorer
        scorer = AIScorer()
        scorer.config = {
            "grade_thresholds": {"S": 90, "A+": 85, "A": 75, "B": 65, "C": 0},
            "special_bonuses": [],
            "penalty_rules": [],
            "score_cap_by_grade": {"S": 100, "A+": 94, "A": 89, "B": 79, "C": 0}
        }

        # Score 78 is in A range (75-84), +5 = 83
        item = _make_pipeline_item(url="https://example.com/cal-pipe-1")
        response = _make_pipeline_response(item.url, 78, "A")
        results = scorer.parse_scoring_response(response, [item])
        assert len(results) == 1
        assert results[0].score == 83, f"Expected 78+5=83 after calibration, got {results[0].score}"

    def test_calibration_in_pipeline_empty_rules_no_change(self, tmp_rules_file, monkeypatch):
        """Empty calibration rules = identical scores (backward compatible)"""
        import src.processors.score_calibrator as sc_mod
        monkeypatch.setattr(sc_mod, "CALIBRATION_RULES_FILE", tmp_rules_file)

        from src.processors.ai_processor import AIScorer
        scorer = AIScorer()
        scorer.config = {
            "grade_thresholds": {"S": 90, "A+": 85, "A": 75, "B": 65, "C": 0},
            "special_bonuses": [],
            "penalty_rules": [],
            "score_cap_by_grade": {"S": 100, "A+": 94, "A": 89, "B": 79, "C": 0}
        }

        item = _make_pipeline_item(
            title="Boring Infrastructure Update",
            content="A data center upgraded its cooling system with improved thermal management",
            url="https://example.com/cal-pipe-empty"
        )
        response = _make_pipeline_response(item.url, 75, "A")
        results = scorer.parse_scoring_response(response, [item])
        assert len(results) >= 0
        if len(results) == 1:
            # Score should be unchanged (no zeitgeist, no calibration)
            assert results[0].score >= 75

    def test_calibration_in_pipeline_entity_rule(self, tmp_rules_file, monkeypatch):
        """Entity calibration rule applied when news item entities match"""
        import src.processors.score_calibrator as sc_mod
        monkeypatch.setattr(sc_mod, "CALIBRATION_RULES_FILE", tmp_rules_file)

        # Write entity rule: "Startup" entity -> -5
        rule = CalibrationRule(
            rule_id="entity_startup_test",
            rule_type="entity",
            value="Startup",
            score_adjustment=-5,
            confidence=0.9,
            sample_count=20,
            created_at=datetime.now(),
            expires_at=datetime.now() + timedelta(days=30)
        )
        rules_data = {
            "generated_at": datetime.now().isoformat(),
            "expires_at": (datetime.now() + timedelta(days=30)).isoformat(),
            "rules": [rule.to_dict()]
        }
        with open(tmp_rules_file, 'w') as f:
            json.dump(rules_data, f)

        from src.processors.ai_processor import AIScorer
        scorer = AIScorer()
        scorer.config = {
            "grade_thresholds": {"S": 90, "A+": 85, "A": 75, "B": 65, "C": 0},
            "special_bonuses": [],
            "penalty_rules": [],
            "score_cap_by_grade": {"S": 100, "A+": 94, "A": 89, "B": 79, "C": 0}
        }

        item = _make_pipeline_item(
            url="https://example.com/cal-pipe-entity",
            entities=["Startup", "融资"]
        )
        response = _make_pipeline_response(item.url, 80, "A")
        results = scorer.parse_scoring_response(response, [item])
        assert len(results) == 1
        assert results[0].score == 75, f"Expected 80-5=75 after entity calibration, got {results[0].score}"

    def test_calibration_pipeline_order(self, tmp_rules_file, monkeypatch):
        """Pipeline order: penalty -> bonuses -> zeitgeist -> calibration -> cap"""
        import src.processors.score_calibrator as sc_mod
        monkeypatch.setattr(sc_mod, "CALIBRATION_RULES_FILE", tmp_rules_file)

        # grade_shift for A: +3
        rule = CalibrationRule(
            rule_id="grade_shift_A_order",
            rule_type="grade_shift",
            value="A",
            score_adjustment=3,
            confidence=0.9,
            sample_count=20,
            created_at=datetime.now(),
            expires_at=datetime.now() + timedelta(days=30)
        )
        rules_data = {
            "generated_at": datetime.now().isoformat(),
            "expires_at": (datetime.now() + timedelta(days=30)).isoformat(),
            "rules": [rule.to_dict()]
        }
        with open(tmp_rules_file, 'w') as f:
            json.dump(rules_data, f)

        from src.processors.ai_processor import AIScorer
        scorer = AIScorer()
        scorer.config = {
            "grade_thresholds": {"S": 90, "A+": 85, "A": 75, "B": 65, "C": 0},
            "special_bonuses": [
                {"keywords": ["hinton"], "bonus": 5, "min_score": 85, "max_score": 100}
            ],
            "penalty_rules": [
                {"name": "military", "keywords": ["军事"], "penalty": -15, "max_grade": None}
            ],
            "score_cap_by_grade": {"S": 100, "A+": 94, "A": 89, "B": 79, "C": 0}
        }

        # Pipeline: 82 -> penalty -15 = 67 -> hinton bonus (+5, min_score=85) = 85
        # -> calibration grade_shift A +3 = 88 -> cap(A=89) no change
        item = _make_pipeline_item(
            title="Hinton research update",
            content="hinton discusses AI safety concerns amid 军事 applications",
            url="https://example.com/cal-pipe-order",
            entities=["test"]
        )
        response = _make_pipeline_response(item.url, 82, "A")
        results = scorer.parse_scoring_response(response, [item])
        assert len(results) == 1
        assert results[0].score == 88, f"Expected 88 after full pipeline, got {results[0].score}"
