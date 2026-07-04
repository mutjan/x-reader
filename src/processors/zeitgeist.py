#!/usr/bin/env python3
"""
时代情绪管理模块
动态跟踪当前科技行业热点趋势，为符合时代情绪的新闻提供加分机制
"""
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
import json
import os
from src.utils.common import setup_logger, load_json, save_json

logger = setup_logger("zeitgeist")

@dataclass
class TrendTopic:
    """热点话题"""
    keyword: str
    weight: float  # 权重 0.1-1.0
    category: str  # 分类：ai, hardware, internet, etc.
    description: str
    start_time: datetime
    end_time: datetime
    boost_value: int  # 加分值
    # 扩展字段，兼容原有upcoming_events中的数据
    category_name: Optional[str] = None
    heat_score: Optional[int] = None
    trend: Optional[str] = None
    trend_name: Optional[str] = None
    related_entities: List[str] = None
    status: str = "active"
    mentions_count: int = 0

    def __post_init__(self):
        """初始化后处理"""
        if self.related_entities is None:
            self.related_entities = []

class ZeitgeistManager:
    """时代情绪管理器"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        """初始化"""
        self.config_path = os.path.join(os.path.dirname(__file__), "../../config/zeitgeist.json")
        self.trends: List[TrendTopic] = []
        self._load_config()
        self._add_default_trends()

    def _load_config(self):
        """加载配置文件"""
        if os.path.exists(self.config_path):
            try:
                data = load_json(self.config_path)
                for trend_data in data.get("trends", []):
                    trend = TrendTopic(
                        keyword=trend_data["keyword"],
                        weight=trend_data.get("weight", 0.5),
                        category=trend_data.get("category", "ai"),
                        description=trend_data.get("description", ""),
                        start_time=datetime.fromisoformat(trend_data["start_time"]) if trend_data.get("start_time") else datetime.now(),
                        end_time=datetime.fromisoformat(trend_data["end_time"]) if trend_data.get("end_time") else datetime.now() + timedelta(days=30),
                        boost_value=trend_data.get("boost_value", 3),
                        category_name=trend_data.get("category_name"),
                        heat_score=trend_data.get("heat_score"),
                        trend=trend_data.get("trend"),
                        trend_name=trend_data.get("trend_name"),
                        related_entities=trend_data.get("related_entities"),
                        status=trend_data.get("status", "active"),
                        mentions_count=trend_data.get("mentions_count", 0)
                    )
                    self.trends.append(trend)
                logger.info(f"加载了 {len(self.trends)} 个时代情绪热点")
            except Exception as e:
                logger.error(f"加载时代情绪配置失败: {e}")

    def _save_config(self):
        """保存配置到文件"""
        data = {
            "trends": [
                {
                    "keyword": trend.keyword,
                    "weight": trend.weight,
                    "category": trend.category,
                    "description": trend.description,
                    "start_time": trend.start_time.isoformat(),
                    "end_time": trend.end_time.isoformat(),
                    "boost_value": trend.boost_value,
                    "category_name": trend.category_name,
                    "heat_score": trend.heat_score,
                    "trend": trend.trend,
                    "trend_name": trend.trend_name,
                    "related_entities": trend.related_entities,
                    "status": trend.status,
                    "mentions_count": trend.mentions_count
                }
                for trend in self.trends
            ]
        }
        save_json(data, self.config_path)

    def _add_default_trends(self):
        """添加默认热点趋势"""
        default_trends = [
            # 2026年Q1 AI大模型迭代热点
            TrendTopic(
                keyword="DeepSeek",
                weight=0.9,
                category="ai",
                description="DeepSeek大模型迭代，国产大模型标杆",
                start_time=datetime(2026, 3, 1),
                end_time=datetime(2026, 4, 30),
                boost_value=5
            ),
            TrendTopic(
                keyword="Claude",
                weight=0.9,
                category="ai",
                description="Anthropic Claude模型更新",
                start_time=datetime(2026, 3, 1),
                end_time=datetime(2026, 4, 30),
                boost_value=4
            ),
            TrendTopic(
                keyword="GPT",
                weight=0.8,
                category="ai",
                description="OpenAI GPT模型更新",
                start_time=datetime(2026, 3, 1),
                end_time=datetime(2026, 4, 30),
                boost_value=4
            ),
            TrendTopic(
                keyword="Gemini",
                weight=0.7,
                category="ai",
                description="谷歌Gemini模型更新",
                start_time=datetime(2026, 3, 1),
                end_time=datetime(2026, 4, 30),
                boost_value=3
            ),
            TrendTopic(
                keyword="多模态",
                weight=0.8,
                category="ai",
                description="多模态大模型技术突破",
                start_time=datetime(2026, 3, 1),
                end_time=datetime(2026, 6, 30),
                boost_value=3
            ),
            TrendTopic(
                keyword="推理优化",
                weight=0.7,
                category="ai",
                description="大模型推理效率优化",
                start_time=datetime(2026, 3, 1),
                end_time=datetime(2026, 6, 30),
                boost_value=3
            ),
            TrendTopic(
                keyword="端侧AI",
                weight=0.8,
                category="ai",
                description="端侧大模型部署与应用",
                start_time=datetime(2026, 3, 1),
                end_time=datetime(2026, 6, 30),
                boost_value=4
            ),
            TrendTopic(
                keyword="AGI",
                weight=0.9,
                category="ai",
                description="通用人工智能相关进展",
                start_time=datetime(2026, 1, 1),
                end_time=datetime(2026, 12, 31),
                boost_value=5
            )
        ]

        # 避免重复添加
        existing_keywords = {t.keyword.lower() for t in self.trends}
        added = 0
        for trend in default_trends:
            if trend.keyword.lower() not in existing_keywords:
                self.trends.append(trend)
                added += 1

        if added > 0:
            logger.info(f"添加了 {added} 个默认热点趋势")
            self._save_config()

    def get_boost_for_content(self, title: str, content: str, entities: List[str] = None) -> Tuple[int, List[str]]:
        """
        检查内容是否符合当前时代情绪，返回加分值和匹配的热点关键词
        """
        now = datetime.now()
        total_boost = 0
        matched_trends = []

        content_text = (title + " " + content).lower()
        entities_lower = [e.lower() for e in (entities or [])]

        for trend in self.trends:
            # 检查是否在有效期内
            if not (trend.start_time <= now <= trend.end_time):
                continue

            # 主关键词匹配
            keyword_lower = trend.keyword.lower()
            is_matched = (keyword_lower in content_text) or (keyword_lower in entities_lower)

            # 如果主关键词不匹配，尝试匹配相关实体和关键词
            if not is_matched and trend.related_entities:
                for related in trend.related_entities:
                    related_lower = related.lower()
                    if (related_lower in content_text) or (related_lower in entities_lower):
                        is_matched = True
                        break

            if is_matched:
                total_boost += trend.boost_value
                matched_trends.append(trend.keyword)
                logger.debug(f"匹配时代情绪热点 '{trend.keyword}', 加分 {trend.boost_value}")

        # 最高加分不超过10分
        total_boost = min(total_boost, 10)
        return total_boost, matched_trends

    def add_trend(self, keyword: str, boost_value: int = 3, duration_days: int = 30,
                 category: str = "ai", description: str = "", weight: float = 0.5,
                 category_name: Optional[str] = None, heat_score: Optional[int] = None,
                 trend: Optional[str] = None, trend_name: Optional[str] = None,
                 related_entities: Optional[List[str]] = None, status: str = "active",
                 mentions_count: int = 0) -> bool:
        """添加新的热点趋势"""
        # 检查是否已存在
        for trend_obj in self.trends:
            if trend_obj.keyword.lower() == keyword.lower():
                logger.warning(f"热点 '{keyword}' 已存在")
                return False

        trend = TrendTopic(
            keyword=keyword,
            weight=weight,
            category=category,
            description=description,
            start_time=datetime.now(),
            end_time=datetime.now() + timedelta(days=duration_days),
            boost_value=boost_value,
            category_name=category_name,
            heat_score=heat_score,
            trend=trend,
            trend_name=trend_name,
            related_entities=related_entities,
            status=status,
            mentions_count=mentions_count
        )

        self.trends.append(trend)
        self._save_config()
        logger.info(f"已添加新热点趋势: {keyword}, 加分{boost_value}, 有效期{duration_days}天")
        return True

    def remove_trend(self, keyword: str) -> bool:
        """移除热点趋势"""
        for i, trend in enumerate(self.trends):
            if trend.keyword.lower() == keyword.lower():
                del self.trends[i]
                self._save_config()
                logger.info(f"已移除热点趋势: {keyword}")
                return True
        return False

    def list_current_trends(self, include_all: bool = False) -> List[Dict]:
        """列出当前有效的热点趋势"""
        now = datetime.now()
        return [
            {
                "keyword": trend.keyword,
                "category": trend.category,
                "category_name": trend.category_name,
                "description": trend.description,
                "boost_value": trend.boost_value,
                "expires_in": (trend.end_time - now).days,
                "weight": trend.weight,
                "heat_score": trend.heat_score,
                "trend": trend.trend,
                "trend_name": trend.trend_name,
                "related_entities": trend.related_entities,
                "status": trend.status,
                "mentions_count": trend.mentions_count
            }
            for trend in self.trends
            if include_all or (trend.start_time <= now <= trend.end_time)
        ]

# 全局实例
zeitgeist_manager = ZeitgeistManager()
