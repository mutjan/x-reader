#!/usr/bin/env python3
"""
新闻去重模块
基于URL、标题相似度、内容相似度等多维度去重
"""
from typing import List, Dict, Set, Tuple, Optional
from collections import defaultdict
import hashlib

from src.models.news import RawNewsItem, ProcessedNewsItem
from src.utils.common import setup_logger, is_similar_text
from src.utils.url import normalize_url
from src.config.settings import PROCESSED_IDS_FILE, DATA_FILE, TEMP_DIR
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

    def save_processed_ids(self, max_ids: int = 10000) -> None:
        """保存已处理的新闻ID集合"""
        # 只保留最近的max_ids条（约7天的量）
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

    def _is_similar_news(self, item: ProcessedNewsItem, other_title: str, other_summary: str = "",
                          other_entities: Optional[List[str]] = None) -> bool:
        """
        判断两条新闻是否相似
        :param item: 新闻项（有完整属性）
        :param other_title: 另一条新闻的标题
        :param other_summary: 另一条新闻的摘要
        :param other_entities: 另一条新闻的实体列表
        :return: 是否相似
        """
        # 1. 实体有交集优先判断为相似（相同实体说明是同一主题）
        entity_overlap = False
        common_entity_count = 0
        if item.entities and other_entities:
            common_entities = set(item.entities) & set(other_entities)
            common_entity_count = len(common_entities)
            if common_entity_count >= 1:
                entity_overlap = True

        # 2. 根据实体交集数量调整相似度阈值
        if common_entity_count >= 2:
            threshold = 0.4
        elif common_entity_count == 1:
            threshold = 0.45
        else:
            threshold = 0.5

        # 3. 标题或摘要相似
        text_similar = (is_similar_text(item.chinese_title, other_title, threshold=threshold) or
                        (other_summary and is_similar_text(item.summary, other_summary, threshold=threshold)))

        # 4. 实体有交集且文本有一定相似度则判定为相似
        return (entity_overlap and text_similar) or text_similar

    def _load_historical_news(self) -> Dict[str, dict]:
        """
        加载历史新闻数据，返回 {id: item_dict} 的映射
        """
        import os
        if not os.path.exists(DATA_FILE):
            return {}

        existing_data = load_json(DATA_FILE, {})

        # 兼容旧的列表格式数据
        if isinstance(existing_data, list):
            result = {}
            for item in existing_data:
                try:
                    result[item["id"]] = item
                except (KeyError, TypeError):
                    pass
            return result

        # 按日期分组格式，展开为id映射
        result = {}
        for date_key, items in existing_data.items():
            if not isinstance(items, list):
                continue
            for item in items:
                try:
                    result[item["id"]] = item
                except (KeyError, TypeError):
                    pass
        return result

    def _save_historical_news(self, historical_dict: dict) -> None:
        """
        将历史新闻字典保存回按日期分组格式
        """
        import os
        from datetime import datetime, timedelta

        # 按日期分组
        news_by_date = {}
        for item in historical_dict.values():
            try:
                time_field = item.get("processed_at", item.get("published_at"))
                if isinstance(time_field, str):
                    date_key = time_field.split('T')[0]
                elif isinstance(time_field, (int, float)):
                    date_key = datetime.fromtimestamp(time_field).strftime('%Y-%m-%d')
                else:
                    continue

                if date_key not in news_by_date:
                    news_by_date[date_key] = []
                news_by_date[date_key].append(item)
            except Exception:
                continue

        # 每个日期内按时间降序排序
        for date in news_by_date:
            news_by_date[date].sort(key=lambda x: x.get("timestamp", 0), reverse=True)

        if os.path.exists(DATA_FILE):
            import shutil
            backup_filename = f"news_data.json.bak.{datetime.now().strftime('%Y%m%d%H%M%S')}"
            backup_file = os.path.join(TEMP_DIR, backup_filename)
            try:
                shutil.copy(DATA_FILE, backup_file)
                logger.info(f"已备份历史数据到: {backup_file}")
            except Exception as e:
                logger.warning(f"历史数据备份失败: {e}")

        save_json(news_by_date, DATA_FILE)

    def merge_similar_news(self, items: List[ProcessedNewsItem]) -> List[ProcessedNewsItem]:
        """
        合并相似新闻，保留信息更全面的版本。
        同时与历史新闻进行对比合并，避免同一事件在不同时间点被抓取后重复。
        :param items: 处理后的新闻项列表
        :return: 合并后的新闻项列表
        """
        if not items:
            return items

        # === 第一步：本轮新闻之间的合并 ===
        merged = []
        used_indices = set()

        for i, item in enumerate(items):
            if i in used_indices:
                continue

            similar_items = [item]
            for j, other in enumerate(items[i+1:], start=i+1):
                if j in used_indices:
                    continue

                if self._is_similar_news(item, other.chinese_title, other.summary, other.entities):
                    similar_items.append(other)
                    used_indices.add(j)

            if len(similar_items) == 1:
                merged.append(item)
            else:
                main_item = max(similar_items, key=lambda x: (x.score, len(x.summary)))
                # 合并来源链接
                all_source_links = []
                seen_urls = set()
                for s_item in similar_items:
                    for link in (s_item.sourceLinks or []):
                        if link["url"] not in seen_urls:
                            all_source_links.append(link)
                            seen_urls.add(link["url"])
                main_item.sourceLinks = all_source_links
                main_item.sources = len(all_source_links)
                merged.append(main_item)
                logger.debug(f"合并了 {len(similar_items)} 条相似新闻: {main_item.chinese_title}")

        if len(items) > 1:
            logger.info(f"合并相似新闻: 总数{len(items)} → 合并后{len(merged)}条")

        # === 第二步：与历史新闻合并 ===
        historical_dict = self._load_historical_news()
        if not historical_dict:
            return merged

        final_items = []
        historical_merged_count = 0

        for item in merged:
            item_id = item.id
            matched = False

            # 先检查ID是否已存在（精确匹配）
            if item_id in historical_dict:
                # ID匹配，更新历史条目
                existing = historical_dict[item_id]
                item_dict = item.to_dict()
                for key, value in item_dict.items():
                    if key not in ["published_at", "processed_at", "timestamp"]:
                        existing[key] = value
                # 合并来源链接
                if "sourceLinks" in item_dict:
                    existing_links = existing.get("sourceLinks", [])
                    existing_urls = {link["url"] for link in existing_links}
                    for link in item_dict["sourceLinks"]:
                        if link["url"] not in existing_urls:
                            existing_links.append(link)
                            existing_urls.add(link["url"])
                    existing["sourceLinks"] = existing_links
                    existing["sources"] = len(existing_links)
                historical_dict[item_id] = existing
                historical_merged_count += 1
                matched = True

            if not matched:
                # 按标题/摘要/实体与历史新闻做相似度匹配
                for hist_id, hist_item in historical_dict.items():
                    hist_title = hist_item.get("chinese_title", hist_item.get("title", "")).strip()
                    hist_summary = hist_item.get("summary", "").strip()
                    hist_entities = hist_item.get("entities", [])

                    if not hist_title:
                        continue

                    if self._is_similar_news(item, hist_title, hist_summary, hist_entities):
                        # 相似新闻，合并到历史条目
                        item_dict = item.to_dict()
                        existing = hist_item

                        # 选择得分更高的版本作为主版本
                        new_score = item.score
                        old_score = existing.get("score", 0)

                        if new_score > old_score:
                            # 新版本更好，用新版本替换（保留时间字段）
                            for key, value in item_dict.items():
                                if key not in ["published_at", "processed_at", "timestamp"]:
                                    existing[key] = value
                        else:
                            # 旧版本更好，只更新来源链接
                            pass

                        # 无论谁更好，都合并来源链接
                        if "sourceLinks" in item_dict:
                            existing_links = existing.get("sourceLinks", [])
                            existing_urls = {link["url"] for link in existing_links}
                            for link in item_dict["sourceLinks"]:
                                if link["url"] not in existing_urls:
                                    existing_links.append(link)
                                    existing_urls.add(link["url"])
                            existing["sourceLinks"] = existing_links
                            existing["sources"] = len(existing_links)

                        historical_dict[hist_id] = existing
                        historical_merged_count += 1
                        matched = True
                        logger.info(f"与历史新闻合并: [{item.chinese_title}] → [{hist_title}]")
                        break

            if not matched:
                final_items.append(item)

        if historical_merged_count > 0:
            logger.info(f"与历史新闻合并: {historical_merged_count}条已合并到历史数据, {len(final_items)}条为全新新闻")
            # 保存更新后的历史数据
            self._save_historical_news(historical_dict)
        else:
            logger.info(f"与历史新闻对比: 无重复，{len(final_items)}条均为全新新闻")

        return final_items

    def get_duplicate_stats(self) -> Dict[str, int]:
        """获取去重统计信息"""
        return {
            "total_processed": len(self.processed_ids)
        }
