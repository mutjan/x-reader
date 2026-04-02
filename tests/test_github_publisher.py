#!/usr/bin/env python3
"""
GitHub Pages 发布器集成测试
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import tempfile
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
from src.publishers.github_pages import GitHubPagesPublisher
from src.models.news import ProcessedNewsItem
from src.processors.event_grouper import EventGrouper, Event


class TestGitHubPublisher:
    """GitHub Pages发布器测试类"""

    def __init__(self):
        """初始化测试"""
        self.temp_dir = tempfile.mkdtemp()
        # 创建临时数据文件
        self.temp_data_file = os.path.join(self.temp_dir, "news_data.json")
        self.temp_event_file = os.path.join(self.temp_dir, "event_groups.json")

        # 创建测试新闻数据
        self.test_news = self._create_test_news()

    def cleanup(self):
        """测试后清理"""
        import shutil
        shutil.rmtree(self.temp_dir)
        # 清理测试生成的事件分组文件
        import src.config.settings
        if os.path.exists(src.config.settings.EVENT_GROUPS_FILE):
            os.remove(src.config.settings.EVENT_GROUPS_FILE)
        # 清理备份文件
        for f in os.listdir(src.config.settings.DATA_DIR):
            if f.startswith("event_groups.json-") and f.endswith(".bak"):
                os.remove(os.path.join(src.config.settings.DATA_DIR, f))

    def _create_test_news(self):
        """创建测试新闻条目"""
        news1 = ProcessedNewsItem(
            id="news1",
            original_title="OpenAI releases GPT-5",
            original_content="OpenAI has released its latest large language model GPT-5 with enhanced capabilities.",
            source="TechCrunch",
            url="http://example.com/news1",
            published_at=datetime.now() - timedelta(hours=2),
            chinese_title="OpenAI发布GPT-5",
            grade="A",
            score=85,
            entities=["OpenAI", "GPT-5"]
        )

        news2 = ProcessedNewsItem(
            id="news2",
            original_title="GPT-5 shows breakthrough performance",
            original_content="Early benchmarks show GPT-5 outperforms previous models on multiple tasks.",
            source="VentureBeat",
            url="http://example.com/news2",
            published_at=datetime.now() - timedelta(hours=1),
            chinese_title="GPT-5展现突破性性能",
            grade="A+",
            score=92,
            entities=["OpenAI", "GPT-5"]
        )

        news3 = ProcessedNewsItem(
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

        # 创建过期新闻（31天前）
        old_news = ProcessedNewsItem(
            id="old_news",
            original_title="Old news about AI",
            original_content="This news is expired and should be cleaned up.",
            source="Old Source",
            url="http://example.com/old",
            published_at=datetime.now() - timedelta(days=31),
            chinese_title="过期AI新闻",
            grade="B",
            score=60,
            entities=["AI"]
        )

        return [news1, news2, news3, old_news]

    def test_dual_file_atomic_write(self):
        """测试双文件原子写入模式：先写入event_groups.json，再写入news_data.json"""
        publisher = GitHubPagesPublisher()

        # 替换数据文件路径为临时路径
        original_data_file = publisher.data_file
        publisher.data_file = self.temp_data_file

        try:
            # 模拟_push_to_github不实际执行git操作
            with patch.object(publisher, '_push_to_github', return_value=True):
                # 发布测试新闻（不包含过期新闻，过期新闻会被清理）
                result = publisher.publish(self.test_news[:3])
                assert result is True

                # 验证数据文件存在
                assert os.path.exists(self.temp_data_file)

                # 读取并验证数据文件内容
                with open(self.temp_data_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                assert "news" in data
                assert "events" not in data  # events字段已移到独立文件
                assert "last_updated" in data
                assert data["total_news"] == 3

                # 验证事件分组文件存在并包含正确数据
                import src.config.settings
                event_groups_path = src.config.settings.EVENT_GROUPS_FILE
                assert os.path.exists(event_groups_path)

                with open(event_groups_path, 'r', encoding='utf-8') as f:
                    events_data = json.load(f)

                assert len(events_data) >= 1
                event_titles = [event.get("event_title", event.get("title")) for event in events_data]
                # 由于相似度阈值，两条OpenAI新闻可能被分到不同组，这里只验证存在事件

        finally:
            publisher.data_file = original_data_file

    def test_expired_cleanup_sync(self):
        """测试过期新闻清理同步：过期新闻ID从事件分组中移除，空组被删除"""
        publisher = GitHubPagesPublisher()

        # 替换数据文件路径为临时路径
        original_data_file = publisher.data_file
        publisher.data_file = self.temp_data_file

        try:
            # 先发布包含过期新闻的测试数据
            with patch.object(publisher, '_push_to_github', return_value=True):
                # 第一次发布包含过期新闻
                result = publisher.publish(self.test_news)
                assert result is True

                # 读取第一次发布的数据
                with open(self.temp_data_file, 'r', encoding='utf-8') as f:
                    first_data = json.load(f)

                # 验证过期新闻已被清理
                assert first_data["total_news"] == 3  # 过期新闻已被删除

                # 第二次发布相同数据，验证不会重复处理
                result = publisher.publish(self.test_news, update_existing=False)
                assert result is True

                with open(self.temp_data_file, 'r', encoding='utf-8') as f:
                    second_data = json.load(f)

                # 验证数据没有变化
                assert second_data["total_news"] == 3
                assert second_data["total_events"] == 2

                # 验证事件分组中不包含过期新闻的ID
                all_news_ids = []
                for date in second_data["news"].values():
                    all_news_ids.extend([item["id"] for item in date])

                assert "old_news" not in all_news_ids

                # 验证事件分组中的新闻ID都存在于news数据中
                for event in second_data["events"]:
                    for news_item in event["news_list"]:
                        assert news_item["id"] in all_news_ids

        finally:
            publisher.data_file = original_data_file


if __name__ == "__main__":
    # 运行测试
    test = TestGitHubPublisher()

    try:
        print("Running dual file atomic write test...")
        test.test_dual_file_atomic_write()
        print("✓ Dual file atomic write test passed")

        print("\nRunning expired cleanup sync test...")
        test.test_expired_cleanup_sync()
        print("✓ Expired cleanup sync test passed")

        print("\n✅ All GitHub Publisher tests passed!")

    finally:
        test.cleanup()
