#!/usr/bin/env python3
"""
完整流水线集成测试
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tempfile
import json
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
from src.fetchers.base import BaseFetcher
from src.models.news import RawNewsItem, ProcessedNewsItem
from src.processors.duplicate import DuplicateRemover
from src.processors.filter import NewsFilter
from src.processors.ai_processor import BaseAIProcessor
from src.publishers.github_pages import GitHubPagesPublisher


class MockFetcher(BaseFetcher):
    """模拟数据源"""
    def __init__(self, test_items):
        super().__init__("mock_source")
        self.test_items = test_items

    def fetch(self, time_window_hours: int = 2) -> list[RawNewsItem]:
        return self.test_items

    def test_connection(self) -> bool:
        return True


class MockAIProcessor(BaseAIProcessor):
    """模拟AI处理器"""
    def process_batch(self, items: list[RawNewsItem]) -> list[ProcessedNewsItem]:
        processed = []
        for i, item in enumerate(items):
            # 简单模拟AI处理结果
            grade = "A" if i % 2 == 0 else "B"
            score = 80 + i * 5
            processed.append(ProcessedNewsItem(
                id=item.get_unique_id(),
                original_title=item.title,
                original_content=item.content,
                source=item.source,
                url=item.url,
                published_at=item.published_at,
                chinese_title=f"[翻译] {item.title}",
                grade=grade,
                score=score,
                entities=["测试", "科技"]
            ))
        return processed


class TestPipelineIntegration:
    """完整流水线集成测试类"""

    def __init__(self):
        """初始化测试"""
        self.temp_dir = tempfile.mkdtemp()
        self.temp_data_file = os.path.join(self.temp_dir, "news_data.json")

        # 创建测试原始新闻数据
        self.raw_items = self._create_test_raw_items()

    def cleanup(self):
        """测试后清理"""
        import shutil
        shutil.rmtree(self.temp_dir)

    def _create_test_raw_items(self):
        """创建测试原始新闻条目"""
        now = datetime.now()
        items = []

        # 创建内容差异较大的测试新闻，避免被去重
        test_data = [
            ("OpenAI发布新一代GPT模型", "OpenAI今日宣布推出GPT-5大模型，性能提升显著", "http://techcrunch.com/openai-gpt5"),
            ("Anthropic发布Claude 3多模态模型", "Anthropic最新推出的Claude 3在多个基准测试中超过GPT-4", "http://venturebeat.com/anthropic-claude3"),
            ("谷歌发布Gemini 2.0", "谷歌DeepMind宣布Gemini 2.0正式上线，支持更长上下文", "http://blog.google/gemini-2"),
            ("英伟达推出新一代AI芯片H200", "英伟达发布H200 GPU，AI推理性能提升一倍", "http://nvidia.com/h200-announcement"),
            ("Meta开源Llama 3大模型", "Meta宣布开源Llama 3，参数规模达700亿", "http://ai.meta.com/llama3")
        ]

        for i, (title, content, url) in enumerate(test_data):
            item = RawNewsItem(
                title=title,
                content=content,
                source=f"来源{i+1}",
                url=url,
                published_at=now - timedelta(hours=i)
            )
            items.append(item)

        return items

    def test_pipeline_with_event_grouper(self):
        """测试完整流水线集成，包含事件分组"""
        # 初始化组件
        fetcher = MockFetcher(self.raw_items)
        duplicate_remover = DuplicateRemover()
        news_filter = NewsFilter()
        ai_processor = MockAIProcessor()
        publisher = GitHubPagesPublisher()

        # 替换数据文件路径为临时路径
        original_data_file = publisher.data_file
        publisher.data_file = self.temp_data_file

        try:
            # 模拟发布流程不实际执行git操作
            with patch.object(publisher, '_push_to_github', return_value=True):
                # 1. 获取新闻
                raw_items = fetcher.fetch(time_window_hours=24)
                assert len(raw_items) == 5, "应该获取到5条原始新闻"

                # 2. 去重
                unique_items = duplicate_remover.deduplicate_raw(raw_items)
                assert len(unique_items) == 5, "去重后应该还有5条新闻"

                # 3. 预筛选
                filtered_items = news_filter.filter_news(unique_items, min_score=0)
                assert len(filtered_items) == 5, "预筛选后应该还有5条新闻"

                # 4. AI处理
                processed_items = ai_processor.process_batch(filtered_items)
                assert len(processed_items) == 5, "AI处理后应该还有5条新闻"
                assert all(hasattr(item, 'grade') for item in processed_items)
                assert all(hasattr(item, 'score') for item in processed_items)

                # 5. 发布
                result = publisher.publish(processed_items)
                assert result is True, "发布应该成功"

                # 验证输出文件
                assert os.path.exists(self.temp_data_file), "数据文件应该存在"

                # 读取并验证数据
                with open(self.temp_data_file, 'r', encoding='utf-8') as f:
                    output_data = json.load(f)

                assert "news" in output_data, "输出应该包含news字段"
                assert "events" in output_data, "输出应该包含events字段"
                assert "last_updated" in output_data, "输出应该包含last_updated字段"
                assert output_data["total_news"] == 5, "应该有5条新闻"

                # 验证事件分组存在
                assert isinstance(output_data["events"], list), "events应该是列表"
                assert output_data["total_events"] >= 1, "至少应该有1个事件"

                # 验证事件中的新闻ID都存在于news数据中
                all_news_ids = set()
                for date in output_data["news"].values():
                    for item in date:
                        all_news_ids.add(item["id"])

                for event in output_data["events"]:
                    assert "news_list" in event, "事件应该包含news_list"
                    for news_item in event["news_list"]:
                        assert news_item["id"] in all_news_ids, f"事件中的新闻ID {news_item['id']} 应该存在于news数据中"

                print(f"  ✓ 流水线执行完成，生成{output_data['total_news']}条新闻，{output_data['total_events']}个事件")

        finally:
            publisher.data_file = original_data_file


if __name__ == "__main__":
    # 运行测试
    test = TestPipelineIntegration()

    try:
        print("Running end-to-end pipeline integration test...")
        test.test_pipeline_with_event_grouper()
        print("✓ Pipeline integration test passed")

        print("\n✅ All Pipeline Integration tests passed!")

    finally:
        test.cleanup()
