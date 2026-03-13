#!/usr/bin/env python3
"""
本地规则驱动的新闻处理脚本（无需 AI API）
基于 content_rules_v2.md 的评分规则
"""

import json
import re
from datetime import datetime
import time
import os

# 高优先级关键词配置
S_KEYWORDS = {
    '人物': ['马斯克', 'elon musk', 'sam altman', '奥特曼', '黄仁勋', '黄仁勳', 'jensen huang', '稚晖君', '彭志辉'],
    '公司': ['openai', 'anthropic', 'deepmind', 'spacex', 'tesla', 'xai', 'nature', 'science', 'cell'],
    '事件': ['gpt-5', 'gpt-4.5', 'gpt-4o', 'claude 4', 'claude 3.5', 'gemini 2', '发布', 'launch', '发布'],
}

A_KEYWORDS = {
    '人物': ['李彦宏', '王小川', '李志飞', '张一鸣', '雷军', '任正非', '马云', '马化腾'],
    '公司': ['字节', 'bytedance', '豆包', '阿里', 'alibaba', '通义', '百度', '文心', '腾讯', '混元',
            '智谱', '月之暗面', 'kimi', 'minimax', '零一万物', '微软', 'microsoft', '谷歌', 'google',
            'meta', '苹果', 'apple', '英伟达', 'nvidia', '华为', '小米', '大疆'],
    '事件': ['开源', 'github', 'arxiv', '突破', '颠覆', '首次', '首个', '第一', '创纪录'],
}

B_KEYWORDS = {
    '事件': ['评测', '实测', '体验', '解析', '分析', '教程', '指南'],
}

def score_item(item):
    """基于规则评分"""
    title = item.get('title', '').lower()
    content = item.get('content', '').lower()
    source = item.get('source', '').lower()
    text = title + ' ' + content

    score = 50  # 基础分
    level = 'C'
    news_type = 'tech'
    reasons = []

    # 政治/军事/法律类新闻降权（除非是重大事件）
    political_keywords = ['trump', 'biden', '特朗普', '拜登', '政府', 'government', 'administration',
                          'policy', '政策', 'regulation', '监管', 'ban', '禁令']
    military_keywords = ['war', '战争', 'military', '军事', 'defense', '国防', 'weapon', '武器',
                         'attack', '攻击', 'conflict', '冲突']
    legal_keywords = ['lawsuit', '诉讼', '起诉', '被告', '原告', 'court', '法庭', 'judge', '法官',
                      'trial', '审判', 'patent', '专利', 'copyright', '版权']

    political_count = sum(1 for kw in political_keywords if kw in text)
    military_count = sum(1 for kw in military_keywords if kw in text)
    legal_count = sum(1 for kw in legal_keywords if kw in text)

    # 重大事件判定：涉及科技巨头
    major_event_indicators = ['google', 'microsoft', 'apple', 'meta', 'amazon', 'openai', 'nvidia',
                              'bytedance', 'tencent', 'alibaba', '字节', '腾讯', '阿里']
    is_tech_major = any(ind in text for ind in major_event_indicators)

    # 非重大事件时降权
    if not is_tech_major:
        if political_count >= 2:
            score -= 15
            reasons.append("政治类-降权")
        if military_count >= 1:
            score -= 20
            reasons.append("军事类-降权")
        if legal_count >= 2:
            score -= 10
            reasons.append("一般法律纠纷-降权")

    score = max(score, 0)

    # S级评分 (90-100)
    for kw in S_KEYWORDS['人物']:
        if kw in text:
            score = max(score, 95)
            reasons.append(f"热点人物: {kw}")
            news_type = 'hot'
            break

    for kw in S_KEYWORDS['公司']:
        if kw in text:
            score = max(score, 90)
            reasons.append(f"顶级机构: {kw}")
            if kw in ['nature', 'science']:
                news_type = 'tech'
            else:
                news_type = 'ai' if 'ai' in text or 'artificial' in text else 'hot'
            break

    for kw in S_KEYWORDS['事件']:
        if kw in text:
            score = max(score, 92)
            reasons.append(f"重大发布: {kw}")
            news_type = 'ai'
            break

    # A级评分 (75-89)
    if score < 90:
        for kw in A_KEYWORDS['人物']:
            if kw in text:
                score = max(score, 80)
                reasons.append(f"行业人物: {kw}")
                break

        for kw in A_KEYWORDS['公司']:
            if kw in text:
                score = max(score, 78)
                reasons.append(f"科技巨头: {kw}")
                if 'ai' in text or '大模型' in text:
                    news_type = 'ai'
                break

        for kw in A_KEYWORDS['事件']:
            if kw in text:
                score = max(score, 82)
                reasons.append(f"突破性事件: {kw}")
                break

    # B级评分 (60-74)
    if score < 75:
        for kw in B_KEYWORDS['事件']:
            if kw in text:
                score = max(score, 65)
                reasons.append(f"技术内容: {kw}")
                break

    # AI 相关内容加分
    if any(kw in text for kw in ['ai', '人工智能', '大模型', 'llm', 'gpt', 'claude', 'gemini', '模型']):
        score += 5
        if news_type == 'tech':
            news_type = 'ai'

    # 多源报道检测（在聚合阶段处理）

    # 确定等级
    if score >= 90:
        level = 'S'
    elif score >= 75:
        level = 'A'
    elif score >= 60:
        level = 'B'
    else:
        level = 'C'

    return {
        'score': min(score, 100),
        'level': level,
        'type': news_type,
        'reasons': reasons
    }

