#!/usr/bin/env python3
"""
验证分类修复效果
"""
import json
from src.models.news import ProcessedNewsItem

# 加载AI结果
with open('full_ai_result.json', 'r', encoding='utf-8') as f:
    ai_results = json.load(f)

# 构造测试新闻项
test_items = []
for i, result in enumerate(ai_results[:5]):  # 测试前5条
    # 创建模拟的ProcessedNewsItem
    from datetime import datetime
    item = ProcessedNewsItem(
        id=f"test_{i}",
        original_title=result.get("chinese_title", ""),
        original_content=result.get("summary", ""),
        source="Test",
        url=f"https://example.com/{i}",
        published_at=datetime.now(),
        chinese_title=result.get("chinese_title", ""),
        summary=result.get("summary", ""),
        grade=result.get("grade", "A"),
        score=result.get("score", 80),
        news_type=result.get("type", ""),
        extension=result.get("extension", ""),
        entities=result.get("entities", [])
    )
    test_items.append(item)

# 测试分类映射
print("分类映射验证结果：")
print("-" * 80)
print(f"{'原始分类':<15} {'分类名称':<15} {'标题'}")
print("-" * 80)

type_counts = {}
for item in test_items:
    front_dict = item.to_frontend_dict()
    news_type = front_dict["type"]
    type_name = front_dict["typeName"]

    if news_type not in type_counts:
        type_counts[news_type] = 0
    type_counts[news_type] += 1

    print(f"{news_type:<15} {type_name:<15} {item.chinese_title[:20]}...")

print("-" * 80)
print(f"\n总分类数: {len(type_counts)}种")
print("分类列表:")
for t in sorted(type_counts.keys()):
    print(f"  {t}")

# 检查所有12种分类是否都在映射表中
type_map = {
    "product": "产品发布",
    "funding": "融资上市",
    "personnel": "人事变动",
    "opinion": "观点访谈",
    "industry": "行业动态",
    "safety": "安全伦理",
    "research": "研究成果",
    "financial": "商业数据",
    "breaking": "突发事件",
    "tool": "工具技巧",
    "society": "社会影响",
    "hardware": "硬件基建"
}

print("\n分类映射表完整性检查:")
all_types = set(type_map.keys())
current_types = set(type_counts.keys())
missing_types = all_types - current_types
extra_types = current_types - all_types

if missing_types:
    print(f"⚠️  缺失的分类: {missing_types}")
else:
    print("✅ 所有12种分类都已正确映射")

if extra_types:
    print(f"⚠️  多余的分类: {extra_types}")
else:
    print("✅ 没有多余分类")

# 检查NeurIPS新闻的分类
print("\nNeurIPS新闻分类检查:")
for i, result in enumerate(ai_results):
    if 'NeurIPS' in result.get("chinese_title", ""):
        news_type = result.get("type", "")
        type_name = type_map.get(news_type, news_type)
        print(f"  标题: {result.get('chinese_title')}")
        print(f"  分类: {news_type} - {type_name}")
        print()