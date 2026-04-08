#!/usr/bin/env python3
"""
清理过期新闻数据
删除超过7天的新闻，并清理关联的空事件
"""
import json
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
NEWS_FILE = BASE_DIR / "data" / "news_data.json"
EVENT_FILE = BASE_DIR / "data" / "event_groups.json"

def main():
    today = datetime.now().date()
    cutoff = today - timedelta(days=6)  # 保留最近7天含今天
    print(f"今天: {today}, 截止日期: {cutoff} (保留此日期及之后)")

    # 1. 加载 news_data.json
    with open(NEWS_FILE, "r") as f:
        data = json.load(f)

    news = data.get("news", {})
    dates_to_delete = []
    deleted_ids = set()

    for date_str in news:
        try:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            continue
        if date_obj < cutoff:
            dates_to_delete.append(date_str)
            for item in news[date_str]:
                deleted_ids.add(item["id"])

    if not dates_to_delete:
        print("没有需要删除的过期新闻")
        return

    print(f"\n要删除的日期: {dates_to_delete}")
    print(f"涉及新闻数量: {len(deleted_ids)}")
    for date_str in dates_to_delete:
        print(f"  {date_str}: {len(news[date_str])} 条新闻")
        for item in news[date_str]:
            print(f"    - [{item.get('grade', '?')}] {item['chinese_title']}")

    # 删除过期日期
    for date_str in dates_to_delete:
        del news[date_str]

    with open(NEWS_FILE, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n已从 news_data.json 删除 {len(dates_to_delete)} 个日期的数据")

    # 2. 处理 event_groups.json
    if not EVENT_FILE.exists():
        print("event_groups.json 不存在，跳过")
        return

    with open(EVENT_FILE, "r") as f:
        events = json.load(f)

    events_to_keep = []
    events_deleted = 0

    for event in events:
        original_count = len(event["news_ids"])
        event["news_ids"] = [nid for nid in event["news_ids"] if nid not in deleted_ids]

        if not event["news_ids"]:
            print(f"  删除事件 (无关联新闻): {event['event_title']}")
            events_deleted += 1
        else:
            removed = original_count - len(event["news_ids"])
            if removed > 0:
                print(f"  事件移除 {removed} 条新闻: {event['event_title']} (剩余 {len(event['news_ids'])} 条)")
            events_to_keep.append(event)

    with open(EVENT_FILE, "w") as f:
        json.dump(events_to_keep, f, ensure_ascii=False, indent=2)

    print(f"\nevent_groups.json: 删除 {events_deleted} 个事件, 保留 {len(events_to_keep)} 个事件")

if __name__ == "__main__":
    main()
