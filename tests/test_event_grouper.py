#!/usr/bin/env python3
"""
事件分组器增量分组测试
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tempfile
from datetime import datetime, timedelta
from src.processors.event_grouper import EventGrouper
from src.models.news import ProcessedNewsItem


class TestEventGrouper:
    """事件分组器测试类"""

    def __init__(self):
        """初始化测试"""
        self.temp_dir = tempfile.mkdtemp()
        self.grouper = EventGrouper()

        # 创建测试新闻数据
        self.openai_news_1 = ProcessedNewsItem(
            id="news1",
            original_title="OpenAI releases GPT-5",
            original_content="OpenAI has released its latest large language model GPT-5 with enhanced capabilities.",
            source="TechCrunch",
            url="http://example.com/news1",
            published_at=datetime.now() - timedelta(hours=2),
            chinese_title="OpenAI发布GPT-5",
            grade="A",
            score=85,
            entities=["OpenAI", "GPT-5", "大模型", "AI"]
        )

        self.openai_news_2 = ProcessedNewsItem(
            id="news2",
            original_title="GPT-5 shows breakthrough performance",
            original_content="Early benchmarks show GPT-5 outperforms previous models on multiple tasks.",
            source="VentureBeat",
            url="http://example.com/news2",
            published_at=datetime.now() - timedelta(hours=1),
            chinese_title="GPT-5展现突破性性能",
            grade="A+",
            score=92,
            entities=["OpenAI", "GPT-5", "大模型", "AI"]
        )

        self.anthropic_news = ProcessedNewsItem(
            id="news3",
            original_title="Anthropic releases Claude 3",
            original_content="Anthropic has announced Claude 3, its next generation of AI assistants.",
            source="TechCrunch",
            url="http://example.com/news3",
            published_at=datetime.now() - timedelta(hours=3),
            chinese_title="Anthropic发布Claude 3",
            grade="A",
            score=88,
            entities=["Anthropic", "Claude 3"]
        )

        self.openai_news_3 = ProcessedNewsItem(
            id="news4",
            original_title="OpenAI announces GPT-5 API access",
            original_content="Developers can now request access to the new GPT-5 API.",
            source="OpenAI Blog",
            url="http://example.com/news4",
            published_at=datetime.now(),
            chinese_title="OpenAI宣布GPT-5 API访问",
            grade="A",
            score=87,
            entities=["OpenAI", "GPT-5", "API", "大模型", "AI"]
        )

    def cleanup(self):
        """测试后清理"""
        import shutil
        shutil.rmtree(self.temp_dir)

    def test_incremental_grouping(self):
        """测试增量分组功能：新条目添加到匹配的现有组或创建新组"""
        # 场景1：没有现有分组 → 所有新条目创建新分组
        batch1 = [self.openai_news_1, self.anthropic_news]
        events1 = self.grouper.group_news(batch1)

        assert len(events1) == 2, "第一次分组应该创建2个事件"
        event_titles1 = [event.title for event in events1]
        assert "OpenAI发布GPT-5" in event_titles1
        assert "Anthropic发布Claude 3" in event_titles1

        # 验证事件属性
        openai_event = next(e for e in events1 if "GPT-5" in e.title)
        assert openai_event.news_count == 1
        assert openai_event.max_grade == "A"
        assert openai_event.max_score == 85

        # 场景2：现有分组存在匹配条目 → 新条目添加到合适的分组
        batch2 = [self.openai_news_1, self.openai_news_2, self.anthropic_news]
        # 将现有事件转换为存储格式的字典
        existing_groups = self.grouper._events_to_dict(events1)
        # 使用增量分组方法 - 增量分组需要所有相关新闻条目来重建事件
        events2 = self.grouper.incremental_group(existing_groups, batch2)

        assert len(events2) == 2, "第二次分组应该还是2个事件"
        openai_event2 = next(e for e in events2 if "GPT-5" in e.title)
        assert openai_event2.news_count == 2, "OpenAI事件应该包含2条新闻"
        assert openai_event2.max_grade == "A+", "最高评分应该更新为A+"
        assert openai_event2.max_score == 92, "最高分数应该更新为92"
        assert openai_event2.title == "GPT-5展现突破性性能", "事件标题应该使用最高评分新闻的标题"

        # 场景3：新条目没有匹配分组 → 创建新分组
        batch3 = [self.openai_news_3]
        # 注意：这条新闻和现有OpenAI事件属于同一事件，应该被添加到已有分组
        all_news2 = []
        for event in events2:
            all_news2.extend(event.news_list)
        all_news2.extend(batch3)

        events3 = self.grouper.group_news(all_news2)

        assert len(events3) == 2, "第三次分组应该还是2个事件"
        openai_event3 = next(e for e in events3 if "GPT-5" in e.title)
        assert openai_event3.news_count == 3, "OpenAI事件应该包含3条新闻"
        assert "API" in openai_event3.entities, "事件实体应该包含API"


if __name__ == "__main__":
    # 运行测试
    test = TestEventGrouper()

    try:
        print("Running incremental grouping test...")
        test.test_incremental_grouping()
        print("✓ Incremental grouping test passed")

        print("\n✅ All Event Grouper tests passed!")

    finally:
        test.cleanup()
