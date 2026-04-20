#!/usr/bin/env python3
"""
调试脚本：查看被过滤的新闻内容和得分
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.fetchers.factory import FetcherFactory
from src.processors.filter import NewsFilter
from src.processors.duplicate import DuplicateRemover
from src.utils.common import setup_logger

logger = setup_logger("debug_filter")

def main():
    # 初始化组件
    fetchers = FetcherFactory.get_all_fetchers()
    duplicate_remover = DuplicateRemover()
    news_filter = NewsFilter()

    # 获取最近2小时新闻
    all_raw_items = []
    for fetcher in fetchers:
        logger.info(f"获取 {fetcher.source_name} 新闻...")
        items = fetcher.fetch(time_window_hours=2)
        all_raw_items.extend(items)
        logger.info(f"获取到 {len(items)} 条 {fetcher.source_name} 新闻")

    if not all_raw_items:
        logger.warning("没有获取到任何新闻")
        return

    # 去重
    logger.info("去重前: %d 条" % len(all_raw_items))
    unique_items = duplicate_remover.deduplicate_raw(all_raw_items)
    logger.info("去重后: %d 条" % len(unique_items))

    # 计算所有新闻的得分，不进行过滤
    logger.info("\n=== 所有新闻得分详情 ===")
    for i, item in enumerate(unique_items):
        is_blacklist, blacklist_keywords = news_filter.is_blacklisted(item)
        score, matched_keywords = news_filter.calculate_priority_score(item)

        status = "✓ 保留" if not is_blacklist and score >= 30 else "✗ 过滤"
        reason = []
        if is_blacklist:
            reason.append(f"黑名单关键词: {blacklist_keywords}")
        if score < 30:
            reason.append(f"得分不足: {score}/30")

        print(f"\n[{i+1}] {status}")
        print(f"标题: {item.title}")
        print(f"来源: {item.source}")
        print(f"发布时间: {item.published_at}")
        print(f"URL: {item.url}")
        print(f"得分: {score}")
        if matched_keywords:
            print(f"匹配关键词: {matched_keywords}")
        if reason:
            print(f"过滤原因: {', '.join(reason)}")
        print(f"内容摘要: {item.content[:200]}..." if len(item.content) > 200 else f"内容: {item.content}")
        print("-" * 80)

    # 统计
    total = len(unique_items)
    passed = sum(1 for item in unique_items if not news_filter.is_blacklisted(item)[0] and news_filter.calculate_priority_score(item)[0] >= 30)
    filtered = total - passed

    logger.info(f"\n=== 统计信息 ===")
    logger.info(f"总新闻数: {total}")
    logger.info(f"通过筛选: {passed}")
    logger.info(f"被过滤: {filtered}")

if __name__ == "__main__":
    main()
