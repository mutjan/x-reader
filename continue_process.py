#!/usr/bin/env python3
"""
继续处理已完成AI处理的新闻
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.fetchers.factory import FetcherFactory
from src.processors.filter import NewsFilter
from src.processors.duplicate import DuplicateRemover
from src.processors.ai_processor import ManualProcessor
from src.publishers.factory import PublisherFactory
from src.utils.common import setup_logger, load_json
import json

logger = setup_logger("continue_process")

def main():
    # 1. 初始化组件
    duplicate_remover = DuplicateRemover()
    news_filter = NewsFilter()
    ai_processor = ManualProcessor()
    publisher = PublisherFactory.get_publisher("github_pages")

    # 2. 重新获取和预处理数据（和之前一样的流程）
    logger.info("重新获取和预处理数据...")
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

    # 如果没有待处理内容，提前退出
    if len(filtered_items) == 0:
        logger.info("没有需要处理的新闻，提前退出")
        return 0

    # 3. 加载AI处理结果
    ai_result_file = "_ai_result.json"
    if not os.path.exists(ai_result_file):
        logger.error(f"AI结果文件 {ai_result_file} 不存在")
        return 1

    logger.info(f"加载AI处理结果: {ai_result_file}")
    processed_items = ai_processor.load_manual_result(ai_result_file, filtered_items)

    if not processed_items:
        logger.warning("没有有效的处理结果")
        return 0

    # 4. 后续流程和main.py一样
    logger.info("处理后去重和合并...")
    processed_items = duplicate_remover.deduplicate_processed(processed_items)
    processed_items = duplicate_remover.merge_similar_news(processed_items)

    if not processed_items:
        logger.warning("去重合并后没有剩余新闻")
        return 0

    logger.info(f"最终得到 {len(processed_items)} 条有效新闻")

    # 标记为已处理
    for item in processed_items:
        duplicate_remover.add_processed_id(item.id)
    duplicate_remover.save_processed_ids()

    # 格式校验
    logger.info("开始JSON格式校验...")
    try:
        for item in processed_items:
            item_dict = item.to_dict()
            json.dumps(item_dict, ensure_ascii=False)
        logger.info("✓ JSON格式校验通过")
    except json.JSONDecodeError as e:
        logger.error(f"✗ JSON格式校验失败: {e}")
        return 1

    # 发布
    logger.info("开始发布到GitHub Pages...")
    if publisher.publish(processed_items):
        logger.info("发布成功！")
    else:
        logger.error("发布失败")
        return 1

    # 输出统计
    logger.info("处理完成！")
    logger.info(f"  原始新闻: {len(all_raw_items)} 条")
    logger.info(f"  预筛选后: {len(filtered_items)} 条")
    logger.info(f"  AI处理后: {len(processed_items)} 条")

    return 0

if __name__ == "__main__":
    sys.exit(main())
