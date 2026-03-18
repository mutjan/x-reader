#!/usr/bin/env python3
"""
预告事件管理模块
维护已预告事件列表，定期检查是否有新消息

使用场景：
- No Priors 预告下期嘉宾是 Karpathy
- 某会议预告某大佬将发表演讲
- 产品发布预告

工作流程：
1. 添加预告事件到 upcoming_events.json
2. 每次执行新闻更新时，检查 RSS 内容是否匹配预告
3. 如果匹配成功，将事件从预告列表移除，加入正式选题
"""

import json
import os
import re
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

# 文件配置
UPCOMING_EVENTS_FILE = "upcoming_events.json"

# 默认空数据结构
DEFAULT_EVENTS_DATA = {
    "version": "1.0",
    "last_checked": None,
    "events": []
}


def load_upcoming_events():
    """加载预告事件列表"""
    if not os.path.exists(UPCOMING_EVENTS_FILE):
        return DEFAULT_EVENTS_DATA.copy()
    
    try:
        with open(UPCOMING_EVENTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        # 确保必要字段存在
        if "events" not in data:
            data["events"] = []
        if "version" not in data:
            data["version"] = "1.0"
        return data
    except Exception as e:
        logger.error(f"[预告事件] 加载失败: {e}")
        return DEFAULT_EVENTS_DATA.copy()


def save_upcoming_events(data):
    """保存预告事件列表"""
    try:
        data["last_checked"] = datetime.now().isoformat()
        with open(UPCOMING_EVENTS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"[预告事件] 保存失败: {e}")
        return False


def add_upcoming_event(title, description, expected_keywords, source_hint="", 
                       expected_date=None, priority="A"):
    """
    添加新的预告事件
    
    Args:
        title: 事件标题（如 "No Priors 预告：Karpathy 将做客下期节目"）
        description: 事件描述
        expected_keywords: 用于匹配的关键词列表（如 ["No Priors", "Karpathy", "podcast"]）
        source_hint: 来源提示（如 "No Priors 播客"）
        expected_date: 预计发布时间（ISO格式，可选）
        priority: 预期优先级（S/A+/A/B）
    """
    data = load_upcoming_events()
    
    # 生成唯一ID
    event_id = f"evt_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{len(data['events'])}"
    
    event = {
        "id": event_id,
        "title": title,
        "description": description,
        "expected_keywords": expected_keywords if isinstance(expected_keywords, list) else [expected_keywords],
        "source_hint": source_hint,
        "expected_date": expected_date,
        "priority": priority,
        "created_at": datetime.now().isoformat(),
        "status": "pending",  # pending, found, expired
        "found_news": None,  # 找到后填入新闻数据
        "check_count": 0  # 检查次数
    }
    
    data["events"].append(event)
    save_upcoming_events(data)
    
    logger.info(f"[预告事件] 已添加: {title} (ID: {event_id})")
    return event_id


def remove_upcoming_event(event_id):
    """移除预告事件"""
    data = load_upcoming_events()
    original_count = len(data["events"])
    data["events"] = [e for e in data["events"] if e["id"] != event_id]
    
    if len(data["events"]) < original_count:
        save_upcoming_events(data)
        logger.info(f"[预告事件] 已移除: {event_id}")
        return True
    return False


def update_event_status(event_id, status, found_news=None):
    """更新事件状态"""
    data = load_upcoming_events()
    
    for event in data["events"]:
        if event["id"] == event_id:
            event["status"] = status
            if found_news:
                event["found_news"] = found_news
            save_upcoming_events(data)
            return True
    
    return False


def check_item_against_events(item):
    """
    检查单条新闻是否匹配任何预告事件
    
    Returns:
        (matched_event_id, match_details) 或 (None, None)
    """
    data = load_upcoming_events()
    pending_events = [e for e in data["events"] if e["status"] == "pending"]
    
    if not pending_events:
        return None, None
    
    text = f"{item.get('title', '')} {item.get('content', '')}".lower()
    url = item.get('url', '').lower()
    
    for event in pending_events:
        keywords = event.get("expected_keywords", [])
        if not keywords:
            continue
        
        match_count = 0
        matched_keywords = []
        
        for keyword in keywords:
            keyword_lower = keyword.lower()
            if keyword_lower in text or keyword_lower in url:
                match_count += 1
                matched_keywords.append(keyword)
        
        # 匹配规则：
        # 1. 如果有 2+ 个关键词匹配，认为命中
        # 2. 如果只有 1 个关键词，但权重很高（如人名+产品名），也命中
        if match_count >= 2 or (match_count == 1 and len(keywords) == 1):
            match_details = {
                "event_id": event["id"],
                "event_title": event["title"],
                "matched_keywords": matched_keywords,
                "match_score": match_count / len(keywords) if keywords else 0
            }
            return event["id"], match_details
    
    return None, None


def check_items_against_events(items):
    """
    批量检查新闻列表，返回匹配的事件和新闻
    
    Returns:
        {
            "matched": [(event, news_item), ...],
            "unmatched": [item, ...]
        }
    """
    matched = []
    unmatched = []
    
    # 跟踪已匹配的事件ID，避免重复匹配
    matched_event_ids = set()
    
    for item in items:
        event_id, match_details = check_item_against_events(item)
        
        if event_id and event_id not in matched_event_ids:
            # 加载完整事件信息
            data = load_upcoming_events()
            event = next((e for e in data["events"] if e["id"] == event_id), None)
            
            if event:
                matched.append((event, item, match_details))
                matched_event_ids.add(event_id)
        else:
            unmatched.append(item)
    
    return {"matched": matched, "unmatched": unmatched}


def convert_matched_to_news(event, item, match_details):
    """
    将匹配的预告事件转换为正式新闻格式
    
    Returns:
        符合 news_data.json 格式的新闻条目
    """
    from update_news import generate_version, calculate_priority_score
    
    # 基于事件预设优先级确定基础分数
    priority = event.get("priority", "A")
    base_scores = {"S": 95, "A+": 87, "A": 80, "B": 70}
    base_score = base_scores.get(priority, 75)
    
    # 计算关键词得分加成
    keyword_score = calculate_priority_score(item) if 'calculate_priority_score' in dir() else 0
    
    # 预告事件匹配加分（因为是期待的内容）
    anticipation_bonus = 5
    
    final_score = min(100, base_score + keyword_score * 0.1 + anticipation_bonus)
    
    # 确定 level
    if final_score >= 90:
        level = "S"
    elif final_score >= 85:
        level = "A+"
    elif final_score >= 75:
        level = "A"
    else:
        level = "B"
    
    news_item = {
        "title": f"【预告落地】{item.get('title', event['title'])}",
        "title_en": item.get("title", ""),
        "summary": f"此前预告的事件已发布。{item.get('content', event['description'])[:150]}...",
        "score": int(final_score),
        "level": level,
        "rating": level,
        "reason": f"【{level}级】评分{int(final_score)}分 | 预告事件落地: {event['title']} | 匹配关键词: {', '.join(match_details.get('matched_keywords', []))}",
        "entities": event.get("expected_keywords", [])[:5],
        "tags": ["预告落地", event.get("source_hint", "")],
        "url": item.get("url", ""),
        "source": item.get("source", "Unknown"),
        "sources": 1,
        "sourceLinks": [{"name": item.get("source", "Unknown"), "url": item.get("url", "")}],
        "timestamp": int(datetime.now().timestamp()),
        "version": generate_version() if 'generate_version' in dir() else datetime.now().strftime('%Y.%m.%d-001'),
        "is_upcoming_event": True,
        "upcoming_event_id": event["id"],
        "upcoming_event_source": event.get("source_hint", "")
    }
    
    return news_item


def get_pending_events_summary():
    """获取待处理预告事件摘要"""
    data = load_upcoming_events()
    pending = [e for e in data["events"] if e["status"] == "pending"]
    
    return {
        "total": len(data["events"]),
        "pending": len(pending),
        "found": len([e for e in data["events"] if e["status"] == "found"]),
        "expired": len([e for e in data["events"] if e["status"] == "expired"]),
        "pending_list": [
            {
                "id": e["id"],
                "title": e["title"],
                "source_hint": e.get("source_hint", ""),
                "keywords": e.get("expected_keywords", []),
                "created_at": e["created_at"]
            }
            for e in pending
        ]
    }


def cleanup_expired_events(days=30):
    """清理过期的预告事件"""
    data = load_upcoming_events()
    cutoff = datetime.now() - timedelta(days=days)
    
    original_count = len(data["events"])
    
    # 保留：pending 状态 或 30天内的 found/expired
    filtered_events = []
    for event in data["events"]:
        if event["status"] == "pending":
            filtered_events.append(event)
        else:
            created = datetime.fromisoformat(event["created_at"])
            if created > cutoff:
                filtered_events.append(event)
    
    data["events"] = filtered_events
    save_upcoming_events(data)
    
    removed = original_count - len(filtered_events)
    if removed > 0:
        logger.info(f"[预告事件] 清理了 {removed} 条过期事件")
    
    return removed


# CLI 接口
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="预告事件管理工具")
    subparsers = parser.add_subparsers(dest="command", help="可用命令")
    
    # 添加事件
    add_parser = subparsers.add_parser("add", help="添加预告事件")
    add_parser.add_argument("--title", required=True, help="事件标题")
    add_parser.add_argument("--description", default="", help="事件描述")
    add_parser.add_argument("--keywords", required=True, help="匹配关键词（逗号分隔）")
    add_parser.add_argument("--source", default="", help="来源提示")
    add_parser.add_argument("--date", default="", help="预计日期（YYYY-MM-DD）")
    add_parser.add_argument("--priority", default="A", choices=["S", "A+", "A", "B"], help="预期优先级")
    
    # 列出事件
    list_parser = subparsers.add_parser("list", help="列出所有预告事件")
    list_parser.add_argument("--status", default="pending", choices=["all", "pending", "found", "expired"], help="筛选状态")
    
    # 移除事件
    remove_parser = subparsers.add_parser("remove", help="移除预告事件")
    remove_parser.add_argument("event_id", help="事件ID")
    
    # 清理过期
    cleanup_parser = subparsers.add_parser("cleanup", help="清理过期事件")
    cleanup_parser.add_argument("--days", type=int, default=30, help="过期天数")
    
    args = parser.parse_args()
    
    if args.command == "add":
        keywords = [k.strip() for k in args.keywords.split(",")]
        event_id = add_upcoming_event(
            title=args.title,
            description=args.description,
            expected_keywords=keywords,
            source_hint=args.source,
            expected_date=args.date if args.date else None,
            priority=args.priority
        )
        print(f"✅ 已添加预告事件: {event_id}")
    
    elif args.command == "list":
        data = load_upcoming_events()
        events = data["events"]
        if args.status != "all":
            events = [e for e in events if e["status"] == args.status]
        
        print(f"\n📋 预告事件列表 ({len(events)} 条)\n")
        for e in events:
            print(f"ID: {e['id']}")
            print(f"  标题: {e['title']}")
            print(f"  状态: {e['status']}")
            print(f"  关键词: {', '.join(e.get('expected_keywords', []))}")
            print(f"  来源: {e.get('source_hint', '-')}")
            print(f"  创建时间: {e['created_at']}")
            print()
    
    elif args.command == "remove":
        if remove_upcoming_event(args.event_id):
            print(f"✅ 已移除事件: {args.event_id}")
        else:
            print(f"❌ 未找到事件: {args.event_id}")
    
    elif args.command == "cleanup":
        removed = cleanup_expired_events(args.days)
        print(f"✅ 清理了 {removed} 条过期事件")
    
    else:
        # 默认显示摘要
        summary = get_pending_events_summary()
        print(f"\n📊 预告事件统计\n")
        print(f"  总计: {summary['total']}")
        print(f"  待处理: {summary['pending']}")
        print(f"  已找到: {summary['found']}")
        print(f"  已过期: {summary['expired']}")
        
        if summary['pending_list']:
            print(f"\n  待处理事件:\n")
            for e in summary['pending_list']:
                print(f"    - {e['title']} ({e['source_hint']})")