def generate_chinese_title(item):
    """生成中文标题"""
    title_en = item.get('title', '')

    # 简单翻译/转换规则
    title_map = {
        'openai': 'OpenAI',
        'gpt': 'GPT',
        'claude': 'Claude',
        'gemini': 'Gemini',
        'google': '谷歌',
        'microsoft': '微软',
        'apple': '苹果',
        'meta': 'Meta',
        'nvidia': '英伟达',
        'tesla': '特斯拉',
        'spacex': 'SpaceX',
        'xai': 'xAI',
        'elon musk': '马斯克',
        'sam altman': '奥特曼',
    }

    title_lower = title_en.lower()

    # 生成中文标题
    if 'launch' in title_lower or 'release' in title_lower or '发布' in title_lower:
        if 'gpt' in title_lower or 'model' in title_lower:
            return f"OpenAI发布新一代模型，能力全面升级"
        elif 'claude' in title_lower:
            return f"Anthropic发布Claude新版本，性能大幅提升"

    if 'elon' in title_lower or 'musk' in title_lower:
        return f"马斯克最新动态：{title_en[:30]}..."

    if 'spacex' in title_lower or 'rocket' in title_lower:
        return f"SpaceX航天新突破：{title_en[:30]}..."

    # 默认返回原标题
    return title_en[:60]

def calculate_similarity(s1, s2):
    """计算两个字符串的相似度"""
    s1_lower, s2_lower = s1.lower(), s2.lower()
    if s1_lower in s2_lower or s2_lower in s1_lower:
        return 0.8

    stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by'}

    def extract_kw(text):
        words = re.findall(r'\b\w{4,}\b', re.sub(r'[^\w\s]', ' ', text.lower()))
        return set(w for w in words if w not in stop_words)

    kw1, kw2 = extract_kw(s1), extract_kw(s2)
    if not kw1 or not kw2:
        return 0
    return len(kw1 & kw2) / len(kw1 | kw2)

def group_by_event(items):
    """按事件分组"""
    groups = []
    used = set()

    for i, item in enumerate(items):
        if i in used:
            continue

        group = [item]
        used.add(i)
        title1 = item["title"]

        for j, other in enumerate(items[i + 1:], i + 1):
            if j in used:
                continue
            title2 = other["title"]
            sim = calculate_similarity(title1, title2)
            if sim > 0.5:
                group.append(other)
                used.add(j)

        groups.append(group)

    return groups

