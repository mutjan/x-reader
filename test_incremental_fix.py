#!/usr/bin/env python3
"""
测试增量更新修复：验证原有事件不会丢失
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime, timedelta
from src.processors.event_grouper import EventGrouper
from src.models.news import ProcessedNewsItem

def test_existing_events_preserved():
    """测试没有新匹配新闻时，原有事件不会丢失"""
    grouper = EventGrouper(similarity_threshold=0.85)

    # 创建初始新闻和事件
    openai_news_1 = ProcessedNewsItem(
        id="news1",
        original_title="OpenAI releases GPT-5",
        original_content="OpenAI released GPT-5.",
        source="TechCrunch",
        url="http://example.com/news1",
        published_at=datetime.now() - timedelta(hours=2),
        chinese_title="OpenAI发布GPT-5",
        summary="OpenAI发布GPT-5大模型",
        grade="A",
        score=85,
        entities=["OpenAI", "GPT-5"]
    )

    anthropic_news = ProcessedNewsItem(
        id="news2",
        original_title="Anthropic releases Claude 3",
        original_content="Anthropic released Claude 3.",
        source="TechCrunch",
        url="http://example.com/news2",
        published_at=datetime.now() - timedelta(hours=3),
        chinese_title="Anthropic发布Claude 3",
        grade="A",
        score=88,
        entities=["Anthropic", "Claude 3"]
    )

    # 初始分组
    initial_events = grouper.group_news([openai_news_1, anthropic_news])
    print(f"初始分组：{len(initial_events)}个事件")
    for event in initial_events:
        print(f"  - {event.title} (新闻数: {event.news_count})")

    # 转换为存储格式
    existing_groups = grouper._events_to_dict(initial_events)

    # 新增一条完全不相关的新闻
    google_news = ProcessedNewsItem(
        id="news3",
        original_title="Google releases Gemini 2",
        original_content="Google released Gemini 2.",
        source="Google Blog",
        url="http://example.com/news3",
        published_at=datetime.now(),
        chinese_title="谷歌发布Gemini 2",
        summary="谷歌发布Gemini 2大模型",
        grade="A",
        score=86,
        entities=["Google", "Gemini 2"]
    )

    # 所有有效新闻包括原有和新增
    all_news = [openai_news_1, anthropic_news, google_news]

    # 增量分组：只传入新的Google新闻
    updated_events = grouper.incremental_group(existing_groups, [google_news], all_news)

    print(f"\n增量更新后：{len(updated_events)}个事件")
    for event in updated_events:
        print(f"  - {event.title} (新闻数: {event.news_count})")

    # 验证原有事件都保留了
    assert len(updated_events) == 3, "应该有3个事件（原有2个 + 新的1个）"

    event_titles = [e.title for e in updated_events]
    assert "OpenAI发布GPT-5" in event_titles, "OpenAI事件应该保留"
    assert "Anthropic发布Claude 3" in event_titles, "Anthropic事件应该保留"
    assert "谷歌发布Gemini 2" in event_titles, "新的Google事件应该被创建"

    # 验证原有事件的新闻数量没有变化
    openai_event = next(e for e in updated_events if "GPT-5" in e.title)
    assert openai_event.news_count == 1, "OpenAI事件应该仍然有1条新闻"

    anthropic_event = next(e for e in updated_events if "Claude 3" in e.title)
    assert anthropic_event.news_count == 1, "Anthropic事件应该仍然有1条新闻"

    print("\n✅ 测试通过：原有事件在增量更新时被正确保留！")

    # 测试另一个场景：现有事件的新闻都不在新批次中，但应该仍然保留
    print("\n\n测试场景：现有事件的新闻都不在新批次中")
    # 转换当前事件为存储格式
    existing_groups2 = grouper._events_to_dict(updated_events)

    # 新增另一条完全不相关的新闻
    meta_news = ProcessedNewsItem(
        id="news4",
        original_title="Meta releases Llama 3",
        original_content="Meta released Llama 3.",
        source="Meta Blog",
        url="http://example.com/news4",
        published_at=datetime.now(),
        chinese_title="Meta发布Llama 3",
        summary="Meta发布Llama 3大模型",
        grade="A",
        score=84,
        entities=["Meta", "Llama 3"]
    )

    # 所有有效新闻包括之前的3条 + 新的1条
    all_news2 = all_news + [meta_news]

    # 增量分组：只传入新的Meta新闻
    updated_events2 = grouper.incremental_group(existing_groups2, [meta_news], all_news2)

    print(f"增量更新后：{len(updated_events2)}个事件")
    for event in updated_events2:
        print(f"  - {event.title} (新闻数: {event.news_count})")

    # 验证所有原有事件都保留了
    assert len(updated_events2) == 4, "应该有4个事件（原有3个 + 新的1个）"

    event_titles2 = [e.title for e in updated_events2]
    assert "OpenAI发布GPT-5" in event_titles2, "OpenAI事件应该保留"
    assert "Anthropic发布Claude 3" in event_titles2, "Anthropic事件应该保留"
    assert "谷歌发布Gemini 2" in event_titles2, "Google事件应该保留"
    assert "Meta发布Llama 3" in event_titles2, "新的Meta事件应该被创建"

    print("\n✅ 测试通过：即使没有匹配的新新闻，原有事件也不会丢失！")

if __name__ == "__main__":
    test_existing_events_preserved()
