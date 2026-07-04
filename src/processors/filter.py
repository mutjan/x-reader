#!/usr/bin/env python3
"""
新闻预筛选模块
基于关键词和规则对原始新闻进行初步筛选
"""
from typing import List, Tuple, Set
import re

from src.models.news import RawNewsItem
from src.config.settings import PRIORITY_KEYWORDS, BLACKLIST_KEYWORDS
from src.utils.common import setup_logger

logger = setup_logger("filter")

class NewsFilter:
    """新闻筛选器"""

    def __init__(self):
        # 编译正则表达式，提高匹配效率
        self.priority_patterns = self._compile_patterns(PRIORITY_KEYWORDS)
        self.blacklist_pattern = self._compile_blacklist_pattern(BLACKLIST_KEYWORDS)

    def _compile_patterns(self, keyword_groups: dict) -> dict:
        """编译关键词组为正则表达式模式"""
        patterns = {}
        for group, keywords in keyword_groups.items():
            # 构建正则表达式，匹配整个单词（支持中英文）
            pattern = re.compile(
                r'\b(' + '|'.join(re.escape(k) for k in keywords) + r')\b',
                re.IGNORECASE | re.UNICODE
            )
            patterns[group] = pattern
        return patterns

    def _compile_blacklist_pattern(self, blacklist_keywords: List[str]) -> re.Pattern:
        """编译黑名单关键词正则表达式"""
        if not blacklist_keywords:
            # 返回一个永远不会匹配的模式
            return re.compile(r'^$')

        return re.compile(
            r'\b(' + '|'.join(re.escape(k) for k in blacklist_keywords) + r')\b',
            re.IGNORECASE | re.UNICODE
        )

    def calculate_priority_score(self, item: RawNewsItem) -> Tuple[int, Set[str]]:
        """
        计算新闻的优先级得分
        :param item: 原始新闻项
        :return: (得分, 匹配到的关键词集合)
        """
        score = 0
        matched_keywords = set()
        text = f"{item.title} {item.content}".lower()

        # 检查各优先级关键词组
        for group, pattern in self.priority_patterns.items():
            matches = pattern.findall(text)
            if matches:
                # 每个匹配到的关键词加10分
                unique_matches = set(match.lower() for match in matches)
                score += len(unique_matches) * 10
                matched_keywords.update(unique_matches)

                # 不同组额外加分
                if group == "ai":
                    score += 5  # AI相关额外加5分
                elif group == "bigtech":
                    score += 3  # 科技巨头相关加3分

        return score, matched_keywords

    def is_blacklisted(self, item: RawNewsItem) -> Tuple[bool, Set[str]]:
        """
        检查新闻是否包含黑名单关键词
        :param item: 原始新闻项
        :return: (是否在黑名单, 匹配到的黑名单关键词集合)
        """
        text = f"{item.title} {item.content}".lower()
        matches = self.blacklist_pattern.findall(text)

        if matches:
            matched_keywords = set(match.lower() for match in matches)
            logger.debug(f"新闻被黑名单过滤，匹配到关键词: {matched_keywords}, 标题: {item.title}")
            return True, matched_keywords

        return False, set()

    def filter_news(self, items: List[RawNewsItem], min_score: int = 10) -> List[RawNewsItem]:
        """
        筛选新闻，保留得分高于阈值且不在黑名单中的新闻
        :param items: 原始新闻项列表
        :param min_score: 最低得分阈值
        :return: 筛选后的新闻项列表
        """
        filtered = []
        total = len(items)
        blacklist_count = 0
        low_score_count = 0

        for item in items:
            # 先检查黑名单
            is_blacklist, _ = self.is_blacklisted(item)
            if is_blacklist:
                blacklist_count += 1
                continue

            # 计算优先级得分
            score, _ = self.calculate_priority_score(item)
            if score >= min_score:
                filtered.append(item)
            else:
                low_score_count += 1

        logger.info(f"预筛选结果: 总数{total} → 保留{len(filtered)} "
                   f"(黑名单过滤{blacklist_count}条, 低分过滤{low_score_count}条)")

        return filtered

    def filter_news_with_scores(self, items: List[RawNewsItem], min_score: int = 10) -> List[Tuple[RawNewsItem, int, Set[str]]]:
        """
        筛选新闻并返回得分和匹配关键词
        :param items: 原始新闻项列表
        :param min_score: 最低得分阈值
        :return: (新闻项, 得分, 匹配关键词)列表
        """
        filtered = []
        total = len(items)
        blacklist_count = 0
        low_score_count = 0

        for item in items:
            # 先检查黑名单
            is_blacklist, _ = self.is_blacklisted(item)
            if is_blacklist:
                blacklist_count += 1
                continue

            # 计算优先级得分
            score, matched_keywords = self.calculate_priority_score(item)
            if score >= min_score:
                filtered.append((item, score, matched_keywords))
            else:
                low_score_count += 1

        logger.info(f"预筛选结果: 总数{total} → 保留{len(filtered)} "
                   f"(黑名单过滤{blacklist_count}条, 低分过滤{low_score_count}条)")

        return filtered
