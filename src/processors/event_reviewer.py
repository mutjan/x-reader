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
from src.config.settings import DATA_DIR, TEMP_DIR, EVENT_GROUPS_FILE

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
        prompt_file = os.path.join(TEMP_DIR, "_event_grouping_review_prompt.txt")
        os.makedirs(TEMP_DIR, exist_ok=True)
        with open(prompt_file, 'w', encoding='utf-8') as f:
            f.write(prompt)
        logger.info(f"复查提示词已生成: {prompt_file}（共{len(new_items)}条新新闻，{len(candidates)}条有候选）")
        return prompt_file
