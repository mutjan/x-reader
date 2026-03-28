#!/usr/bin/env python3
"""
新闻去重模块
基于URL、标题相似度、内容相似度等多维度去重
"""
from typing import List, Dict, Set, Tuple
from collections import defaultdict
import hashlib

from src.models.news import RawNewsItem, ProcessedNewsItem
from src.utils.common import setup_logger, normalize_url, is_similar_text
from src.config.settings import PROCESSED_IDS_FILE
from src.utils.common import load_json, save_json

logger = setup_logger("duplicate")

class DuplicateRemover:
    """新闻去重器"""

    def __init__(self):
        self.processed_ids: Set[str] = self._load_processed_ids()
        self.url_cache: Dict[str, RawNewsItem] = {}
        self.title_cache: Dict[str, RawNewsItem] = {}

    def _load_processed_ids(self) -> Set[str]:
        """加载已处理的新闻ID集合"""
        data = load_json(PROCESSED_IDS_FILE, [])
        return set(data)

    def save_processed_ids(self, max_ids: int = 5000) -> None:
        """保存已处理的新闻ID集合"""
        # 只保留最近的max_ids条
        ids_list = list(self.processed_ids)[-max_ids:]
        save_json(ids_list, PROCESSED_IDS_FILE)
        logger.info(f"已保存 {len(ids_list)} 条处理记录")

    def add_processed_id(self, item_id: str) -> None:
        """添加已处理的新闻ID"""
        self.processed_ids.add(item_id)

    def is_processed(self, item_id: str) -> bool:
        """检查新闻是否已经处理过"""
        return item_id in self.processed_ids

    def deduplicate_raw(self, items: List[RawNewsItem]) -> List[RawNewsItem]:
        """
        对原始新闻项进行去重
        :param items: 原始新闻项列表
        :return: 去重后的新闻项列表
        """
        unique_items = []
        url_counts: Dict[str, int] = defaultdict(int)
        duplicate_count = 0
        processed_count = 0

        for item in items:
            item_id = item.get_unique_id()

            # 检查是否已经处理过
            if self.is_processed(item_id):
                processed_count += 1
                continue

            # 基于URL去重
            normalized_url = normalize_url(item.url)
            if normalized_url and normalized_url in url_counts:
                url_counts[normalized_url] += 1
                duplicate_count += 1
                continue

            # 基于标题相似度去重
            is_duplicate = False
            for existing_item in unique_items:
                if is_similar_text(item.title, existing_item.title, threshold=0.8):
                    duplicate_count += 1
                    is_duplicate = True
                    break

            if not is_duplicate:
                unique_items.append(item)
                if normalized_url:
                    url_counts[normalized_url] += 1

        logger.info(f"原始去重结果: 总数{len(items)} → 保留{len(unique_items)} "
                   f"(重复{duplicate_count}条, 已处理过{processed_count}条)")

        return unique_items

    def deduplicate_processed(self, items: List[ProcessedNewsItem]) -> List[ProcessedNewsItem]:
        """
        对处理后的新闻项进行去重
        :param items: 处理后的新闻项列表
        :return: 去重后的新闻项列表
        """
        unique_items = []
        seen_ids = set()
        duplicate_count = 0

        for item in items:
            if item.id in seen_ids:
                duplicate_count += 1
                continue

            # 检查内容相似度
            is_duplicate = False
            for existing_item in unique_items:
                # 标题高度相似
                if is_similar_text(item.chinese_title, existing_item.chinese_title, threshold=0.7):
                    duplicate_count += 1
                    is_duplicate = True
                    break

                # 摘要高度相似
                if is_similar_text(item.summary, existing_item.summary, threshold=0.7):
                    duplicate_count += 1
                    is_duplicate = True
                    break

            if not is_duplicate:
                unique_items.append(item)
                seen_ids.add(item.id)

        logger.info(f"处理后去重结果: 总数{len(items)} → 保留{len(unique_items)} (重复{duplicate_count}条)")
        return unique_items

    def merge_similar_news(self, items: List[ProcessedNewsItem]) -> List[ProcessedNewsItem]:
        """
        合并相似新闻，保留信息更全面的版本
        :param items: 处理后的新闻项列表
        :return: 合并后的新闻项列表
        """
        if len(items) <= 1:
            return items

        merged = []
        used_indices = set()

        for i, item in enumerate(items):
            if i in used_indices:
                continue

            # 查找所有相似的新闻
            similar_items = [item]
            for j, other in enumerate(items[i+1:], start=i+1):
                if j in used_indices:
                    continue

                # 判断是否相似
                if (is_similar_text(item.chinese_title, other.chinese_title, threshold=0.6) or
                    is_similar_text(item.summary, other.summary, threshold=0.6)):
                    similar_items.append(other)
                    used_indices.add(j)

            if len(similar_items) == 1:
                merged.append(item)
            else:
                # 选择得分最高、内容最丰富的作为主版本
                main_item = max(similar_items, key=lambda x: (x.score, len(x.summary)))
                merged.append(main_item)
                logger.debug(f"合并了 {len(similar_items)} 条相似新闻: {main_item.chinese_title}")

        logger.info(f"合并相似新闻: 总数{len(items)} → 合并后{len(merged)}条")
        return merged

    def get_duplicate_stats(self) -> Dict[str, int]:
        """获取去重统计信息"""
        return {
            "total_processed": len(self.processed_ids)
        }
