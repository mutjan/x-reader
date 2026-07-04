#!/usr/bin/env python3
"""
迁移upcoming_events中的时代情绪数据到新系统
"""
import json
from datetime import datetime, timedelta
from src.processors.zeitgeist import zeitgeist_manager

def load_upcoming_zeitgeist():
    """加载upcoming_events中的zeitgeist数据"""
    with open('upcoming_events.json', 'r', encoding='utf-8') as f:
        data = json.load(f)

    return data.get('zeitgeist', [])

def migrate_zeitgeist_data():
    """迁移数据"""
    zeitgeist_data = load_upcoming_zeitgeist()
    print(f"发现 {len(zeitgeist_data)} 个待迁移的时代情绪热点")

    # 分类映射
    category_map = {
        "expectation": "social",
        "frustration": "social",
        "skepticism": "social",
        "opportunity": "social"
    }

    # 热度分数到boost_value的映射
    heat_to_boost = {
        70: 2,
        75: 3,
        80: 3,
        82: 4,
        85: 4,
        90: 5
    }

    migrated = 0
    skipped = 0

    for item in zeitgeist_data:
        topic = item['topic']
        keywords = item['keywords']
        description = item['description']
        category = category_map.get(item['category'], "general")
        category_name = item.get('category_name')
        heat_score = item.get('heat_score', 75)
        trend = item.get('trend')
        trend_name = item.get('trend_name')
        related_entities = item.get('related_entities', [])
        created_at = datetime.fromisoformat(item['created_at']) if item.get('created_at') else datetime.now()

        # 计算boost_value，基于热度分数
        boost_value = 2
        for threshold, value in sorted(heat_to_boost.items()):
            if heat_score >= threshold:
                boost_value = value

        # 有效期设置为180天
        duration_days = 180

        # 主关键词使用topic，同时添加相关关键词作为实体
        # 先检查是否已存在
        exists = False
        for trend_obj in zeitgeist_manager.trends:
            if trend_obj.keyword.lower() == topic.lower():
                exists = True
                break

        if exists:
            print(f"跳过已存在的热点: {topic}")
            skipped += 1
            continue

        # 添加热点
        success = zeitgeist_manager.add_trend(
            keyword=topic,
            boost_value=boost_value,
            duration_days=duration_days,
            category=category,
            description=description,
            weight=0.7,
            category_name=category_name,
            heat_score=heat_score,
            trend=trend,
            trend_name=trend_name,
            related_entities=keywords + related_entities,  # 合并关键词和相关实体
            status="active",
            mentions_count=item.get('mentions_count', 0)
        )

        if success:
            print(f"✅ 成功迁移: {topic} (热度{heat_score}, 加分{boost_value})")
            migrated += 1
        else:
            print(f"❌ 迁移失败: {topic}")
            skipped += 1

    print(f"\n迁移完成! 成功: {migrated}, 跳过: {skipped}")
    print(f"当前总热点数: {len(zeitgeist_manager.trends)}")

if __name__ == "__main__":
    migrate_zeitgeist_data()