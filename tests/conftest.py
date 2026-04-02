#!/usr/bin/env python3
"""
pytest共享fixture配置
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from datetime import datetime, timedelta
from src.models.news import ProcessedNewsItem
from src.processors.event_grouper import Event


@pytest.fixture
def event_group_fixture():
    """事件分组数据fixture，匹配event_groups.json存储格式"""
    return {
        "version": "1.0",
        "generated_at": "2026-04-02T12:00:00Z",
        "groups": {
            "event_001": {
                "event_id": "event_001",
                "title": "OpenAI发布GPT-5大模型",
                "max_grade": "A+",
                "max_score": 95,
                "start_time": "2026-04-01T08:00:00Z",
                "end_time": "2026-04-02T10:30:00Z",
                "news_count": 3,
                "entities": ["OpenAI", "GPT", "大模型", "AI"],
                "news_ids": ["news_1", "news_2", "news_3"]
            },
            "event_002": {
                "event_id": "event_002",
                "title": "Anthropic推出Claude 3.5系列模型",
                "max_grade": "A",
                "max_score": 88,
                "start_time": "2026-04-01T14:00:00Z",
                "end_time": "2026-04-01T16:30:00Z",
                "news_count": 2,
                "entities": ["Anthropic", "Claude", "大模型"],
                "news_ids": ["news_4", "news_5"]
            }
        }
    }


@pytest.fixture
def news_data_fixture():
    """新闻数据fixture，匹配news_data.json存储格式"""
    return {
        "version": "1.0",
        "generated_at": "2026-04-02T12:00:00Z",
        "news": {
            "2026-04-01": [
                {
                    "id": "news_1",
                    "title": "OpenAI发布GPT-5，支持100万上下文窗口",
                    "original_title": "OpenAI releases GPT-5 with 1M context window",
                    "summary": "OpenAI正式发布GPT-5大模型，上下文窗口提升至100万token，性能相比前代提升40%。",
                    "rating": "A",
                    "score": 85,
                    "type": "product",
                    "typeName": "产品发布",
                    "expansion": "",
                    "entities": ["OpenAI", "GPT", "大模型"],
                    "sourceLinks": [{"name": "TechCrunch", "url": "https://techcrunch.com/openai-gpt5"}],
                    "sources": 1,
                    "timestamp": 1774982400,
                    "published_at": "2026-04-01T08:00:00Z",
                    "source": "TechCrunch",
                    "url": "https://techcrunch.com/openai-gpt5",
                    "event_id": "event_001"
                },
                {
                    "id": "news_2",
                    "title": "GPT-5基准测试显示全任务SOTA性能",
                    "original_title": "GPT-5 benchmarks show state-of-the-art performance across all tasks",
                    "summary": "第三方基准测试显示，GPT-5在推理、编码、多模态等所有任务上均超越现有模型，达到新的SOTA水平。",
                    "rating": "A+",
                    "score": 95,
                    "type": "research",
                    "typeName": "研究成果",
                    "expansion": "",
                    "entities": ["OpenAI", "GPT", "大模型", "AI"],
                    "sourceLinks": [{"name": "VentureBeat", "url": "https://venturebeat.com/gpt5-benchmarks"}],
                    "sources": 1,
                    "timestamp": 1775004000,
                    "published_at": "2026-04-01T14:00:00Z",
                    "source": "VentureBeat",
                    "url": "https://venturebeat.com/gpt5-benchmarks",
                    "event_id": "event_001"
                },
                {
                    "id": "news_4",
                    "title": "Anthropic发布Claude 3.5，推理能力显著提升",
                    "original_title": "Anthropic releases Claude 3.5 with improved reasoning capabilities",
                    "summary": "Anthropic推出Claude 3.5系列模型，推理能力提升30%，响应速度加快2倍。",
                    "rating": "A",
                    "score": 88,
                    "type": "product",
                    "typeName": "产品发布",
                    "expansion": "",
                    "entities": ["Anthropic", "Claude", "大模型"],
                    "sourceLinks": [{"name": "Anthropic Blog", "url": "https://anthropic.com/claude-3-5"}],
                    "sources": 1,
                    "timestamp": 1775004000,
                    "published_at": "2026-04-01T14:00:00Z",
                    "source": "Anthropic Blog",
                    "url": "https://anthropic.com/claude-3-5",
                    "event_id": "event_002"
                },
                {
                    "id": "news_5",
                    "title": "Claude 3.5编码基准测试超越GPT-4",
                    "original_title": "Claude 3.5 outperforms GPT-4 in coding benchmarks",
                    "summary": "独立测试显示，Claude 3.5在编码和数学推理任务上的表现优于GPT-4，成为新的编程首选模型。",
                    "rating": "A",
                    "score": 87,
                    "type": "research",
                    "typeName": "研究成果",
                    "expansion": "",
                    "entities": ["Anthropic", "Claude", "大模型"],
                    "sourceLinks": [{"name": "Hacker News", "url": "https://news.ycombinator.com/claude-3-5-coding"}],
                    "sources": 1,
                    "timestamp": 1775013000,
                    "published_at": "2026-04-01T16:30:00Z",
                    "source": "Hacker News",
                    "url": "https://news.ycombinator.com/claude-3-5-coding",
                    "event_id": "event_002"
                }
            ],
            "2026-04-02": [
                {
                    "id": "news_3",
                    "title": "OpenAI公布GPT-5 API定价和可用性",
                    "original_title": "OpenAI announces GPT-5 API pricing and availability",
                    "summary": "OpenAI宣布GPT-5 API开放申请，定价为每千token 0.01美元，预计下周全面开放。",
                    "rating": "A",
                    "score": 88,
                    "type": "product",
                    "typeName": "产品发布",
                    "expansion": "",
                    "entities": ["OpenAI", "GPT", "API", "大模型"],
                    "sourceLinks": [{"name": "OpenAI Blog", "url": "https://openai.com/blog/gpt5-api"}],
                    "sources": 1,
                    "timestamp": 1775087400,
                    "published_at": "2026-04-02T10:30:00Z",
                    "source": "OpenAI Blog",
                    "url": "https://openai.com/blog/gpt5-api",
                    "event_id": "event_001"
                },
                {
                    "id": "news_6",
                    "title": "特斯拉发布Optimus Gen 2人形机器人",
                    "original_title": "Tesla unveils new Optimus Gen 2 humanoid robot",
                    "summary": "特斯拉推出第二代Optimus人形机器人，灵巧度和移动能力大幅提升，可完成更多复杂任务。",
                    "rating": "A",
                    "score": 86,
                    "type": "product",
                    "typeName": "产品发布",
                    "expansion": "",
                    "entities": ["特斯拉", "机器人", "AI"],
                    "sourceLinks": [{"name": "Tesla Blog", "url": "https://tesla.com/optimus-gen2"}],
                    "sources": 1,
                    "timestamp": 1775082000,
                    "published_at": "2026-04-02T09:00:00Z",
                    "source": "Tesla Blog",
                    "url": "https://tesla.com/optimus-gen2",
                    "event_id": None
                }
            ]
        }
    }


@pytest.fixture
def full_event_object_fixture(news_data_fixture):
    """完整事件对象fixture，包含嵌套的新闻条目"""
    # 创建ProcessedNewsItem对象
    news_items = []
    for date_news in news_data_fixture["news"].values():
        for news_data in date_news:
            if news_data["event_id"] == "event_001":
                item = ProcessedNewsItem.from_dict(news_data)
                news_items.append(item)

    # 按发布时间排序
    news_items.sort(key=lambda x: x.published_at)

    # 创建事件对象
    event = Event(
        event_id="event_001",
        title="OpenAI发布GPT-5大模型",
        main_news=news_items[1],  # 最高评分的新闻作为主新闻
        news_list=news_items,
        entities=["OpenAI", "GPT", "大模型", "AI", "API"],
        max_grade="A+",
        max_score=95,
        start_time=datetime.fromisoformat("2026-04-01T08:00:00Z"),
        end_time=datetime.fromisoformat("2026-04-02T10:30:00Z"),
        news_count=3
    )

    return event
