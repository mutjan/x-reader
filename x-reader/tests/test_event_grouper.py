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

    def setup_method(self):
        """初始化测试"""
        self.temp_dir = tempfile.mkdtemp()
        # 使用较低的相似度阈值以便测试通过
        self.grouper = EventGrouper(similarity_threshold=0.5)

        # 创建测试新闻数据
        self.openai_news_1 = ProcessedNewsItem(
            id="news1",
            original_title="OpenAI releases GPT-5 with enhanced capabilities",
            original_content="OpenAI has released its latest large language model GPT-5 with enhanced capabilities.",
            source="TechCrunch",
            url="http://example.com/news1",
            published_at=datetime.now() - timedelta(hours=2),
            chinese_title="OpenAI发布GPT-5，性能大幅提升",
            summary="OpenAI今日正式发布GPT-5大模型，在多项基准测试中展现出超越前代的性能表现",
            grade="A",
            score=85,
            entities=["OpenAI", "GPT-5", "大模型", "AI", "大型语言模型"]
        )

        self.openai_news_2 = ProcessedNewsItem(
            id="news2",
            original_title="OpenAI GPT-5 shows breakthrough performance in benchmarks",
            original_content="Early benchmarks show GPT-5 outperforms previous models on multiple tasks.",
            source="VentureBeat",
            url="http://example.com/news2",
            published_at=datetime.now() - timedelta(hours=1),
            chinese_title="OpenAI GPT-5在基准测试中展现突破性性能",
            summary="最新发布的GPT-5在多项行业基准测试中表现出色，性能远超GPT-4等前代模型",
            grade="A+",
            score=92,
            entities=["OpenAI", "GPT-5", "大模型", "AI", "大型语言模型"]
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
            original_title="OpenAI announces GPT-5 API access for developers",
            original_content="Developers can now request access to the new GPT-5 API.",
            source="OpenAI Blog",
            url="http://example.com/news4",
            published_at=datetime.now(),
            chinese_title="OpenAI宣布GPT-5 API开放，开发者可申请访问",
            summary="OpenAI今日宣布正式开放GPT-5的API访问权限，开发者可以通过申请获得最新大模型的使用能力",
            grade="A",
            score=87,
            entities=["OpenAI", "GPT-5", "API", "大模型", "AI", "大型语言模型"]
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
        assert "OpenAI发布GPT-5，性能大幅提升" in event_titles1
        assert "Anthropic发布Claude 3" in event_titles1

        # 验证事件属性
        openai_event = next(e for e in events1 if "GPT-5" in e.title)
        assert openai_event.news_count == 1
        assert openai_event.max_grade == "A"
        assert openai_event.max_score == 85

        # 场景2：现有分组存在匹配条目 → 新条目添加到合适的分组
        # 增量分组需要所有相关新闻条目（包括原有新闻和新增新闻）来正确重建事件
        batch2 = [self.openai_news_1, self.openai_news_2, self.anthropic_news]
        # 将现有事件转换为存储格式的字典
        existing_groups = self.grouper._events_to_dict(events1)
        # 使用增量分组方法
        events2 = self.grouper.incremental_group(existing_groups, batch2)

        assert len(events2) == 2, "第二次分组应该还是2个事件"
        openai_event2 = next(e for e in events2 if "GPT-5" in e.title)
        assert openai_event2.news_count == 2, "OpenAI事件应该包含2条新闻"
        assert openai_event2.max_grade == "A+", "最高评分应该更新为A+"
        assert openai_event2.max_score == 92, "最高分数应该更新为92"
        assert openai_event2.title == "OpenAI GPT-5在基准测试中展现突破性性能", "事件标题应该使用最高评分新闻的标题"

        # 场景3：新条目没有匹配现有分组 → 创建新分组，原有分组保留
        batch3 = [self.openai_news_3]
        # 准备所有新闻（包括原有和新增）
        all_news2 = []
        for event in events2:
            all_news2.extend(event.news_list)
        all_news2.extend(batch3)

        # 将现有事件转换为存储格式的字典
        existing_groups2 = self.grouper._events_to_dict(events2)
        # 使用增量分组方法，传入所有有效新闻
        events3 = self.grouper.incremental_group(existing_groups2, batch3, all_news2)

        # API新闻与现有OpenAI事件相似度低于阈值，会创建新分组
        assert len(events3) == 3, "第三次分组应该有3个事件"
        # 验证原有事件都保留了
        event_titles3 = [event.title for event in events3]
        assert "OpenAI GPT-5在基准测试中展现突破性性能" in event_titles3
        assert "Anthropic发布Claude 3" in event_titles3
        assert "OpenAI宣布GPT-5 API开放，开发者可申请访问" in event_titles3

        # 场景4：验证没有新匹配新闻的原有事件不会丢失
        # 新增一条完全不相关的新闻
        google_news = ProcessedNewsItem(
            id="news5",
            original_title="Google releases Gemini 2",
            original_content="Google has announced its new Gemini 2 model.",
            source="Google Blog",
            url="http://example.com/news5",
            published_at=datetime.now(),
            chinese_title="谷歌发布Gemini 2大模型",
            summary="谷歌今日发布新一代大模型Gemini 2，性能显著提升",
            grade="A",
            score=86,
            entities=["Google", "Gemini 2", "大模型", "AI"]
        )
        batch4 = [google_news]
        # 所有新闻包括原有3条OpenAI相关、1条Anthropic、1条新的Google新闻
        all_news3 = all_news2 + [google_news]

        # 转换现有分组为存储格式
        existing_groups3 = self.grouper._events_to_dict(events3)
        # 增量分组，只传入新的Google新闻
        events4 = self.grouper.incremental_group(existing_groups3, batch4, all_news3)

        # 应该有4个事件：原有3个 + 新的1个
        assert len(events4) == 4, "第四次分组应该有4个事件"
        # 验证原有事件都保留了
        event_titles4 = [event.title for event in events4]
        assert "OpenAI GPT-5在基准测试中展现突破性性能" in event_titles4
        assert "Anthropic发布Claude 3" in event_titles4
        assert "OpenAI宣布GPT-5 API开放，开发者可申请访问" in event_titles4
        assert "谷歌发布Gemini 2大模型" in event_titles4
        # 验证原有事件的新闻数量没有变化
        openai_event4 = next(e for e in events4 if "GPT-5在基准测试" in e.title)
        assert openai_event4.news_count == 2, "OpenAI基准测试事件应该仍然包含2条新闻"
        openai_api_event4 = next(e for e in events4 if "API开放" in e.title)
        assert openai_api_event4.news_count == 1, "OpenAI API事件应该仍然包含1条新闻"
        anthropic_event4 = next(e for e in events4 if "Claude 3" in e.title)
        assert anthropic_event4.news_count == 1, "Anthropic事件应该仍然包含1条新闻"


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
