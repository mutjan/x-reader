#!/usr/bin/env python3
"""
继续处理已完成AI处理的新闻
支持两种模式：
1. 基础处理完成后加载基础结果，进行聚合和打分
2. 打分完成后加载打分结果，直接发布
"""
import sys
import os
import argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.fetchers.factory import FetcherFactory
from src.processors.filter import NewsFilter
from src.processors.duplicate import DuplicateRemover
from src.processors.ai_processor import ManualProcessor, AIScorer
from src.publishers.factory import PublisherFactory
from src.utils.common import setup_logger, load_json
from src.config.settings import AI_RESULT_FILE, SCORING_RESULT_FILE
import json

logger = setup_logger("continue_process")

def main():
    parser = argparse.ArgumentParser(description='继续处理新闻流程')
    parser.add_argument('--stage', type=str, default='scoring',
                       choices=['scoring', 'publish'],
                       help='处理阶段: scoring(加载基础处理结果，进行聚合和打分), publish(加载打分结果，直接发布)')
    parser.add_argument('--base-result', type=str, default=AI_RESULT_FILE,
                       help='基础处理结果文件路径')
    parser.add_argument('--scoring-result', type=str, default=SCORING_RESULT_FILE,
                       help='打分结果文件路径')
    parser.add_argument('--time-window', type=int, default=24,
                       help='获取最近多少小时内的新闻')
    args = parser.parse_args()

    # 1. 初始化组件
    duplicate_remover = DuplicateRemover()
    news_filter = NewsFilter()
    ai_processor = ManualProcessor()
    ai_scorer = AIScorer()
    publisher = PublisherFactory.get_publisher("github_pages")

    if args.stage == 'scoring':
        # 阶段1：加载基础处理结果，进行聚合和打分
        # 2. 重新获取和预处理数据（和之前一样的流程）
        logger.info("重新获取和预处理数据...")
        fetchers = FetcherFactory.get_all_fetchers()

        all_raw_items = []
        for fetcher in fetchers:
            logger.info(f"获取 {fetcher.source_name} 新闻...")
            items = fetcher.fetch(time_window_hours=args.time_window)
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

        # 3. 加载AI基础处理结果
        ai_result_file = args.base_result
        if not os.path.exists(ai_result_file):
            logger.error(f"AI基础结果文件 {ai_result_file} 不存在")
            return 1

        logger.info(f"加载AI基础处理结果: {ai_result_file}")
        processed_items = ai_processor.load_manual_result(ai_result_file, filtered_items)

        if not processed_items:
            logger.warning("没有有效的处理结果")
            return 0

        # 4. 处理后去重和合并
        logger.info("处理后去重和新闻聚合...")
        processed_items = duplicate_remover.deduplicate_processed(processed_items)
        processed_items = duplicate_remover.merge_similar_news(processed_items)

        if not processed_items:
            logger.warning("去重合并后没有剩余新闻")
            return 0

        # 5. 加载打分结果
        scoring_result_file = args.scoring_result
        if not os.path.exists(scoring_result_file):
            # 生成分打提示词
            logger.info(f"生成分打提示词...")
            ai_scorer.score_batch(processed_items)
            logger.info(f"请将打分结果保存为 {scoring_result_file} 后重新运行，使用 --stage publish 参数")
            return 0

        logger.info(f"加载AI打分结果: {scoring_result_file}")
        scored_items = ai_scorer.load_manual_scoring_result(scoring_result_file, processed_items)

        if not scored_items:
            logger.warning("没有有效的打分结果")
            return 0

    else:  # publish 阶段
        # 直接加载打分结果发布
        scoring_result_file = args.scoring_result
        if not os.path.exists(scoring_result_file):
            logger.error(f"打分结果文件 {scoring_result_file} 不存在")
            return 1

        logger.info(f"加载AI打分结果: {scoring_result_file}")

        # 需要重新获取原始数据来重建processed_items
        logger.info("重新获取原始数据...")
        fetchers = FetcherFactory.get_all_fetchers()
        all_raw_items = []
        for fetcher in fetchers:
            items = fetcher.fetch(time_window_hours=args.time_window)
            all_raw_items.extend(items)

        unique_items = duplicate_remover.deduplicate_raw(all_raw_items)
        filtered_items = news_filter.filter_news(unique_items, min_score=10)

        # 先加载基础处理结果
        base_result_file = args.base_result
        if not os.path.exists(base_result_file):
            logger.error(f"基础结果文件 {base_result_file} 不存在")
            return 1
        processed_items = ai_processor.load_manual_result(base_result_file, filtered_items)
        processed_items = duplicate_remover.deduplicate_processed(processed_items)
        processed_items = duplicate_remover.merge_similar_news(processed_items)

        # 加载打分结果
        scored_items = ai_scorer.load_manual_scoring_result(scoring_result_file, processed_items)

        if not scored_items:
            logger.warning("没有有效的打分结果")
            return 0

    logger.info(f"最终得到 {len(scored_items)} 条有效新闻")

    # 标记为已处理
    for item in scored_items:
        duplicate_remover.add_processed_id(item.id)
    duplicate_remover.save_processed_ids()

    # 格式校验
    logger.info("开始JSON格式校验...")
    try:
        for item in scored_items:
            item_dict = item.to_dict()
            json.dumps(item_dict, ensure_ascii=False)
        logger.info("✓ JSON格式校验通过")
    except json.JSONDecodeError as e:
        logger.error(f"✗ JSON格式校验失败: {e}")
        return 1

    # 发布
    logger.info("开始发布到GitHub Pages...")
    if publisher.publish(scored_items):
        logger.info("发布成功！")
    else:
        logger.error("发布失败")
        return 1

    # 输出统计
    logger.info("处理完成！")
    logger.info(f"  原始新闻: {len(all_raw_items)} 条")
    logger.info(f"  预筛选后: {len(filtered_items)} 条")
    if args.stage == 'scoring':
        logger.info(f"  AI基础处理后: {len(processed_items)} 条")
        logger.info(f"  去重合并后: {len(processed_items)} 条")
    logger.info(f"  AI打分后: {len(scored_items)} 条")

    return 0

if __name__ == "__main__":
    sys.exit(main())
