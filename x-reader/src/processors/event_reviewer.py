#!/usr/bin/env python3
"""
事件分组复查处理器（Agent review）
在脚本自动分组完成后，对分组结果进行Agent复查验证
"""
from typing import List, Dict, Any, Optional
from datetime import datetime
import os
import uuid
import json

from src.models.news import ProcessedNewsItem
from src.utils.similarity import calculate_news_similarity
from src.utils.common import setup_logger, save_json, load_json
from src.config import settings as settings_mod

logger = setup_logger("event_reviewer")

REVIEW_PROMPT_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "prompts",
    "event_grouping_review.md"
)


class EventGroupReviewer:
    """事件分组复查器"""

    def __init__(self, entity_threshold: int = 3, review_similarity_threshold: float = 0.55):
        self.entity_threshold = entity_threshold
        # review阈值(0.55)低于分组阈值(0.65)，扩大复查面
        self.review_similarity_threshold = review_similarity_threshold
        self.max_candidates_per_news = 5

    def _load_prompt_template(self) -> str:
        """加载提示词模板文件"""
        if not os.path.exists(REVIEW_PROMPT_FILE):
            logger.error(f"提示词模板文件不存在: {REVIEW_PROMPT_FILE}")
            return ""
        with open(REVIEW_PROMPT_FILE, 'r', encoding='utf-8') as f:
            return f.read()

    def generate_review_prompt(
        self,
        new_items: List[ProcessedNewsItem],
        events: List[Any],
        all_items: List[ProcessedNewsItem]
    ) -> str:
        """
        生成复查提示词
        Args:
            new_items: 本批次新新闻
            events: 当前事件分组列表（Event对象）
            all_items: 所有有效新闻条目
        Returns:
            写入的提示词文件绝对路径
        """
        template = self._load_prompt_template()
        if not template:
            return ""

        # 1. 构建现有事件分组概要
        event_summary = []
        for event in events:
            event_summary.append({
                "group_id": event.event_id,
                "event_title": event.title,
                "entities": event.entities[:10],
                "news_ids": [n.id for n in event.news_list],
                "max_grade": event.max_grade,
                "max_score": event.max_score,
                "news_count": event.news_count,
            })
        event_groups_text = json.dumps(event_summary, ensure_ascii=False, indent=2)

        # 2. 构建新新闻列表 + 当前归属标记
        new_items_summary = []
        for news in new_items:
            current_event_id = None
            for event in events:
                if news.id in [n.id for n in event.news_list]:
                    current_event_id = event.event_id
                    break
            new_items_summary.append({
                "id": news.id,
                "title": news.chinese_title,
                "summary": news.summary[:200] if news.summary else "",
                "entities": news.entities,
                "current_event_id": current_event_id,
            })
        new_items_text = json.dumps(new_items_summary, ensure_ascii=False, indent=2)

        # 3. 候选筛选 — 找高相似度事件（D-02）
        candidates = []
        for news in new_items:
            high_sim_events = []
            for event in events:
                max_sim = 0.0
                for event_news in event.news_list:
                    sim = calculate_news_similarity(
                        news, event_news,
                        entity_threshold=self.entity_threshold,
                        similarity_threshold=self.review_similarity_threshold
                    )
                    if sim > max_sim:
                        max_sim = sim
                if max_sim >= self.review_similarity_threshold:
                    high_sim_events.append({
                        "event_id": event.event_id,
                        "event_title": event.title,
                        "similarity": round(max_sim, 3),
                        "news_in_event": [
                            {"id": n.id, "title": n.chinese_title}
                            for n in event.news_list[:5]
                        ],
                    })
            # 按相似度降序，取top N
            high_sim_events.sort(key=lambda x: x["similarity"], reverse=True)
            high_sim_events = high_sim_events[:self.max_candidates_per_news]

            if high_sim_events:
                candidates.append({
                    "news_id": news.id,
                    "news_title": news.chinese_title,
                    "assigned_event_id": None,
                    "high_similarity_events": high_sim_events,
                })

        candidates_text = json.dumps(candidates, ensure_ascii=False, indent=2)

        # 4. 替换占位符
        prompt = template.replace("{{event_groups_list}}", event_groups_text)
        prompt = prompt.replace("{{new_items_list}}", new_items_text)
        prompt = prompt.replace("{{candidates_list}}", candidates_text)

        # 5. 写入临时文件
        prompt_file = os.path.join(settings_mod.TEMP_DIR, "_event_grouping_review_prompt.txt")
        os.makedirs(settings_mod.TEMP_DIR, exist_ok=True)
        with open(prompt_file, 'w', encoding='utf-8') as f:
            f.write(prompt)
        logger.info(f"复查提示词已生成: {prompt_file}（共{len(new_items)}条新新闻，{len(candidates)}条有候选）")
        return prompt_file

    def _update_event_properties(self, event: Any) -> None:
        """更新事件属性（复用EventGrouper的逻辑）"""
        from src.processors.event_grouper import EventGrouper
        grouper = EventGrouper()
        grouper._update_event_properties(event)

    def _find_news_by_id(self, news_id: str, events: List[Any]) -> Optional[ProcessedNewsItem]:
        """在所有事件中查找指定ID的新闻"""
        for event in events:
            for news in event.news_list:
                if news.id == news_id:
                    return news
        return None

    def apply_corrections(
        self,
        corrections: List[Dict[str, Any]],
        events: List[Any],
        batch_id: Optional[str] = None
    ) -> tuple:
        """
        应用AI复查修正到事件列表
        Args:
            corrections: 修正列表，每项含 {"news_id", "current_event_id", "suggested_event_id", "reason"}
            events: Event对象列表（会被就地修改）
            batch_id: 批次标识
        Returns:
            (success: bool, audit_entry: dict)
        """
        if not corrections:
            audit_entry = {
                "timestamp": datetime.now().isoformat(),
                "batch_id": batch_id or "unknown",
                "corrections_applied": 0,
                "details": [],
                "note": "复查无修正"
            }
            return self._write_audit_log(audit_entry)

        # 构建 event_id -> Event 映射
        event_map: Dict[str, Any] = {}
        for event in events:
            event_map[event.event_id] = event

        # 构建 news_id -> (Event, news_item) 映射
        news_to_event: Dict[str, tuple] = {}
        for event in events:
            for news in event.news_list:
                news_to_event[news.id] = (event, news)

        # 验证并收集修正
        valid_corrections = []
        for correction in corrections:
            news_id = correction.get("news_id", "")
            from_event_id = correction.get("current_event_id")
            to_event_id = correction.get("suggested_event_id", "")
            reason = correction.get("reason", "")

            # 检查新闻是否存在
            if news_id not in news_to_event:
                # 新闻不在当前事件列表中（可能是新新闻，还没被分组）
                # 这种情况允许创建新事件
                pass

            # 验证目标事件ID
            if to_event_id != "new_event" and to_event_id not in event_map:
                logger.warning(f"目标事件ID不存在: {to_event_id}，跳过该修正 (news_id={news_id})")
                continue

            valid_corrections.append({
                "news_id": news_id,
                "from_event_id": from_event_id,
                "to_event_id": to_event_id,
                "reason": reason,
                "new_event_title": correction.get("new_event_title", ""),
            })

        if not valid_corrections:
            audit_entry = {
                "timestamp": datetime.now().isoformat(),
                "batch_id": batch_id or "unknown",
                "corrections_applied": 0,
                "details": [],
                "note": "无有效修正"
            }
            return self._write_audit_log(audit_entry)

        # 应用修正
        from src.processors.event_grouper import Event
        for corr in valid_corrections:
            news_id = corr["news_id"]
            from_event_id = corr["from_event_id"]
            to_event_id = corr["to_event_id"]

            # 先获取新闻对象引用（在移除之前）
            news_item = self._find_news_by_id(news_id, events)
            if not news_item:
                # 如果新闻不在任何事件中，尝试从 news_to_event 映射中获取
                if news_id in news_to_event:
                    news_item = news_to_event[news_id][1]
                else:
                    logger.warning(f"新闻ID不存在: {news_id}，跳过该修正")
                    continue

            # 从原事件移除
            if from_event_id and from_event_id in event_map:
                from_event = event_map[from_event_id]
                from_event.news_list = [n for n in from_event.news_list if n.id != news_id]
                if from_event.news_list:
                    self._update_event_properties(from_event)

            # 添加到目标事件或创建新事件
            if to_event_id == "new_event":
                new_event = Event(
                    event_id=str(uuid.uuid4())[:8],
                    title=corr.get("new_event_title", news_item.chinese_title),
                    main_news=news_item,
                    news_list=[news_item],
                    entities=news_item.entities.copy() if news_item.entities else [],
                    max_grade=news_item.grade or "B",
                    max_score=news_item.score or 0,
                    start_time=news_item.published_at,
                    end_time=news_item.published_at,
                    news_count=1
                )
                events.append(new_event)
                event_map[new_event.event_id] = new_event
            elif to_event_id in event_map:
                if news_item not in event_map[to_event_id].news_list:
                    event_map[to_event_id].news_list.append(news_item)
                    self._update_event_properties(event_map[to_event_id])

        # 写审计日志
        audit_details = []
        for corr in valid_corrections:
            audit_details.append({
                "news_id": corr["news_id"],
                "from_event_id": corr["from_event_id"],
                "to_event_id": corr["to_event_id"],
                "reason": corr["reason"],
            })
        audit_entry = {
            "timestamp": datetime.now().isoformat(),
            "batch_id": batch_id or "unknown",
            "corrections_applied": len(audit_details),
            "details": audit_details,
        }
        return self._write_audit_log(audit_entry)

    def _write_audit_log(self, audit_entry: Dict[str, Any]) -> tuple:
        """
        写审计日志到文件（追加模式）
        Returns:
            (success: bool, audit_entry: dict)
        """
        log_path = os.path.join(settings_mod.DATA_DIR, "event_review_log.json")
        log_data = load_json(log_path, {"entries": []})
        log_data["entries"].append(audit_entry)
        if not save_json(log_data, log_path):
            logger.error(f"审计日志写入失败: {log_path}")
            return (False, audit_entry)
        logger.info(f"审计日志已写入: {log_path}（共{len(log_data['entries'])}条记录）")
        return (True, audit_entry)


def load_review_corrections(result_file: str) -> List[Dict[str, Any]]:
    """
    加载Agent复查结果JSON文件
    Args:
        result_file: _event_grouping_review_result.json 的路径
    Returns:
        修正列表
    """
    if not os.path.exists(result_file):
        logger.error(f"复查结果文件不存在: {result_file}")
        return []
    results = load_json(result_file, [])
    if not isinstance(results, list):
        logger.error(f"复查结果格式错误: 期望JSON数组，实际 {type(results)}")
        return []
    logger.info(f"加载复查结果: {len(results)} 条修正")
    return results
