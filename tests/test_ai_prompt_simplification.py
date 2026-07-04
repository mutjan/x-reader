#!/usr/bin/env python3
"""Tests for the token-saving hourly AI workflow."""
import json
from datetime import datetime

import src.processors.ai_processor as ai_processor_module
from src.models.news import ProcessedNewsItem, RawNewsItem
from src.processors.ai_processor import AIScorer, ManualProcessor


def _raw_item() -> RawNewsItem:
    return RawNewsItem(
        title="OpenAI launches new agent",
        content="OpenAI announced a new coding agent with ChatGPT integration.",
        source="TestSource",
        url="https://example.com/openai-agent",
        published_at=datetime.now(),
    )


def _processed_item(content: str) -> ProcessedNewsItem:
    return ProcessedNewsItem(
        id="item1",
        original_title="OpenAI launches new agent",
        original_content=content,
        source="TestSource",
        url="https://example.com/openai-agent",
        published_at=datetime.now(),
        chinese_title="OpenAI发布新一代编程智能体",
        summary="OpenAI发布与ChatGPT集成的新编程智能体，面向开发者自动完成代码任务。",
        grade="",
        score=0,
        news_type="product",
        extension="可继续观察其对开发工具生态和企业软件采购的影响。",
        entities=["OpenAI", "GPT"],
    )


def test_base_result_preserves_entities_from_prompt_output():
    processor = ManualProcessor()
    raw_item = _raw_item()
    response = json.dumps([
        {
            "index": 0,
            "original_url": raw_item.url,
            "chinese_title": "OpenAI发布新一代编程智能体",
            "summary": "OpenAI发布与ChatGPT集成的新编程智能体，面向开发者自动完成代码任务。",
            "type": "product",
            "extension": "可继续观察其对开发工具生态和企业软件采购的影响。",
            "entities": ["OpenAI", "ChatGPT", "Altman"],
        }
    ], ensure_ascii=False)

    items = processor.parse_response(response, [raw_item])

    assert len(items) == 1
    assert items[0].entities == ["GPT", "OpenAI", "Sam Altman"]


def test_manual_processor_generates_only_base_prompt(tmp_path, monkeypatch):
    temp_dir = tmp_path / ".tmp"
    snapshot_dir = temp_dir / "snapshots"
    temp_dir.mkdir()
    snapshot_dir.mkdir()
    monkeypatch.setattr(ai_processor_module, "TEMP_DIR", str(temp_dir))
    monkeypatch.setattr(ai_processor_module, "SNAPSHOT_DIR", str(snapshot_dir))

    processor = ManualProcessor()
    result = processor.process_batch([_raw_item()])

    assert result == []
    assert list(temp_dir.glob("ai_prompt_*.txt"))
    assert not list(temp_dir.glob("entity_prompt_*.txt"))

    snapshot_files = list(snapshot_dir.glob("snapshot_*.json"))
    assert len(snapshot_files) == 1
    snapshot = json.loads(snapshot_files[0].read_text(encoding="utf-8"))
    assert snapshot["status"]["entity_recognition"] == "included_in_base"


def test_scoring_prompt_truncates_original_content_and_keeps_extension():
    long_content = "A" * 2000
    scorer = AIScorer()

    prompt = scorer.build_scoring_prompt([_processed_item(long_content)])
    payload = json.loads(prompt.split("待打分新闻：\n", 1)[1])

    assert len(payload[0]["original_content"]) <= 500
    assert payload[0]["original_content"].endswith("...")
    assert payload[0]["extension"] == "可继续观察其对开发工具生态和企业软件采购的影响。"
