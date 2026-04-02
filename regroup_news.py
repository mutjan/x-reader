#!/usr/bin/env python3
"""
重新分组所有4月2日的新闻
"""
import sys
import os
from datetime import datetime

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.processors.event_grouper import EventGrouper
from src.utils.common import load_json, save_json
from src.models.news import ProcessedNewsItem
from src.config.settings import DATA_FILE, EVENT_GROUPS_FILE, EVENT_GROUPER_CONFIG_FILE
import json

def main():
    print("🔄 开始重新分组4月2日所有新闻...")

    # 1. 加载所有新闻数据
    news_data = load_json(DATA_FILE, {})
    print(f"📥 加载了新闻数据文件")

    # 2. 获取所有日期的所有新闻
    all_news = []
    if "news" in news_data:
        for date_str, news_list in news_data["news"].items():
            print(f"📅 {date_str} 共有 {len(news_list)} 条新闻")
            for item in news_list:
                try:
                    # 转换为ProcessedNewsItem对象
                    # 处理字段映射（前端格式 → 内部格式）
                    item["chinese_title"] = item["title"]
                    item["grade"] = item["rating"]
                    item["original_content"] = item.get("summary", "")
                    item["source_url"] = item.get("url", "")
                    item["published_at"] = item.get("published_at", "")
                    item["entities"] = item.get("entities", [])  # 修复：复制entities字段
                    news_item = ProcessedNewsItem.from_dict(item)
                    all_news.append(news_item)
                except Exception as e:
                    print(f"⚠️  跳过无效新闻: {e}")
                    continue

    print(f"✅ 总共加载 {len(all_news)} 条新闻")

    if not all_news:
        print("❌ 没有找到任何新闻数据")
        return

    # 3. 读取配置并重新分组
    config = load_json(EVENT_GROUPER_CONFIG_FILE, {})
    entity_threshold = config.get('entity_threshold', 3)
    similarity_threshold = config.get('similarity_threshold', 0.85)
    print(f"⚙️ 使用配置: entity_threshold={entity_threshold}, similarity_threshold={similarity_threshold}")

    grouper = EventGrouper(
        entity_threshold=entity_threshold,
        similarity_threshold=similarity_threshold
    )
    events = grouper.group_news(all_news)

    print(f"✅ 分组完成: {len(all_news)} 条新闻 → {len(events)} 个事件")

    # 4. 保存新的事件分组
    success = grouper.save_event_groups(events, EVENT_GROUPS_FILE)

    if success:
        print(f"💾 事件分组已保存到 {EVENT_GROUPS_FILE}")
        # 显示分组结果摘要
        print("\n📊 分组结果摘要:")
        for i, event in enumerate(events[:10]):  # 只显示前10个
            print(f"  {i+1}. {event.title} (评分: {event.max_score}{event.max_grade}, {event.news_count}条新闻)")
        if len(events) > 10:
            print(f"  ... 还有 {len(events) - 10} 个事件")
    else:
        print("❌ 保存事件分组失败")

if __name__ == "__main__":
    main()