def main():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 开始本地规则驱动的新闻处理...")

    # 读取原始数据
    try:
        with open('news_raw_2026-03-08.json', 'r', encoding='utf-8') as f:
            items = json.load(f)
    except:
        print("未找到缓存数据，需要重新获取")
        return

    print(f"读取到 {len(items)} 条原始内容")

    # 评分
    scored_items = []
    for item in items:
        scoring = score_item(item)
        if scoring['level'] != 'C':  # 只保留 B 级及以上
            item['_scoring'] = scoring
            scored_items.append(item)

    print(f"筛选出 {len(scored_items)} 条高潜力选题")

    # 按事件分组
    event_groups = group_by_event(scored_items)
    print(f"聚合为 {len(event_groups)} 个独立事件")

    # 构建输出
    processed = []
    for group in event_groups:
        # 取评分最高的作为代表
        representative = max(group, key=lambda x: x['_scoring']['score'])
        scoring = representative['_scoring']

        # 合并来源
        all_links = []
        seen_urls = set()
        for item in group:
            url = item.get('url', '')
            source = item.get('source', 'Unknown')
            if url and url not in seen_urls:
                all_links.append({'name': source, 'url': url})
                seen_urls.add(url)

        # 多源加分
        source_count = len(all_links)
        final_score = min(scoring['score'] + (source_count - 1) * 5, 100)

        # 构建选题理由
        level_labels = {'S': 'S级必报', 'A': 'A级优先', 'B': 'B级可选'}
        reason_text = f"【{level_labels.get(scoring['level'], scoring['level'])}】评分{final_score}分"
        if source_count > 1:
            reason_text += f" | {source_count}个来源报道"
        if scoring['reasons']:
            reason_text += f" | {'; '.join(scoring['reasons'][:2])}"

        processed.append({
            'title': generate_chinese_title(representative),
            'title_en': representative['title'],
            'summary': representative.get('content', '点击链接查看详情')[:150] + '...' if len(representative.get('content', '')) > 150 else representative.get('content', '点击链接查看详情'),
            'type': scoring['type'],
            'typeName': {'hot': '热点', 'ai': 'AI', 'tech': '科技', 'business': '商业'}.get(scoring['type'], '科技'),
            'score': final_score,
            'level': scoring['level'],
            'reason': reason_text,
            'url': representative.get('url', ''),
            'source': representative.get('source', 'Unknown'),
            'sources': source_count,
            'sourceLinks': all_links,
            'timestamp': int(time.time()),
            'version': datetime.now().strftime('%Y.%m.%d-001'),
        })

    # 按分数排序
    processed.sort(key=lambda x: x['score'], reverse=True)

    # 统计
    s_count = len([t for t in processed if t['level'] == 'S'])
    a_count = len([t for t in processed if t['level'] == 'A'])
    b_count = len([t for t in processed if t['level'] == 'B'])
    multi_source = len([t for t in processed if t['sources'] > 1])

    print(f"\n处理完成!")
    print(f"  获取内容总数: {len(items)}")
    print(f"  S级(必报): {s_count} 条")
    print(f"  A级(优先): {a_count} 条")
    print(f"  B级(可选): {b_count} 条")
    print(f"  多源报道: {multi_source} 条")

    print(f"\n高潜力选题标题 (前10条):")
    for i, item in enumerate(processed[:10], 1):
        print(f"  {i}. [{item['level']}级|{item['score']}分] {item['title']}")

    # 保存结果
    today = datetime.now().strftime('%Y-%m-%d')
    data_file = 'news_data.json'

    if os.path.exists(data_file):
        with open(data_file, 'r', encoding='utf-8') as f:
            archive = json.load(f)
    else:
        archive = {}

    archive[today] = processed

    # 只保留最近30天
    dates = sorted(archive.keys())
    if len(dates) > 30:
        for old_date in dates[:-30]:
            del archive[old_date]

    with open(data_file, 'w', encoding='utf-8') as f:
        json.dump(archive, f, ensure_ascii=False, indent=2)

    print(f"\n数据已保存到 {data_file}")

if __name__ == '__main__':
    main()
