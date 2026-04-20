#!/usr/bin/env python3
"""
手动AI处理脚本
批量处理所有预筛选后的新闻
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.processors.ai_processor import ManualProcessor
from src.fetchers.factory import FetcherFactory
from src.processors.filter import NewsFilter
from src.processors.duplicate import DuplicateRemover
from src.utils.common import setup_logger, save_json, load_json
import json

logger = setup_logger("manual_process")

def main():
    logger.info("开始手动处理新闻...")

    # 1. 获取和预处理新闻
    logger.info("获取新闻数据...")
    fetchers = FetcherFactory.get_all_fetchers()

    all_raw_items = []
    for fetcher in fetchers:
        items = fetcher.fetch(time_window_hours=24)
        all_raw_items.extend(items)

    logger.info(f"总共获取到 {len(all_raw_items)} 条原始新闻")

    # 去重
    duplicate_remover = DuplicateRemover()
    unique_items = duplicate_remover.deduplicate_raw(all_raw_items)
    logger.info(f"去重后剩余 {len(unique_items)} 条")

    # 预筛选
    news_filter = NewsFilter()
    filtered_items = news_filter.filter_news(unique_items, min_score=10)
    logger.info(f"预筛选后剩余 {len(filtered_items)} 条需要处理")

    # 2. 生成完整的提示词
    ai_processor = ManualProcessor()
    prompt = ai_processor.build_prompt(filtered_items)

    prompt_file = "full_ai_prompt.txt"
    with open(prompt_file, 'w', encoding='utf-8') as f:
        f.write(prompt)

    logger.info(f"完整提示词已生成到: {prompt_file}")
    logger.info(f"共 {len(filtered_items)} 条新闻需要处理")

    # 3. 等待用户处理
    logger.info("请处理完提示词后，将结果保存为 full_ai_result.json，然后按回车继续...")
    input()

    # 4. 处理结果
    result_file = "full_ai_result.json"
    if not os.path.exists(result_file):
        logger.error(f"结果文件 {result_file} 不存在")
        return 1

    processed_items = ai_processor.load_manual_result(result_file, filtered_items)
    logger.info(f"AI处理完成，得到 {len(processed_items)} 条有效新闻")

    # 5. 保存中间结果
    save_json([item.to_dict() for item in processed_items], "_processed_items.json")
    logger.info("处理结果已保存到 _processed_items.json")

    return 0

if __name__ == "__main__":
    sys.exit(main())