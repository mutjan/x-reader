#!/usr/bin/env python3
"""
重新转换新闻数据格式，修复字段问题
"""
import json
import os
from datetime import datetime
from src.models.news import ProcessedNewsItem
from src.utils.common import load_json, save_json

DATA_FILE = "news_data_latest.json"

def main():
    # 加载现有数据
    data = load_json(DATA_FILE, {})

    if "news" in data:
        print("检测到最新格式数据，包含news顶级键")
        # 提取所有新闻项
        all_items = []
        for date in data["news"]:
            for item in data["news"][date]:
                all_items.append(item)
    else:
        print("检测到中间格式数据，直接按日期分组")
        all_items = []
        for date in data:
            for item in data[date]:
                all_items.append(item)

    print(f"加载到 {len(all_items)} 条新闻")

    # 转换为ProcessedNewsItem对象，重新生成前端格式
    processed_items = []
    for item_dict in all_items:
        try:
            # 从字典加载
            item = ProcessedNewsItem.from_dict(item_dict)
            # 确保字段正确
            if not item.chinese_title:
                print(f"警告: 新闻 {item.id} 没有中文标题")
            if not item.news_type:
                print(f"警告: 新闻 {item.id} 没有类型")
            if not item.extension:
                print(f"警告: 新闻 {item.id} 没有扩展内容")

            processed_items.append(item)
        except Exception as e:
            print(f"跳过无效新闻条目: {e}")

    # 重新生成按日期分组的前端格式
    news_by_date = {}
    for item in processed_items:
        front_item = item.to_frontend_dict()
        date_key = item.processed_at.strftime('%Y-%m-%d')

        if date_key not in news_by_date:
            news_by_date[date_key] = []
        news_by_date[date_key].append(front_item)

    # 排序
    for date in news_by_date:
        news_by_date[date].sort(key=lambda x: x["timestamp"], reverse=True)

    # 保存新数据
    output_data = {
        "news": news_by_date,
        "last_updated": datetime.now().isoformat(),
        "total_news": len(processed_items)
    }

    save_success = save_json(output_data, DATA_FILE)
    if save_success:
        print(f"✓ 成功保存转换后的数据，共 {len(processed_items)} 条新闻")
        # 显示第一条新闻的详细信息
        if processed_items:
            first = processed_items[0]
            print("\n第一条新闻信息:")
            print(f"  ID: {first.id}")
            print(f"  中文标题: {first.chinese_title}")
            print(f"  类型: {first.news_type} -> {front_item['typeName']}")
            print(f"  扩展内容: {first.extension[:50]}...")
    else:
        print("✗ 保存失败")

if __name__ == "__main__":
    main()