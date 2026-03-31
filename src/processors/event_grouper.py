#!/usr/bin/env python3
"""
事件分组处理器
自动将同事件的新闻归为一组
"""
from typing import List, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime
import uuid
from src.models.news import ProcessedNewsItem
from src.utils.similarity import calculate_news_similarity
from src.utils.common import setup_logger

logger = setup_logger("event_grouper")

@dataclass
class Event:
    """事件数据类"""
    event_id: str
    title: str  # 事件主标题（取最高评分新闻的标题）
    main_news: ProcessedNewsItem  # 主新闻（最高评分/最新）
    news_list: List[ProcessedNewsItem] = field(default_factory=list)
    entities: List[str] = field(default_factory=list)
    max_grade: str = "B"
    max_score: int = 0
    start_time: datetime = field(default_factory=datetime.now)
    end_time: datetime = field(default_factory=datetime.now)
    news_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "event_id": self.event_id,
            "title": self.title,
            "max_grade": self.max_grade,
            "max_score": self.max_score,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "news_count": self.news_count,
            "entities": self.entities,
            "news_list": [item.to_frontend_dict() for item in self.news_list]
        }

class EventGrouper:
    """事件分组处理器"""

    def __init__(self, entity_threshold: int = 3, similarity_threshold: float = 0.85):
        self.entity_threshold = entity_threshold
        self.similarity_threshold = similarity_threshold
        self.grade_order = {"S": 5, "A+": 4, "A": 3, "B": 2, "C": 1}

    def group_news(self, news_items: List[ProcessedNewsItem]) -> List[Event]:
        """
        将新闻列表分组为事件
        :param news_items: 处理后的新闻列表
        :return: 事件列表
        """
        if not news_items:
            return []

        # 按发布时间升序排序，先处理早的新闻
        sorted_news = sorted(news_items, key=lambda x: x.published_at)
        events: List[Event] = []

        for news in sorted_news:
            matched_event = None
            max_similarity = 0.0

            # 查找最匹配的事件
            for event in events:
                # 和事件中的每条新闻比较，取最高相似度
                event_max_sim = 0.0
                for event_news in event.news_list:
                    sim = calculate_news_similarity(
                        news, event_news,
                        entity_threshold=self.entity_threshold,
                        similarity_threshold=self.similarity_threshold
                    )
                    if sim > event_max_sim:
                        event_max_sim = sim

                if event_max_sim > max_similarity and event_max_sim >= self.similarity_threshold:
                    max_similarity = event_max_sim
                    matched_event = event

            if matched_event:
                # 添加到已有事件
                matched_event.news_list.append(news)
                # 更新事件属性
                self._update_event_properties(matched_event)
            else:
                # 创建新事件
                new_event = self._create_new_event(news)
                events.append(new_event)

        # 过滤掉只有1条新闻的事件（不算成事件）
        events = [e for e in events if e.news_count >= 2]

        # 按事件重要性排序（最高评分降序，新闻数量降序）
        events.sort(key=lambda e: (self.grade_order[e.max_grade], e.max_score, e.news_count), reverse=True)

        # 给每条新闻添加event_id标记
        for event in events:
            for news in event.news_list:
                news.event_id = event.event_id

        logger.info(f"事件分组完成: {len(news_items)}条新闻 → {len(events)}个事件")
        return events

    def _create_new_event(self, news: ProcessedNewsItem) -> Event:
        """创建新事件"""
        event_id = str(uuid.uuid4())[:8]  # 8位UUID作为事件ID
        return Event(
            event_id=event_id,
            title=news.chinese_title,
            main_news=news,
            news_list=[news],
            entities=news.entities.copy(),
            max_grade=news.grade,
            max_score=news.score,
            start_time=news.published_at,
            end_time=news.published_at,
            news_count=1
        )

    def _update_event_properties(self, event: Event):
        """更新事件属性"""
        # 更新新闻数量
        event.news_count = len(event.news_list)

        # 更新时间范围
        publish_times = [n.published_at for n in event.news_list]
        event.start_time = min(publish_times)
        event.end_time = max(publish_times)

        # 找到最高评分的新闻作为主新闻
        event.news_list.sort(key=lambda x: (self.grade_order[x.grade], x.score), reverse=True)
        main_news = event.news_list[0]
        event.title = main_news.chinese_title
        event.main_news = main_news
        event.max_grade = main_news.grade
        event.max_score = main_news.score

        # 更新实体集合（合并所有新闻的实体，去重）
        all_entities = set()
        for n in event.news_list:
            all_entities.update(n.entities)
        event.entities = sorted(list(all_entities))
