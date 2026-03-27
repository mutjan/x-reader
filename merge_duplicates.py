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
    """基于内容相似度找出重复新闻 - 使用精确配对策略"""
    groups = []
    processed = set()

    def extract_significant_words(title):
        """提取标题中有意义的词汇"""
        words = set(re.findall(r'[\u4e00-\u9fa5]{2,}|[a-zA-Z]+', title.lower()))
        stopwords = {'计划', '预计', '或', '超', '达', '将', '与', '及', '等', '的', '是', '在', '了', '和', '为', '从', '到', '对', '被', '把', '给', '让', '向', '跟', '比', '以', 'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'must', 'shall', 'can', 'to', 'of', 'in', 'for', 'on', 'with', 'at', 'by', 'from', 'as', 'into', 'through', 'during', 'before', 'after', 'above', 'below', 'between', 'under', 'again', 'further', 'then', 'once', 'here', 'there', 'when', 'where', 'why', 'how', 'all', 'each', 'few', 'more', 'most', 'other', 'some', 'such', 'no', 'nor', 'not', 'only', 'own', 'same', 'so', 'than', 'too', 'very', 'just', 'and', 'but', 'if', 'or', 'because', 'until', 'while', 'this', 'that', 'these', 'those', '成为', '史上', '第二大'}
        return words - stopwords

    def calculate_similarity(title1, title2):
        """计算标题Jaccard相似度"""
        words1 = extract_significant_words(title1)
        words2 = extract_significant_words(title2)
        if not words1 or not words2:
            return 0
        intersection = words1 & words2
        union = words1 | words2
        return len(intersection) / len(union) if union else 0

    def get_strict_event_signature(title):
        """
        获取严格的事件签名 - 必须同时包含特定组合才算同一事件
        返回元组 (主体, 事件) 或 None
        """
        t = title.lower()

        # Anthropic + IPO
        if 'anthropic' in t and ('ipo' in t or '上市' in t or 'q4' in t):
            return ('anthropic', 'ipo')

        # SpaceX + IPO
        if 'spacex' in t and ('ipo' in t or '上市' in t):
            return ('spacex', 'ipo')

        # Meta + TRIBE
        if 'meta' in t and 'tribe' in t:
            return ('meta', 'tribe')

        # Cursor + Composer
        if 'cursor' in t and 'composer' in t:
            return ('cursor', 'composer')

        # Claude + 越狱/攻击 (特定技术事件)
        if 'claude' in t and ('越狱' in t or '攻击' in t or 'jailbreak' in t):
            return ('claude', 'jailbreak')

        # Claude Code + 定时任务/插件 (特定功能) - 需要更严格的匹配
        if 'claude code' in t and ('定时' in t or '插件' in t or '网页' in t):
            return ('claude', 'code_feature')

        return None

    def are_strictly_similar(item1, item2):
        """
        判断两条新闻是否严格相似（必须满足多个条件之一）
        这是核心配对函数，必须非常严格
        """
        title1 = item1.get('title', '')
        title2 = item2.get('title', '')
        t1_lower = title1.lower()
        t2_lower = title2.lower()
        entities1 = set(e.lower() for e in item1.get('entities', []))
        entities2 = set(e.lower() for e in item2.get('entities', []))

        # 1. 严格事件签名匹配
        sig1 = get_strict_event_signature(title1)
        sig2 = get_strict_event_signature(title2)
        if sig1 and sig2 and sig1 == sig2:
            return True

        # 2. 高标题相似度 (>= 0.75)
        sim = calculate_similarity(title1, title2)
        if sim >= 0.75:
            return True

        # 3. 标题互相包含（且长度都>15，避免短词误匹配）
        if len(title1) > 15 and len(title2) > 15:
            if t1_lower in t2_lower or t2_lower in t1_lower:
                return True

        # 4. 至少2个具体实体匹配 + 高相似度标题 (>= 0.5)
        if entities1 and entities2:
            generic = {'ai', '人工智能', '科技', '公司', '产品', '技术', '模型', '用户', '市场', '平台', '服务', '系统', '应用', '投资', '融资', '估值', '上市', 'ipo', '裁员', '招聘', '团队', 'ceo', '创始人', '高管'}
            specific1 = entities1 - generic
            specific2 = entities2 - generic
            common = specific1 & specific2
            if len(common) >= 2 and sim >= 0.5:
                return True

        return False

    # 使用并查集思路：先找出所有相似对，然后合并连通分量
    n = len(news_list)
    parent = list(range(n))

    def find(x):
        if parent[x] != x:
            parent[x] = find(parent[x])
        return parent[x]

    def union(x, y):
        px, py = find(x), find(y)
        if px != py:
            parent[px] = py

    # 找出所有相似对
    for i in range(n):
        for j in range(i + 1, n):
            if are_strictly_similar(news_list[i], news_list[j]):
                union(i, j)

    # 按根节点分组
    group_map = {}
    for i in range(n):
        root = find(i)
        if root not in group_map:
            group_map[root] = []
        group_map[root].append(news_list[i])

    # 只返回有多于一条新闻的组
    groups = [group for group in group_map.values() if len(group) > 1]

    return groups


def main():
    # 读取新闻数据
    with open('news_data.json', 'r', encoding='utf-8') as f:
        data = json.load(f)

    today = '2026-03-27'
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
