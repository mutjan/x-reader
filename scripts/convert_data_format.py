#!/usr/bin/env python3
"""
转换现有的news_data.json为前端需要的格式
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.models.news import ProcessedNewsItem
from src.utils.common import load_json, save_json
from src.publishers.github_pages import GitHubPagesPublisher

def main():
    data_file = "/Users/lzw/Documents/LobsterAI/lzw/x-reader/news_data.json"
    backup_file = "/Users/lzw/Documents/LobsterAI/lzw/x-reader/news_data.json.backup"

    # 加载现有数据
    print(f"加载现有数据: {data_file}")
    data = load_json(data_file, {})

    if not data:
        print("数据文件为空或不存在")
        return 1

    # 备份原文件
    print(f"备份原文件到: {backup_file}")
    save_json(data, backup_file)

    # 转换所有数据
    print("开始转换数据格式...")
    converted_data = {}
    total_items = 0

    for date in data:
        converted_data[date] = []
        for item_dict in data[date]:
            try:
                # 从旧格式字典加载ProcessedNewsItem
                news_item = ProcessedNewsItem.from_dict(item_dict)
                # 转换为前端格式
                front_item = news_item.to_frontend_dict()
                converted_data[date].append(front_item)
                total_items += 1
            except Exception as e:
                print(f"转换失败，跳过条目: {e}")
                continue

    print(f"转换完成: 共转换 {total_items} 条新闻，覆盖 {len(converted_data)} 个日期")

    # 保存转换后的数据
    print(f"保存转换后的数据到: {data_file}")
    save_json(converted_data, data_file)

    # 推送到GitHub
    print("推送更新到GitHub...")
    publisher = GitHubPagesPublisher()
    if publisher._push_to_github("转换数据格式为前端期望的字段结构"):
        print("✅ 推送成功！")
        return 0
    else:
        print("❌ 推送失败")
        return 1

if __name__ == "__main__":
    sys.exit(main())