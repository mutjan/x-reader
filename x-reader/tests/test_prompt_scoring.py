"""Tests for prompts/scoring.md content validation.

Validates PROMPT-01 (negative categories with soft guidance, no numeric penalties)
and PROMPT-02 (calibration anchors for all 5 dimensions at 4 grade levels).
"""
import os
import re

import pytest


def _load_scoring_prompt():
    """Load the scoring prompt file from the project root."""
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    prompt_path = os.path.join(project_root, "prompts", "scoring.md")
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()


class TestNegativeCategories:
    """PROMPT-01: scoring.md contains all 9 negative categories with soft guidance."""

    NEGATIVE_CATEGORIES = [
        ("政治军事", ["政治", "军事"]),
        ("促销优惠", ["促销优惠"]),
        ("垂直行业商业活动", ["垂直行业商业活动"]),
        ("元宇宙/VR/AR", ["元宇宙"]),
        ("不知名公司融资", ["不知名公司融资"]),
        ("不知名人物创业", ["不知名人物创业"]),
        ("法律诉讼", ["法律诉讼"]),
        ("地质/环境/考古", ["地质"]),
        ("强化学习", ["强化学习"]),
    ]

    def test_negative_categories_present(self):
        """All 9 negative categories must appear in the prompt."""
        content = _load_scoring_prompt()
        missing = []
        for name, keywords in self.NEGATIVE_CATEGORIES:
            if not all(kw in content for kw in keywords):
                missing.append(name)
        assert not missing, (
            f"Missing negative categories in scoring.md: {missing}"
        )


class TestNoNumericPenalties:
    """PROMPT-01: scoring.md must NOT contain any numeric penalty rules."""

    def test_no_numeric_penalties_in_prompt(self):
        """No patterns like '-XX分' or '自动-XX' should appear."""
        content = _load_scoring_prompt()

        # Pattern 1: penalty "-数字分" but NOT score ranges like "90-100分"
        # Score ranges have format "数字-数字分" (e.g. "90-100分")
        # Penalties have format "-数字分" preceded by non-digit (e.g. "自动-20分")
        all_deduct = re.findall(r'-\d+\s*分', content)
        numeric_deduct = [
            m for m in all_deduct
            # Exclude score ranges: "数字-数字分" pattern
            if not re.search(r'\d' + re.escape(m), content)
        ]
        assert not numeric_deduct, (
            f"Found numeric penalty patterns in scoring.md: {numeric_deduct}"
        )

        # Pattern 2: "自动-数字" (e.g. "自动-20", "自动-15")
        auto_deduct = re.findall(r'自动-\d+', content)
        assert not auto_deduct, (
            f"Found auto-deduction patterns in scoring.md: {auto_deduct}"
        )

        # Pattern 3: "总分自动" pattern
        auto_total = re.findall(r'总分自动', content)
        assert not auto_total, (
            f"Found '总分自动' pattern in scoring.md: {auto_total}"
        )


class TestCalibrationAnchors:
    """PROMPT-02: scoring.md must contain calibration anchors for 5 dims x 4 levels."""

    DIMENSIONS = ["话题热度", "独特性", "读者价值", "可延伸深度", "扩展性"]
    LEVELS = ["S", "A+", "A", "C"]
    LEVEL_SCORES = {"S": "95", "A+": "85", "A": "75", "C": "60"}

    def test_calibration_anchors_present(self):
        """Each of 5 dimensions must have anchors at S/A+/A/C levels."""
        content = _load_scoring_prompt()

        # Check that calibration section exists
        assert "校准参考" in content, (
            "Missing '校准参考' section in scoring.md"
        )

        missing = []
        for dim in self.DIMENSIONS:
            # Find the dimension section
            if dim not in content:
                missing.append(f"{dim} (dimension not found)")
                continue

            for level in self.LEVELS:
                score = self.LEVEL_SCORES[level]
                # Look for score reference pattern like "95分参考" or "95分："
                score_pattern = f"{score}分"
                if score_pattern not in content:
                    missing.append(f"{dim} @ {level} ({score}分 reference)")

        assert not missing, (
            f"Missing calibration anchors in scoring.md: {missing}"
        )

    def test_anchors_are_abstract(self):
        """Calibration anchors should use abstract descriptions, not real headlines."""
        content = _load_scoring_prompt()

        # Check for quoted strings that look like real headlines (20+ chars in quotes)
        # This catches patterns like "DeepSeek聊天机器人国内遭遇超7小时大规模宕机"
        quoted_headlines = re.findall(r'"[^"]{20,}"', content)

        # Filter out JSON format examples and structural quotes
        structural_patterns = [
            "原始新闻URL", "S/A+/A/B/C", "index", "original_url",
            "grade", "score"
        ]
        real_headlines = [
            q for q in quoted_headlines
            if not any(p in q for p in structural_patterns)
        ]

        assert not real_headlines, (
            f"Found possible real headlines in calibration anchors "
            f"(should be abstract descriptions): {real_headlines}"
        )
