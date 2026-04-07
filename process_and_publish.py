#!/usr/bin/env python3
"""
直接处理现有AI结果并发布的简单脚本
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import json
from datetime import datetime
from src.models.news import RawNewsItem, ProcessedNewsItem
from src.processors.ai_processor import ManualProcessor, AIScorer
from src.processors.duplicate import DuplicateRemover
from src.publishers.factory import PublisherFactory
from src.utils.common import setup_logger, load_json
from src.fetchers.factory import FetcherFactory
from src.processors.filter import NewsFilter

logger = setup_logger("process_and_publish")

def main():
    logger.info("=" * 60)
    logger.info("处理现有AI结果并发布")
    logger.info("=" * 60)

    # 1. 初始化组件
    duplicate_remover = DuplicateRemover()
    news_filter = NewsFilter()
    ai_processor = ManualProcessor()
    ai_scorer = AIScorer()
    publisher = PublisherFactory.get_publisher("github_pages")

    # 2. 重新获取和预处理数据（以重建原始新闻项）
    logger.info("重新获取原始数据...")
    fetchers = FetcherFactory.get_all_fetchers()

    all_raw_items = []
    for fetcher in fetchers:
        logger.info(f"获取 {fetcher.source_name} 新闻...")
        items = fetcher.fetch(time_window_hours=24)
        all_raw_items.extend(items)

    logger.info(f"总共获取到 {len(all_raw_items)} 条原始新闻")

    # 去重
    unique_items = duplicate_remover.deduplicate_raw(all_raw_items)
    logger.info(f"去重后保留 {len(unique_items)} 条")

    # 预筛选
    filtered_items = news_filter.filter_news(unique_items, min_score=10)
    logger.info(f"预筛选后保留 {len(filtered_items)} 条")

    if not filtered_items:
        logger.info("没有需要处理的新闻")
        return 0

    # 3. 加载AI基础处理结果
    base_result_file = "_ai_base_result.json"
    if not os.path.exists(base_result_file):
        logger.error(f"基础结果文件 {base_result_file} 不存在")
        return 1

    logger.info(f"加载AI基础处理结果: {base_result_file}")
    processed_items = ai_processor.load_manual_result(base_result_file, filtered_items)

    if not processed_items:
        logger.warning("没有有效的处理结果")
        return 1

    # 4. 处理后去重
    logger.info("处理后去重...")
    processed_items = duplicate_remover.deduplicate_processed(processed_items)

    if not processed_items:
        logger.warning("去重后没有剩余新闻")
        return 1

    # 5. 加载打分结果
    scoring_result_file = "_ai_scoring_result.json"
    if not os.path.exists(scoring_result_file):
        logger.error(f"打分结果文件 {scoring_result_file} 不存在")
        return 1

    logger.info(f"加载AI打分结果: {scoring_result_file}")
    scored_items = ai_scorer.load_manual_scoring_result(scoring_result_file, processed_items)

    if not scored_items:
        logger.warning("没有有效的打分结果")
        return 1

    logger.info(f"最终得到 {len(scored_items)} 条有效新闻")

    # 6. 标记为已处理
    for item in scored_items:
        duplicate_remover.add_processed_id(item.id)
    duplicate_remover.save_processed_ids()

    # 7. 格式校验
    logger.info("开始JSON格式校验...")
    try:
        for item in scored_items:
            item_dict = item.to_dict()
            json.dumps(item_dict, ensure_ascii=False)
        logger.info("✓ JSON格式校验通过")
    except json.JSONDecodeError as e:
        logger.error(f"✗ JSON格式校验失败: {e}")
        return 1

    # 8. 统计分级分布
    logger.info("新闻分级统计:")
    grade_counts = {}
    for item in scored_items:
        grade = item.grade or "C"
        grade_counts[grade] = grade_counts.get(grade, 0) + 1

    for grade in sorted(grade_counts.keys()):
        logger.info(f"  {grade}: {grade_counts[grade]} 条")

    # 9. 发布
    logger.info("开始发布到GitHub Pages...")
    if publisher.publish(scored_items):
        logger.info("发布成功！")
    else:
        logger.error("发布失败")
        return 1

    # 输出统计
    logger.info("处理完成！")
    logger.info("=" * 60)
    logger.info(f"处理统计:")
    logger.info(f"  原始新闻: {len(all_raw_items)} 条")
    logger.info(f"  去重后: {len(unique_items)} 条")
    logger.info(f"  预筛选后: {len(filtered_items)} 条")
    logger.info(f"  AI处理后: {len(processed_items)} 条")
    logger.info(f"  最终有效: {len(scored_items)} 条")

    return 0

if __name__ == "__main__":
    sys.exit(main())
