#!/usr/bin/env python3
"""
相似度计算配置驱动阶梯方案测试
验证动态阈值、权重、地板阈值和向后兼容性
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
from unittest.mock import patch
from src.models.news import ProcessedNewsItem
from src.utils import similarity


def _make_news(id, title, summary, entities):
    """测试辅助函数：创建ProcessedNewsItem"""
    return ProcessedNewsItem(
        id=id,
        original_title=title,
        original_content=summary,
        source="test",
        url=f"http://test/{id}",
        published_at=datetime.now(),
        chinese_title=title,
        summary=summary,
        grade="A",
        score=85,
        entities=entities,
    )


class TestSimilarityConfig:
    """配置驱动阶梯方案测试"""

    def test_step_lookup_replaces_hardcoded_threshold(self):
        """Test 1: 阶梯查找替代硬编码阈值
        3个特定实体共享时，应使用min_entities=3的阶梯配置
        text_threshold=0.10, entity_weight=0.55, text_weight=0.45
        """
        config = {
            "entity_threshold_steps": [
                {"min_entities": 1, "text_threshold": 0.20, "entity_weight": 0.30, "text_weight": 0.70},
                {"min_entities": 3, "text_threshold": 0.10, "entity_weight": 0.55, "text_weight": 0.45},
            ],
            "threshold_floor": 0.01,
        }

        # 3个特定实体共享: OpenAI, GPT-5, Sam Altman (AI是通用实体，被过滤)
        news_a = _make_news(
            "a1",
            "OpenAI发布GPT-5大模型",
            "OpenAI今日发布最新大模型GPT-5",
            ["OpenAI", "GPT-5", "Sam Altman", "AI"],
        )
        news_b = _make_news(
            "b1",
            "OpenAI GPT-5模型发布",
            "OpenAI的GPT-5模型正式发布",
            ["OpenAI", "GPT-5", "Sam Altman", "AI"],
        )

        with patch.object(similarity, "_get_threshold_config", return_value=config):
            result = similarity.calculate_news_similarity(
                news_a, news_b, entity_threshold=3, similarity_threshold=0.85
            )

        # 两条新闻共享3个特定实体 (OpenAI, GPT-5, Sam Altman)
        # text_sim likely > 0.10 (titles are very similar with jieba)
        # Should match because text_sim >= 0.10
        assert result > 0, "3 shared entities + similar text should match"

        # Verify the combined score uses dynamic weights (0.55/0.45)
        # specific_count=3 -> entity_score = min(3/3, 1.0) = 1.0
        # combined = 1.0 * 0.55 + text_sim * 0.45
        text_sim = similarity._text_similarity(news_a, news_b)
        expected = 1.0 * 0.55 + text_sim * 0.45
        assert abs(result - expected) < 0.001, f"Expected {expected}, got {result}"

    def test_floor_enforcement(self):
        """Test 2: 地板阈值强制执行
        当阶梯配置的text_threshold低于threshold_floor时，使用threshold_floor
        """
        config = {
            "entity_threshold_steps": [
                {"min_entities": 1, "text_threshold": 0.20, "entity_weight": 0.30, "text_weight": 0.70},
                {"min_entities": 6, "text_threshold": 0.03, "entity_weight": 0.85, "text_weight": 0.15},
            ],
            "threshold_floor": 0.05,
        }

        # 6个特定实体共享（无通用实体）
        entities_shared = ["OpenAI", "GPT-5", "Sam Altman", "Dario Amodei", "DeepMind", "Claude"]
        news_a = _make_news(
            "a2", "AI公司集体发布新模型", "多家AI公司发布模型", entities_shared
        )
        news_b = _make_news(
            "b2", "科技公司AI新动态", "科技公司发布新AI模型", entities_shared
        )

        with patch.object(similarity, "_get_threshold_config", return_value=config):
            # Need to check: text_sim between these titles may or may not be >= 0.05
            # Let's compute first
            text_sim = similarity._text_similarity(news_a, news_b)

            result = similarity.calculate_news_similarity(
                news_a, news_b, entity_threshold=3, similarity_threshold=0.85
            )

        # If text_sim < 0.05 (floor), result should be 0.0
        if text_sim < 0.05:
            assert result == 0.0, f"text_sim={text_sim} < floor=0.05, should not match"
        else:
            # If text_sim >= 0.05, it should match with dynamic weights
            assert result > 0, "text_sim >= floor, should match"

    def test_dynamic_weights_replace_fixed(self):
        """Test 3: 动态权重替代固定50/50
        5个特定实体共享时，entity_weight=0.75, text_weight=0.25
        """
        config = {
            "entity_threshold_steps": [
                {"min_entities": 1, "text_threshold": 0.20, "entity_weight": 0.30, "text_weight": 0.70},
                {"min_entities": 5, "text_threshold": 0.03, "entity_weight": 0.75, "text_weight": 0.25},
            ],
            "threshold_floor": 0.01,
        }

        # 5个特定实体共享
        entities_shared = ["OpenAI", "GPT-5", "Sam Altman", "Dario Amodei", "DeepMind"]
        news_a = _make_news(
            "a3", "OpenAI发布GPT-5大模型", "OpenAI发布GPT-5", entities_shared
        )
        news_b = _make_news(
            "b3", "OpenAI GPT-5模型发布", "OpenAI发布GPT-5模型", entities_shared
        )

        with patch.object(similarity, "_get_threshold_config", return_value=config):
            result = similarity.calculate_news_similarity(
                news_a, news_b, entity_threshold=3, similarity_threshold=0.85
            )

        assert result > 0, "5 shared entities should match"

        # Verify weights: entity_score=5/3=1.0(capped), combined = 1.0*0.75 + text_sim*0.25
        text_sim = similarity._text_similarity(news_a, news_b)
        expected = 1.0 * 0.75 + text_sim * 0.25
        assert abs(result - expected) < 0.001, f"Expected {expected}, got {result}"

    def test_backward_compat_no_config(self):
        """Test 4: 向后兼容 - 无阶梯配置时回退到旧行为
        specific_count>=2 -> threshold=0.15, weights=0.5/0.5
        Returns combined score (no floor applied)
        """
        config = {}  # No entity_threshold_steps

        # 2个特定实体共享 (OpenAI, GPT-5; "AI" is generic)
        news_a = _make_news(
            "a4",
            "OpenAI发布GPT-5大模型",
            "OpenAI发布GPT-5",
            ["OpenAI", "GPT-5", "AI"],
        )
        news_b = _make_news(
            "b4",
            "OpenAI GPT-5模型发布",
            "OpenAI的GPT-5模型",
            ["OpenAI", "GPT-5", "AI"],
        )

        with patch.object(similarity, "_get_threshold_config", return_value=config):
            result = similarity.calculate_news_similarity(
                news_a, news_b, entity_threshold=3, similarity_threshold=0.85
            )

        # specific_count=2 -> old behavior: threshold=0.15, weights=0.5/0.5
        text_sim = similarity._text_similarity(news_a, news_b)
        if text_sim >= 0.15:
            assert result > 0, "text_sim >= 0.15, should match"
            # Returns combined = entity_score * 0.5 + text_sim * 0.5
            entity_score = min(2 / 3.0, 1.0)
            expected = entity_score * 0.5 + text_sim * 0.5
            assert abs(result - expected) < 0.001, f"Expected {expected}, got {result}"
        else:
            assert result == 0.0

    def test_specific_count_1_no_floor_to_prevent_overaggregation(self):
        """FIX-01: specific_count=1 does NOT apply floor to prevent transitive over-aggregation.
        Only returns combined score (may be below similarity_threshold).
        Floor is reserved for specific_count>=2 where entity signal is stronger."""
        config = {
            "entity_threshold_steps": [
                {"min_entities": 1, "text_threshold": 0.20, "entity_weight": 0.30, "text_weight": 0.70},
            ],
            "threshold_floor": 0.01,
        }

        # Two news sharing 1 specific entity "Claude" (exclude "AI" which is generic)
        news_a = _make_news(
            "a_fix1", "Claude新功能发布", "Claude发布了新功能", ["Claude", "AI"]
        )
        news_b = _make_news(
            "b_fix1", "Claude功能更新", "Claude推出了功能更新", ["Claude", "AI"]
        )

        with patch.object(similarity, "_get_threshold_config", return_value=config):
            result = similarity.calculate_news_similarity(
                news_a, news_b, entity_threshold=3, similarity_threshold=0.5
            )

        # specific_count=1: returns combined (NOT floored)
        # combined = entity_score * 0.30 + text_sim * 0.70
        text_sim = similarity._text_similarity(news_a, news_b)
        entity_score = min(1 / 3.0, 1.0)
        expected = entity_score * 0.30 + text_sim * 0.70
        assert result > 0, "specific_count=1 should still match (returns combined)"
        assert abs(result - expected) < 0.001, f"Expected combined {expected}, got {result}"

    def test_specific_count_2_passes_caller_threshold(self):
        """FIX-02: specific_count=2, text_sim >= text_threshold(0.15), similarity_threshold=0.5 -> result >= 0.5"""
        config = {
            "entity_threshold_steps": [
                {"min_entities": 1, "text_threshold": 0.20, "entity_weight": 0.30, "text_weight": 0.70},
                {"min_entities": 2, "text_threshold": 0.15, "entity_weight": 0.45, "text_weight": 0.55},
            ],
            "threshold_floor": 0.01,
        }

        # Two news sharing 2 specific entities "Claude", "Anthropic" (exclude "AI")
        news_a = _make_news(
            "a_fix2", "Claude模型Anthropic发布", "Anthropic发布Claude模型", ["Claude", "Anthropic", "AI"]
        )
        news_b = _make_news(
            "b_fix2", "Anthropic推出Claude", "Anthropic推出新Claude", ["Claude", "Anthropic", "AI"]
        )

        with patch.object(similarity, "_get_threshold_config", return_value=config):
            result = similarity.calculate_news_similarity(
                news_a, news_b, entity_threshold=3, similarity_threshold=0.5
            )

        assert result >= 0.5, f"specific_count=2 with similarity_threshold=0.5: result {result} should >= 0.5"

    def test_high_entity_count_not_floored(self):
        """FIX-04 regression: specific_count=3, combined naturally >= 0.5 -> result == combined (no flooring)"""
        config = {
            "entity_threshold_steps": [
                {"min_entities": 1, "text_threshold": 0.20, "entity_weight": 0.30, "text_weight": 0.70},
                {"min_entities": 3, "text_threshold": 0.10, "entity_weight": 0.55, "text_weight": 0.45},
            ],
            "threshold_floor": 0.01,
        }

        # 3 specific entities: OpenAI, GPT-5, Sam Altman (AI is generic)
        news_a = _make_news(
            "a_fix4", "OpenAI发布GPT-5大模型", "OpenAI今日发布最新大模型GPT-5", ["OpenAI", "GPT-5", "Sam Altman", "AI"]
        )
        news_b = _make_news(
            "b_fix4", "OpenAI GPT-5模型发布", "OpenAI的GPT-5模型正式发布", ["OpenAI", "GPT-5", "Sam Altman", "AI"]
        )

        with patch.object(similarity, "_get_threshold_config", return_value=config):
            result = similarity.calculate_news_similarity(
                news_a, news_b, entity_threshold=3, similarity_threshold=0.5
            )

        # specific_count=3 -> entity_score = min(3/3, 1.0) = 1.0
        # combined = 1.0 * 0.55 + text_sim * 0.45 >= 0.55
        # max(combined, 0.5) == combined (no flooring applied)
        text_sim = similarity._text_similarity(news_a, news_b)
        entity_score = min(3 / 3.0, 1.0)
        expected_combined = entity_score * 0.55 + text_sim * 0.45
        assert abs(result - expected_combined) < 0.001, f"Expected {expected_combined}, got {result} -- should NOT be floored"

    def test_different_caller_thresholds_count_2(self):
        """FIX-06: different caller thresholds with specific_count=2 -- floor uses actual similarity_threshold"""
        config = {
            "entity_threshold_steps": [
                {"min_entities": 1, "text_threshold": 0.20, "entity_weight": 0.30, "text_weight": 0.70},
                {"min_entities": 2, "text_threshold": 0.15, "entity_weight": 0.45, "text_weight": 0.55},
            ],
            "threshold_floor": 0.01,
        }

        # specific_count=2, similarity_threshold=0.55 (reviewer's threshold)
        news_a = _make_news(
            "a_fix6", "Claude模型Anthropic发布", "Anthropic发布Claude模型", ["Claude", "Anthropic", "AI"]
        )
        news_b = _make_news(
            "b_fix6", "Anthropic推出Claude", "Anthropic推出新Claude", ["Claude", "Anthropic", "AI"]
        )

        with patch.object(similarity, "_get_threshold_config", return_value=config):
            result = similarity.calculate_news_similarity(
                news_a, news_b, entity_threshold=3, similarity_threshold=0.55
            )

        # specific_count=2: floor applies, result >= similarity_threshold
        assert result >= 0.55, f"specific_count=2 with similarity_threshold=0.55: result {result} should >= 0.55"

    def test_ranking_preservation(self):
        """Ranking: specific_count=3 vs specific_count=1, both pass threshold -> higher count has higher score"""
        config = {
            "entity_threshold_steps": [
                {"min_entities": 1, "text_threshold": 0.20, "entity_weight": 0.30, "text_weight": 0.70},
                {"min_entities": 3, "text_threshold": 0.10, "entity_weight": 0.55, "text_weight": 0.45},
            ],
            "threshold_floor": 0.01,
        }

        # news_a and news_b share 3 entities
        news_a = _make_news(
            "a_rank", "OpenAI发布GPT-5大模型", "OpenAI发布GPT-5模型", ["OpenAI", "GPT-5", "Sam Altman", "AI"]
        )
        news_b = _make_news(
            "b_rank", "OpenAI GPT-5模型发布", "OpenAI发布GPT-5", ["OpenAI", "GPT-5", "Sam Altman", "AI"]
        )

        # news_c and news_d share 1 entity
        news_c = _make_news(
            "c_rank", "Claude新功能发布", "Claude发布了新功能", ["Claude", "AI"]
        )
        news_d = _make_news(
            "d_rank", "Claude功能更新", "Claude推出了功能更新", ["Claude", "AI"]
        )

        with patch.object(similarity, "_get_threshold_config", return_value=config):
            result_high = similarity.calculate_news_similarity(
                news_a, news_b, entity_threshold=3, similarity_threshold=0.5
            )
            result_low = similarity.calculate_news_similarity(
                news_c, news_d, entity_threshold=3, similarity_threshold=0.5
            )

        assert result_high > result_low, f"3 entities ({result_high}) should rank higher than 1 entity ({result_low})"

    def test_zero_entities_unchanged(self):
        """Test 5: 零特定实体共享时行为不变
        返回text_sim如果 >= similarity_threshold，否则0.0
        """
        news_a = _make_news(
            "a5", "OpenAI发布新模型", "OpenAI发布新模型", ["OpenAI"]
        )
        news_b = _make_news(
            "b5", "谷歌发布新芯片", "谷歌发布新芯片", ["Google"]
        )

        # 无特定实体共享 -> should use similarity_threshold as cutoff
        config = {
            "entity_threshold_steps": [
                {"min_entities": 1, "text_threshold": 0.20, "entity_weight": 0.30, "text_weight": 0.70},
            ],
            "threshold_floor": 0.01,
        }

        with patch.object(similarity, "_get_threshold_config", return_value=config):
            result = similarity.calculate_news_similarity(
                news_a, news_b, entity_threshold=3, similarity_threshold=0.85
            )

        text_sim = similarity._text_similarity(news_a, news_b)

        if text_sim >= 0.85:
            assert result == text_sim, "text_sim >= threshold, should return text_sim"
        else:
            assert result == 0.0, f"text_sim={text_sim} < threshold=0.85, should return 0.0"


if __name__ == "__main__":
    test = TestSimilarityConfig()
    test.test_step_lookup_replaces_hardcoded_threshold()
    print("PASS: test_step_lookup_replaces_hardcoded_threshold")
    test.test_floor_enforcement()
    print("PASS: test_floor_enforcement")
    test.test_dynamic_weights_replace_fixed()
    print("PASS: test_dynamic_weights_replace_fixed")
    test.test_backward_compat_no_config()
    print("PASS: test_backward_compat_no_config")
    test.test_zero_entities_unchanged()
    print("PASS: test_zero_entities_unchanged")
    print("\nAll similarity config tests passed!")
