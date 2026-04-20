#!/usr/bin/env python3
"""
事件分组复查处理器测试
测试 EventGroupReviewer 的初始化、提示词生成、修正应用、审计日志等功能
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tempfile
import shutil
import json
from datetime import datetime, timedelta
from src.models.news import ProcessedNewsItem
from src.processors.event_grouper import Event, EventGrouper
from src.processors.event_reviewer import EventGroupReviewer


# ========== DATA_DIR 切换辅助 ==========

_orig_data_dir = None
_orig_groups_file = None
_orig_temp_dir = None


def _use_temp_data_dir(tmp_dir: str):
    """临时切换DATA_DIR到测试目录"""
    global _orig_data_dir, _orig_groups_file, _orig_temp_dir
    import src.config.settings as settings_mod
    _orig_data_dir = settings_mod.DATA_DIR
    _orig_groups_file = settings_mod.EVENT_GROUPS_FILE
    _orig_temp_dir = settings_mod.TEMP_DIR
    settings_mod.DATA_DIR = tmp_dir
    settings_mod.EVENT_GROUPS_FILE = os.path.join(tmp_dir, "event_groups.json")
    settings_mod.TEMP_DIR = os.path.join(tmp_dir, ".tmp")
    os.makedirs(settings_mod.TEMP_DIR, exist_ok=True)


def _restore_data_dir():
    """恢复原始DATA_DIR"""
    global _orig_data_dir, _orig_groups_file, _orig_temp_dir
    if _orig_data_dir is not None:
        import src.config.settings as settings_mod
        settings_mod.DATA_DIR = _orig_data_dir
        settings_mod.EVENT_GROUPS_FILE = _orig_groups_file
        settings_mod.TEMP_DIR = _orig_temp_dir


# ========== 测试辅助 ==========

def _make_test_news(item_id: str, title: str, entities: list = None) -> ProcessedNewsItem:
    """创建测试用 ProcessedNewsItem"""
    return ProcessedNewsItem(
        id=item_id,
        original_title=title,
        original_content=f"Content for {title}",
        source="TestSource",
        url=f"https://example.com/{item_id}",
        published_at=datetime.now(),
        processed_at=datetime.now(),
        grade="A",
        score=80,
        entities=entities or ["TestEntity"],
        chinese_title=title,
        summary=f"Summary for {title[:50]}",
        news_type="product",
        extension="",
    )


def _make_test_event(event_id: str, news_list: list) -> Event:
    """创建测试用 Event"""
    grouper = EventGrouper()
    event = Event(
        event_id=event_id,
        title=news_list[0].chinese_title if news_list else "Empty Event",
        main_news=news_list[0] if news_list else None,
        news_list=news_list,
        entities=[],
        max_grade="B",
        max_score=0,
        start_time=datetime.now(),
        end_time=datetime.now(),
        news_count=len(news_list),
    )
    if news_list:
        grouper._update_event_properties(event)
    return event


# ========== 测试类 ==========

class TestEventGroupReviewer:
    """事件分组复查器测试类"""

    def setup_method(self):
        """初始化测试"""
        self.temp_dir = tempfile.mkdtemp()
        _use_temp_data_dir(self.temp_dir)
        self.reviewer = EventGroupReviewer()

    def teardown_method(self):
        """清理测试"""
        _restore_data_dir()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # ===== 测试 1: 初始化 =====

    def test_reviewer_initialization(self):
        """测试 EventGroupReviewer 初始化参数"""
        reviewer = EventGroupReviewer()
        assert reviewer.entity_threshold == 3
        assert reviewer.review_similarity_threshold == 0.55
        assert reviewer.max_candidates_per_news == 5

        # 自定义参数
        reviewer2 = EventGroupReviewer(entity_threshold=5, review_similarity_threshold=0.7)
        assert reviewer2.entity_threshold == 5
        assert reviewer2.review_similarity_threshold == 0.7

    # ===== 测试 2: 提示词文件生成 =====

    def test_prompt_file_created(self):
        """测试 generate_review_prompt 生成提示词文件"""
        news1 = _make_test_news("n1", "OpenAI发布GPT-5", ["OpenAI", "GPT", "大模型", "AI", "人工智能"])
        event1 = _make_test_event("evt1", [news1])

        new_items = [_make_test_news("n2", "GPT-5性能测试结果出炉", ["OpenAI", "GPT", "大模型", "AI", "人工智能"])]

        result = self.reviewer.generate_review_prompt(new_items, [event1], new_items)

        assert result != "", "generate_review_prompt 应返回文件路径"
        assert os.path.exists(result), f"提示词文件应存在: {result}"

        with open(result, 'r', encoding='utf-8') as f:
            content = f.read()

        assert len(content) > 100, "提示词内容应大于100字符"
        assert "复查任务" in content or "事件分组复查" in content, "应包含复查相关标题"

    # ===== 测试 3: 移动新闻到另一个事件 =====

    def test_apply_corrections_move_news(self):
        """测试将新闻从一个事件移动到另一个事件"""
        news1 = _make_test_news("n1", "新闻1", ["OpenAI", "GPT", "大模型", "AI", "人工智能"])
        news2 = _make_test_news("n2", "新闻2", ["OpenAI", "GPT", "大模型", "AI", "人工智能"])
        news3 = _make_test_news("n3", "新闻3", ["OpenAI", "GPT", "大模型", "AI", "人工智能"])

        event1 = _make_test_event("evt1", [news1, news3])
        event2 = _make_test_event("evt2", [news2])
        events = [event1, event2]

        corrections = [
            {
                "news_id": "n2",
                "current_event_id": "evt2",
                "suggested_event_id": "evt1",
                "reason": "n2与evt1的新闻更相关"
            }
        ]

        success, audit_entry = self.reviewer.apply_corrections(corrections, events, batch_id="test-batch")

        assert success, "修正应成功"
        assert audit_entry["corrections_applied"] == 1

        # 验证 news2 已移到 event1
        evt1_news_ids = [n.id for n in event1.news_list]
        evt2_news_ids = [n.id for n in event2.news_list]
        assert "n2" in evt1_news_ids, "n2 应在 evt1 中"
        assert "n2" not in evt2_news_ids, "n2 不应在 evt2 中"

    # ===== 测试 4: 创建新事件 =====

    def test_apply_corrections_create_new_event(self):
        """测试 suggested_event_id=new_event 时创建新事件"""
        news1 = _make_test_news("n1", "新闻1", ["TestEntity", "Entity2", "Entity3"])
        news2 = _make_test_news("n2", "新闻2-需要新事件", ["TestEntity", "Entity2", "Entity3"])

        event1 = _make_test_event("evt1", [news1, news2])
        events = [event1]

        corrections = [
            {
                "news_id": "n2",
                "current_event_id": "evt1",
                "suggested_event_id": "new_event",
                "new_event_title": "新事件X",
                "reason": "n2不属于evt1的范围"
            }
        ]

        initial_count = len(events)
        success, audit_entry = self.reviewer.apply_corrections(corrections, events, batch_id="test-new")

        assert success, "修正应成功"
        assert audit_entry["corrections_applied"] == 1
        assert len(events) == initial_count + 1, "应新增一个事件"

        new_event = events[-1]
        assert new_event.title == "新事件X"
        new_event_news_ids = [n.id for n in new_event.news_list]
        assert "n2" in new_event_news_ids, "n2 应在新事件中"

    # ===== 测试 5: 审计日志写入 =====

    def test_audit_log_written(self):
        """测试审计日志正确写入文件"""
        news1 = _make_test_news("n1", "新闻1", ["TestEntity"])
        event1 = _make_test_event("evt1", [news1])
        events = [event1]

        corrections = [
            {
                "news_id": "n1",
                "current_event_id": "evt1",
                "suggested_event_id": "new_event",
                "reason": "测试审计日志"
            }
        ]

        success, audit_entry = self.reviewer.apply_corrections(corrections, events, batch_id="audit-test")

        assert success
        log_path = os.path.join(self.temp_dir, "event_review_log.json")
        assert os.path.exists(log_path), "审计日志文件应存在"

        log_data = json.load(open(log_path, 'r', encoding='utf-8'))
        assert "entries" in log_data
        assert len(log_data["entries"]) > 0

        last_entry = log_data["entries"][-1]
        assert last_entry["batch_id"] == "audit-test"
        assert last_entry["corrections_applied"] == 1

    # ===== 测试 6: 空修正列表 =====

    def test_empty_corrections(self):
        """测试空修正列表不修改事件"""
        news1 = _make_test_news("n1", "新闻1", ["TestEntity"])
        event1 = _make_test_event("evt1", [news1])
        events = [event1]
        original_news_count = len(event1.news_list)

        success, audit_entry = self.reviewer.apply_corrections([], events, batch_id="empty-test")

        assert success
        assert audit_entry["corrections_applied"] == 0
        assert len(event1.news_list) == original_news_count, "事件不应被修改"

    # ===== 测试 7: 无效事件ID被跳过 =====

    def test_invalid_event_ids_skipped(self):
        """测试无效的目标事件ID被跳过"""
        news1 = _make_test_news("n1", "新闻1", ["TestEntity"])
        event1 = _make_test_event("evt1", [news1])
        events = [event1]

        corrections = [
            {
                "news_id": "n1",
                "current_event_id": "evt1",
                "suggested_event_id": "nonexistent_event",
                "reason": "目标不存在"
            }
        ]

        success, audit_entry = self.reviewer.apply_corrections(corrections, events, batch_id="invalid-test")

        assert success
        assert audit_entry["corrections_applied"] == 0, "无效修正应被跳过"
        assert "无有效修正" in audit_entry.get("note", "")

    # ===== 测试 8: 候选选择 =====

    def test_candidate_selection(self):
        """测试高相似度候选事件出现在提示词中"""
        # 创建共享大量实体的新闻
        shared_entities = ["OpenAI", "GPT", "大模型", "AI", "人工智能"]
        news1 = _make_test_news("n1", "OpenAI发布GPT-5大模型", shared_entities)
        news2 = _make_test_news("n2", "OpenAI GPT-5性能测试结果", shared_entities)

        event1 = _make_test_event("evt1", [news1])

        # 新新闻与event1高度相似
        new_items = [news2]

        # 使用较低阈值确保候选能匹配
        reviewer = EventGroupReviewer(review_similarity_threshold=0.3)
        result = reviewer.generate_review_prompt(new_items, [event1], new_items)

        assert result != "", "提示词文件应成功生成"

        with open(result, 'r', encoding='utf-8') as f:
            content = f.read()

        # 验证候选信息出现在提示词中
        assert "evt1" in content, "候选事件ID应出现在提示词中"
        # 候选列表区域应包含高相似度事件信息
        assert "high_similarity_events" in content or "similarity" in content, "应包含相似度信息"


if __name__ == "__main__":
    test = TestEventGroupReviewer()

    methods = [
        ("reviewer_initialization", test.test_reviewer_initialization),
        ("prompt_file_created", test.test_prompt_file_created),
        ("apply_corrections_move_news", test.test_apply_corrections_move_news),
        ("apply_corrections_create_new_event", test.test_apply_corrections_create_new_event),
        ("audit_log_written", test.test_audit_log_written),
        ("empty_corrections", test.test_empty_corrections),
        ("invalid_event_ids_skipped", test.test_invalid_event_ids_skipped),
        ("candidate_selection", test.test_candidate_selection),
    ]

    passed = 0
    failed = 0
    for name, method in methods:
        try:
            test.setup_method()
            method()
            print(f"  PASS: {name}")
            passed += 1
        except Exception as e:
            print(f"  FAIL: {name} -- {e}")
            failed += 1
        finally:
            test.teardown_method()

    print(f"\n{passed} passed, {failed} failed, {len(methods)} total")

    if failed > 0:
        sys.exit(1)
    else:
        print("\nAll EventGroupReviewer tests passed!")
