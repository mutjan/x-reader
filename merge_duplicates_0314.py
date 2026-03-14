#!/usr/bin/env python3
"""
合并3月14日的重复新闻条目 - 改进版
使用实体匹配和关键词匹配来识别重复
"""
import json
import re
from datetime import datetime

def load_news_data():
    with open('news_data.json', 'r', encoding='utf-8') as f:
        return json.load(f)

def save_news_data(data):
    with open('news_data.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def extract_core_keywords(title, entities=None):
    """提取标题核心关键词（公司名、产品名、人名等）"""
    # 定义核心实体词
    core_terms = {
        'claude', 'opus', 'sonnet', 'anthropic', '100万', '百万', 'token', '上下文',
        'spacex', 'ipo', '投行',
        'kalanick', 'travis', 'uber', 'atoms', '自动驾驶',
        '马斯克', 'elon', 'musk', '奥特曼', 'altman', 'openai', '诉讼',
        'blackstone', '黑石',
        'medos', '斯坦福', 'princeton', '普林斯顿',
        'google', 'gemini', 'maps',
        'perplexity', 'final', 'pass',
        'sora', 'chatgpt',
        '估值', 'nvidia',
        '地缘政治', 'xai',
        'genspark', 'claw'
    }

    title_lower = title.lower()
    found = set()

    for term in core_terms:
        if term in title_lower:
            found.add(term)

    # 也加入实体
    if entities:
        for e in entities:
            e_lower = e.lower()
            if e_lower in title_lower or any(e_lower in t for t in title_lower.split()):
                found.add(e_lower)

    return found

def is_same_event(item1, item2):
    """判断两条新闻是否报道同一事件"""
    t1, t2 = item1["title"], item2["title"]
    e1 = set(item1.get("entities", []))
    e2 = set(item2.get("entities", []))

    # 1. 检查是否共享关键实体
    common_entities = e1 & e2

    # 2. 提取核心关键词
    k1 = extract_core_keywords(t1, e1)
    k2 = extract_core_keywords(t2, e2)

    # 3. 特定事件匹配规则

    # Claude 100万上下文
    if {'claude', '100万'} <= k1 and {'claude', '100万'} <= k2:
        return True
    if {'claude', '百万'} <= k1 and {'claude', '百万'} <= k2:
        return True
    if {'anthropic', '100万'} <= k1 and {'anthropic', '100万'} <= k2:
        return True

    # SpaceX IPO
    if {'spacex', 'ipo'} <= k1 and {'spacex', 'ipo'} <= k2:
        return True

    # Travis Kalanick / Atoms / Uber
    if 'kalanick' in k1 and 'kalanick' in k2:
        # 都是关于Kalanick的新闻
        return True

    # 马斯克 vs 奥特曼诉讼
    if {'马斯克', 'openai'} <= k1 and {'马斯克', 'openai'} <= k2:
        return True
    if {'musk', 'openai'} <= k1 and {'musk', 'openai'} <= k2:
        return True
    if {'elon', 'altman'} <= k1 and {'elon', 'altman'} <= k2:
        return True
    if '1090亿' in t1 and '1090亿' in t2:
        return True

    # Anthropic前科学家创业
    if 'anthropic' in k1 and 'anthropic' in k2 and ('创业' in t1 or '估值' in t1 or '融资' in t1 or 'startup' in t1.lower()):
        if 'anthropic' in k2 and ('创业' in t2 or '估值' in t2 or '融资' in t2 or 'startup' in t2.lower()):
            return True

    # Anthropic + Blackstone
    if {'anthropic', 'blackstone'} <= k1 and {'anthropic', 'blackstone'} <= k2:
        return True
    if {'anthropic', '黑石'} <= k1 and {'anthropic', '黑石'} <= k2:
        return True

    # OpenAI估值
    if 'openai' in k1 and 'openai' in k2 and ('估值' in t1 or '28倍' in t1):
        if '估值' in t2 or '28倍' in t2:
            return True

    # MedOS
    if 'medos' in k1 and 'medos' in k2:
        return True

    # Claude Code
    if 'claude code' in t1.lower() and 'claude code' in t2.lower():
        return True

    # Perplexity Final Pass
    if {'perplexity', 'final'} <= k1 and {'perplexity', 'final'} <= k2:
        return True

    # Google Gemini
    if {'google', 'gemini'} <= k1 and {'google', 'gemini'} <= k2:
        return True

    # OpenAI/xAI地缘政治
    if {'openai', 'xai'} <= k1 and {'openai', 'xai'} <= k2:
        if '地缘政治' in t1 or '地缘政治' in t2 or '海湾' in t1 or '海湾' in t2 or '中东' in t1 or '中东' in t2:
            return True

    # 高实体重叠 + 关键词重叠
    if len(common_entities) >= 2:
        keyword_overlap = k1 & k2
        if len(keyword_overlap) >= 2:
            return True

    return False

def merge_source_links(existing_links, new_links):
    """合并来源链接，去重"""
    seen_urls = {link["url"] for link in existing_links}
    merged = existing_links.copy()
    for link in new_links:
        if link["url"] not in seen_urls:
            merged.append(link)
            seen_urls.add(link["url"])
    return merged

def merge_entities(existing, new_items):
    """合并实体列表，去重，保留最多5个"""
    merged = list(dict.fromkeys(existing + new_items))
    return merged[:5]

def merge_tags(existing, new_items):
    """合并标签列表，去重，保留最多5个"""
    merged = list(dict.fromkeys(existing + new_items))
    return merged[:5]

def merge_two_items(item1, item2):
    """合并两个相似的新闻条目"""
    # 保留评分更高的作为主条目
    if item2.get("score", 0) > item1.get("score", 0):
        main, secondary = item2, item1
    else:
        main, secondary = item1, item2

    # 合并sourceLinks
    main["sourceLinks"] = merge_source_links(
        main.get("sourceLinks", []),
        secondary.get("sourceLinks", [])
    )
    main["sources"] = len(main["sourceLinks"])

    # 合并entities
    main["entities"] = merge_entities(
        main.get("entities", []),
        secondary.get("entities", [])
    )

    # 合并tags
    main["tags"] = merge_tags(
        main.get("tags", []),
        secondary.get("tags", [])
    )

    # 保留更高的评分和等级
    if secondary.get("score", 0) > main.get("score", 0):
        main["score"] = secondary["score"]
        main["level"] = secondary["level"]
        main["reason"] = secondary["reason"]

    # 选择更详细的标题
    if len(secondary.get("title", "")) > len(main.get("title", "")):
        main["title"] = secondary["title"]

    # 合并英文标题
    if secondary.get("title_en") and len(secondary["title_en"]) > len(main.get("title_en", "")):
        main["title_en"] = secondary["title_en"]

    # 选择更详细的摘要
    if len(secondary.get("summary", "")) > len(main.get("summary", "")):
        main["summary"] = secondary["summary"]

    return main

def find_and_merge_duplicates(news_list):
    """查找并合并重复的新闻条目"""
    merged = []
    skip_indices = set()
    merge_log = []

    for i, item1 in enumerate(news_list):
        if i in skip_indices:
            continue

        # 查找相似的条目
        duplicates = [item1]
        duplicate_indices = [i]

        for j, item2 in enumerate(news_list[i+1:], start=i+1):
            if j in skip_indices:
                continue
            if is_same_event(item1, item2):
                duplicates.append(item2)
                duplicate_indices.append(j)
                skip_indices.add(j)

        if len(duplicates) > 1:
            # 合并所有重复项
            result = duplicates[0]
            for dup in duplicates[1:]:
                result = merge_two_items(result, dup)
            merged.append(result)
            merge_log.append({
                "title": result["title"][:50],
                "count": len(duplicates),
                "indices": duplicate_indices,
                "sources": len(result["sourceLinks"])
            })
        else:
            merged.append(item1)

    return merged, merge_log

def main():
    print("=" * 70)
    print("开始合并3月14日重复新闻条目")
    print("=" * 70)

    data = load_news_data()
    news_0314 = data.get("2026-03-14", [])

    print(f"\n原始条目数: {len(news_0314)}")

    # 显示所有条目标题
    print("\n原始条目列表:")
    for i, item in enumerate(news_0314, 1):
        print(f"  {i:2d}. [{item.get('score', 0):2d}分] {item['title'][:55]}...")

    # 查找并合并重复
    merged, merge_log = find_and_merge_duplicates(news_0314)

    print(f"\n{'='*70}")
    print(f"合并结果")
    print(f"{'='*70}")
    print(f"合并前条目数: {len(news_0314)}")
    print(f"合并后条目数: {len(merged)}")
    print(f"合并去重: {len(news_0314) - len(merged)} 条")

    if merge_log:
        print(f"\n合并详情:")
        for log in merge_log:
            print(f"  • {log['title']}...")
            print(f"    合并了 {log['count']} 条 → 最终 {log['sources']} 个来源")

    # 显示合并后的条目
    print(f"\n{'='*70}")
    print("合并后条目列表:")
    print(f"{'='*70}")
    for i, item in enumerate(merged, 1):
        sources = len(item.get("sourceLinks", []))
        source_info = f"[{sources}来源]" if sources > 1 else "[单来源]"
        print(f"  {i:2d}. [{item.get('score', 0):2d}分]{source_info} {item['title'][:50]}...")

    # 更新数据
    data["2026-03-14"] = merged

    # 保存
    save_news_data(data)
    print(f"\n{'='*70}")
    print("✅ 已保存到 news_data.json")
    print(f"{'='*70}")

if __name__ == "__main__":
    main()
