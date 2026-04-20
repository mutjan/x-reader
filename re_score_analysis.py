#!/usr/bin/env python3
"""
Phase 18 惩罚规则影响分析脚本
加载部署目录的现有新闻，应用 penalty_rules，输出差异报告
"""
import json
import os
from pathlib import Path
from typing import Dict, List, Tuple

# 路径配置
DEPLOY_DIR = Path("/Users/lzw/develop/deploy/x-reader")
NEWS_FILE = DEPLOY_DIR / "data" / "news_data.json"
SCORING_CONFIG_FILE = DEPLOY_DIR / "prompts" / "scoring_config.json"

def load_scoring_config() -> dict:
    """加载评分配置（含 penalty_rules）"""
    if SCORING_CONFIG_FILE.exists():
        with open(SCORING_CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        "grade_thresholds": {"S": 90, "A+": 85, "A": 75, "B": 65, "C": 0},
        "penalty_rules": [],
        "special_bonuses": []
    }

def load_news_data() -> Dict[str, List[dict]]:
    """加载部署目录的新闻数据"""
    if NEWS_FILE.exists():
        with open(NEWS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # 支持两种格式: {"news": {"date": [...]}} 或 {"date": [...]}
            if isinstance(data, dict) and 'news' in data:
                return data['news']
            return data
    return {}

def apply_penalty_rules(item: dict, config: dict) -> Tuple[int, str, List[dict]]:
    """
    应用 penalty_rules，返回 (新分数, 新等级, 命中的规则列表)
    模拟 AIScorer.parse_scoring_response 的逻辑
    """
    original_score = item.get('score', 0)
    original_grade = item.get('grade', 'C')

    # 获取内容用于关键词匹配
    content_lower = (item.get('chinese_title', '') + ' ' +
                    item.get('original_title', '') + ' ' +
                    item.get('summary', '')).lower()

    new_score = original_score
    matched_rules = []
    max_grade_rule = None

    # 应用 penalty_rules（只应用第一个匹配的）
    for rule in config.get('penalty_rules', []):
        keywords = rule.get('keywords', [])
        penalty = rule.get('penalty', 0)
        rule_max_grade = rule.get('max_grade')

        is_matched = any(kw.lower() in content_lower for kw in keywords)
        if is_matched:
            matched_rules.append(rule)

            # 执行分数惩罚
            if penalty != 0:
                new_score = max(new_score + penalty, 0)

            # 记录 max_grade 规则
            if rule_max_grade:
                max_grade_rule = rule
            break  # 只应用第一个匹配的规则

    # 根据新分数重新评定等级
    thresholds = config.get('grade_thresholds', {'S': 90, 'A+': 85, 'A': 75, 'B': 65, 'C': 0})

    if new_score >= thresholds.get('S', 90):
        new_grade = 'S'
    elif new_score >= thresholds.get('A+', 85):
        new_grade = 'A+'
    elif new_score >= thresholds.get('A', 75):
        new_grade = 'A'
    elif new_score >= thresholds.get('B', 65):
        new_grade = 'B'
    else:
        new_grade = 'C'

    # 应用 max_grade 限制
    if max_grade_rule:
        grade_order = {'S': 5, 'A+': 4, 'A': 3, 'B': 2, 'C': 1}
        cap_grade = max_grade_rule['max_grade']
        if grade_order.get(new_grade, 0) > grade_order.get(cap_grade, 0):
            new_grade = cap_grade

    return new_score, new_grade, matched_rules

def main():
    print("=" * 70)
    print("Phase 18 惩罚规则影响分析")
    print("=" * 70)

    # 加载配置和数据
    config = load_scoring_config()
    news_data = load_news_data()

    penalty_rules = config.get('penalty_rules', [])
    print(f"\n加载配置: {len(penalty_rules)} 条 penalty_rules")
    for rule in penalty_rules:
        print(f"  - [{rule.get('name')}]: penalty={rule.get('penalty', 0)}, max_grade={rule.get('max_grade', '无')}")

    # 收集所有新闻
    all_news = []
    for date, items in news_data.items():
        for item in items:
            item_copy = dict(item)  # 复制一份以免修改原始数据
            item_copy['_date'] = date
            all_news.append(item_copy)

    print(f"\n加载新闻数据: {len(all_news)} 条")

    # 分析每条新闻
    affected = []  # 受影响的
    would_be_filtered = []  # 会被过滤（降到C级）
    grade_changed = []  # 等级变化

    for item in all_news:
        new_score, new_grade, rules = apply_penalty_rules(item, config)
        old_score = item.get('score', 0)
        old_grade = item.get('grade', 'C')

        if rules:  # 有命中规则
            affected.append({
                'item': item,
                'old_score': old_score,
                'new_score': new_score,
                'old_grade': old_grade,
                'new_grade': new_grade,
                'rules': rules
            })

            if old_grade != 'C' and new_grade == 'C':
                would_be_filtered.append(item)
            elif old_grade != new_grade:
                grade_changed.append({
                    'item': item,
                    'old': old_grade,
                    'new': new_grade
                })

    # 输出报告
    print(f"\n{'=' * 70}")
    print("统计摘要")
    print(f"{'=' * 70}")
    print(f"总新闻数: {len(all_news)}")
    print(f"命中惩罚规则: {len(affected)}")
    print(f"  - 会被过滤 (降到C级): {len(would_be_filtered)}")
    print(f"  - 等级变化但不过滤: {len(grade_changed)}")

    # 按规则统计
    print(f"\n{'=' * 70}")
    print("各规则命中统计")
    print(f"{'=' * 70}")
    rule_counts = {}
    for a in affected:
        for rule in a['rules']:
            name = rule.get('name', 'unknown')
            rule_counts[name] = rule_counts.get(name, 0) + 1
    for name, count in sorted(rule_counts.items(), key=lambda x: -x[1]):
        print(f"  {name}: {count} 条")

    # 详细列出受影响的新闻
    if affected:
        print(f"\n{'=' * 70}")
        print(f"受影响的新闻详情 (按旧等级排序)")
        print(f"{'=' * 70}")

        # 按旧等级排序 (S > A+ > A > B)
        grade_order = {'S': 5, 'A+': 4, 'A': 3, 'B': 2, 'C': 1}
        affected_sorted = sorted(affected, key=lambda x: -grade_order.get(x['old_grade'], 0))

        for a in affected_sorted[:30]:  # 只显示前30条
            item = a['item']
            title = item.get('chinese_title', item.get('title', item.get('original_title', '')))[:40]
            rule_names = [r.get('name', 'unknown') for r in a['rules']]

            change_marker = "⚠️ " if a['new_grade'] == 'C' else "  "
            print(f"{change_marker}{a['old_grade']}({a['old_score']}) → {a['new_grade']}({a['new_score']}) | {title}...")
            print(f"    规则: {', '.join(rule_names)}")

        if len(affected) > 30:
            print(f"\n... 还有 {len(affected) - 30} 条未显示")

    # 按日期统计
    print(f"\n{'=' * 70}")
    print("按日期统计 (受影响数 / 总数)")
    print(f"{'=' * 70}")
    date_stats = {}
    for date, items in news_data.items():
        total = len(items)
        affected_count = sum(1 for a in affected if a['item']['_date'] == date)
        if affected_count > 0:
            date_stats[date] = (affected_count, total)

    for date in sorted(date_stats.keys()):
        affected_count, total = date_stats[date]
        print(f"  {date}: {affected_count}/{total} ({affected_count/total*100:.1f}%)")

    print(f"\n{'=' * 70}")
    print("结论")
    print(f"{'=' * 70}")
    if len(affected) == 0:
        print("✓ 当前新闻数据中没有任何条目会命中 penalty_rules")
    else:
        print(f"⚠️ 有 {len(affected)} 条新闻会被 penalty_rules 影响")
        print(f"  - {len(would_be_filtered)} 条会被降级到C级并过滤")
        print(f"  - {len(grade_changed)} 条等级变化但仍保留")
        print("\n建议检查这些新闻是否确实是低价值内容")

if __name__ == '__main__':
    main()
