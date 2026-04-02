#!/usr/bin/env python3
"""调试新闻查找字典"""
import json
import os

from src.config.settings import DATA_FILE, EVENT_GROUPS_FILE
import os
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE_PATH = os.path.join(ROOT_DIR, DATA_FILE)
EVENT_GROUPS_FILE_PATH = os.path.join(ROOT_DIR, EVENT_GROUPS_FILE)
from src.utils.common import load_json

# 加载数据
event_groups = load_json(EVENT_GROUPS_FILE_PATH, [])
news_data = load_json(DATA_FILE_PATH, {}).get('news', {})

print("事件分组:")
for group in event_groups:
    print(f"  - {group['group_id']}: {group['event_title']}")
    print(f"    news_ids: {group['news_ids']}")

print("\n新闻数据:")
news_lookup = {}
for date, items in news_data.items():
    print(f"  日期: {date}")
    for news in items:
        print(f"    - {news['id']}: {news['title']}")
        news_lookup[news['id']] = news

print("\n查找字典中的ID:")
print(f"  所有ID: {list(news_lookup.keys())}")

print("\n检查每个事件的新闻是否存在:")
for group in event_groups:
    print(f"  事件: {group['group_id']}")
    for news_id in group['news_ids']:
        exists = news_id in news_lookup
        print(f"    - {news_id}: {'存在' if exists else '不存在'}")
