#!/usr/bin/env python3
"""
手动合并重复新闻脚本
用于修复已存在的重复选题
"""

import json
import re
from datetime import datetime

def merge_news_items(items):
    """合并多个相似的新闻条目"""
    if not items:
        return None

    # 选择评分最高的作为基础
    base = max(items, key=lambda x: x.get('score', 0))

    # 合并所有来源链接
    all_links = []
    seen_urls = set()
    for item in items:
        for link in item.get('sourceLinks', []):
            url = link.get('url', '')
            if url and url not in seen_urls:
                seen_urls.add(url)
                all_links.append(link)

    # 合并实体
    all_entities = []
    seen_entities = set()
    for item in items:
        for entity in item.get('entities', []):
            # 标准化实体名称
            normalized = entity.lower().strip()
            if normalized not in seen_entities:
                seen_entities.add(normalized)
                all_entities.append(entity)

    # 合并标签
    all_tags = []
    seen_tags = set()
    for item in items:
        for tag in item.get('tags', []):
            if tag not in seen_tags:
                seen_tags.add(tag)
                all_tags.append(tag)

    # 创建合并后的新闻
    merged = base.copy()
    merged['sourceLinks'] = all_links[:5]  # 最多保留5个来源
    merged['sources'] = len(all_links)
    merged['entities'] = all_entities[:5]  # 最多保留5个实体
    merged['tags'] = all_tags[:5]  # 最多保留5个标签

    return merged


def find_duplicates_by_content(news_list):
    """基于内容相似度找出重复新闻"""
    groups = []
    processed = set()

    for i, item1 in enumerate(news_list):
        if i in processed:
            continue

        group = [item1]
        processed.add(i)

        title1 = item1.get('title', '').lower()
        entities1 = set(e.lower() for e in item1.get('entities', []))

        for j, item2 in enumerate(news_list[i+1:], start=i+1):
            if j in processed:
                continue

            title2 = item2.get('title', '').lower()
            entities2 = set(e.lower() for e in item2.get('entities', []))

            # 检查是否为同一事件
            is_duplicate = False

            # 1. 标题包含关系
            if title1 in title2 or title2 in title1:
                is_duplicate = True

            # 2. 实体重叠度高
            if entities1 and entities2:
                common = entities1 & entities2
                # 标准化映射
                company_map = {
                    '字节跳动': 'bytedance',
                    'bytedance': 'bytedance',
                    'byte dance': 'bytedance',
                }
                product_map = {
                    'seedance': 'seedance',
                    'seedance 2.0': 'seedance',
                    'ai视频生成': 'seedance',
                    'ai视频模型': 'seedance',
                    'chatgpt': 'chatgpt',
                    'alphafold': 'alphafold',
                    'mrna疫苗': 'mrna',
                    '个性化医疗': 'mrna',
                    'turboquant': 'turboquant',
                }

                norm_entities1 = set()
                norm_entities2 = set()
                for e in entities1:
                    e_lower = e.lower()
                    if e_lower in company_map:
                        norm_entities1.add(company_map[e_lower])
                    elif e_lower in product_map:
                        norm_entities1.add(product_map[e_lower])
                    else:
                        norm_entities1.add(e_lower)

                for e in entities2:
                    e_lower = e.lower()
                    if e_lower in company_map:
                        norm_entities2.add(company_map[e_lower])
                    elif e_lower in product_map:
                        norm_entities2.add(product_map[e_lower])
                    else:
                        norm_entities2.add(e_lower)

                common_norm = norm_entities1 & norm_entities2

                # 如果有3个及以上共同标准化实体
                if len(common_norm) >= 3:
                    is_duplicate = True
                # 如果有2个共同实体且包含关键实体
                elif len(common_norm) >= 2 and any(e in common_norm for e in ['bytedance', 'seedance', 'chatgpt', 'alphafold', 'mrna', 'turboquant']):
                    is_duplicate = True

            if is_duplicate:
                group.append(item2)
                processed.add(j)

        if len(group) > 1:
            groups.append(group)

    return groups


def main():
    # 读取新闻数据
    with open('news_data.json', 'r', encoding='utf-8') as f:
        data = json.load(f)

    today = '2026-03-26'
    if today not in data:
        print("今日无数据")
        return

    news_list = data[today]
    print(f"处理前新闻数量: {len(news_list)}")

    # 找出重复组
    duplicate_groups = find_duplicates_by_content(news_list)
    print(f"\n发现 {len(duplicate_groups)} 组重复新闻:")

    for i, group in enumerate(duplicate_groups):
        print(f"\n组 {i+1}:")
        for item in group:
            print(f"  - {item['title'][:50]}... (评分: {item.get('score', 0)})")

    # 合并重复新闻
    merged_news = []
    processed_indices = set()

    for group in duplicate_groups:
        for item in news_list:
            if item in group:
                processed_indices.add(news_list.index(item))
        merged = merge_news_items(group)
        if merged:
            merged_news.append(merged)

    # 添加未处理的新闻
    for i, item in enumerate(news_list):
        if i not in processed_indices:
            merged_news.append(item)

    print(f"\n处理后新闻数量: {len(merged_news)}")
    print(f"合并了 {len(news_list) - len(merged_news)} 条重复新闻")

    # 保存结果
    data[today] = merged_news
    with open('news_data.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print("\n已保存到 news_data.json")


if __name__ == '__main__':
    main()
