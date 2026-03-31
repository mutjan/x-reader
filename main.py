#!/usr/bin/env python3
"""
x-reader 主程序入口 v1.0.0
模块化重构版本
"""
import argparse
import sys
import os
from typing import List

# 添加src目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.fetchers.factory import FetcherFactory
from src.processors.filter import NewsFilter
from src.processors.duplicate import DuplicateRemover
from src.processors.ai_processor import ManualProcessor
from src.publishers.factory import PublisherFactory
from src.utils.common import setup_logger, save_json
import json
from src.config.settings import DEFAULT_BATCH_SIZE

logger = setup_logger("main")

def main():
    parser = argparse.ArgumentParser(description='x-reader 新闻聚合工具')
    parser.add_argument('--source', type=str, default='all',
                       choices=['twitter', 'inoreader', 'all'],
                       help='数据源类型 (默认: all)')
    parser.add_argument('--time-window', type=int, default=2,
                       help='获取最近多少小时内的新闻 (默认: 2，增量更新)')
    parser.add_argument('--full', action='store_true',
                       help='全量更新模式，获取最近24小时内的新闻')
    parser.add_argument('--min-score', type=int, default=10,
                       help='预筛选最低得分 (默认: 10)')
    parser.add_argument('--batch-size', type=int, default=DEFAULT_BATCH_SIZE,
                       help=f'AI处理批量大小 (默认: {DEFAULT_BATCH_SIZE})')
    parser.add_argument('--no-publish', action='store_true',
                       help='不发布到GitHub Pages')
    parser.add_argument('--test', action='store_true',
                       help='测试模式，只获取数据不处理')

    args = parser.parse_args()

    # 处理全量更新模式
    if args.full:
        args.time_window = 24
        logger.info("全量更新模式，抓取最近24小时新闻")

    logger.info("=" * 60)
    logger.info("x-reader 新闻聚合工具 v1.0.0")
    logger.info("=" * 60)

    # 1. 初始化组件
    logger.info("初始化组件...")
    duplicate_remover = DuplicateRemover()
    news_filter = NewsFilter()
    ai_processor = ManualProcessor()  # 默认使用手动处理模式
    publisher = PublisherFactory.get_publisher("github_pages")

    # 2. 获取数据源
    logger.info(f"获取数据源: {args.source}")
    if args.source == 'all':
        fetchers = FetcherFactory.get_all_fetchers()
    else:
        fetcher = FetcherFactory.get_fetcher(args.source)
        if not fetcher:
            logger.error(f"不支持的数据源类型: {args.source}")
            return 1
        fetchers = [fetcher]

    # 3. 测试数据源连接
    logger.info("测试数据源连接...")
    for fetcher in fetchers:
        if not fetcher.test_connection():
            logger.error(f"数据源 {fetcher.source_name} 连接失败")
            return 1
        logger.info(f"✓ {fetcher.source_name} 连接正常")

    # 4. 获取新闻
    all_raw_items = []
    for fetcher in fetchers:
        logger.info(f"开始获取 {fetcher.source_name} 新闻...")
        items = fetcher.fetch(time_window_hours=args.time_window)
        all_raw_items.extend(items)
        logger.info(f"获取到 {len(items)} 条 {fetcher.source_name} 新闻")

    if not all_raw_items:
        logger.warning("没有获取到任何新闻")
        return 0

    logger.info(f"总共获取到 {len(all_raw_items)} 条原始新闻")

    if args.test:
        logger.info("测试模式，退出")
        return 0

    # 5. 去重
    logger.info("开始去重...")
    unique_items = duplicate_remover.deduplicate_raw(all_raw_items)
    if not unique_items:
        logger.warning("去重后没有剩余新闻")
        return 0

    # 6. 预筛选
    logger.info("开始预筛选...")
    filtered_items = news_filter.filter_news(unique_items, min_score=args.min_score)
    if not filtered_items:
        logger.warning("预筛选后没有剩余新闻")
        return 0

    # 7. AI处理
    logger.info(f"开始AI处理，共 {len(filtered_items)} 条新闻")

    # 分批处理
    processed_items = []
    for i in range(0, len(filtered_items), args.batch_size):
        batch = filtered_items[i:i+args.batch_size]
        logger.info(f"处理批次 {i//args.batch_size + 1}/{(len(filtered_items) + args.batch_size - 1)//args.batch_size} "
                   f"({len(batch)}条)")
        batch_processed = ai_processor.process_batch(batch)
        processed_items.extend(batch_processed)

    if not processed_items:
        logger.warning("AI处理后没有剩余新闻")
        return 0

    # 8. 处理后去重和合并
    logger.info("处理后去重...")
    processed_items = duplicate_remover.deduplicate_processed(processed_items)
    processed_items = duplicate_remover.merge_similar_news(processed_items)

    if not processed_items:
        logger.warning("去重合并后没有剩余新闻")
        return 0

    logger.info(f"最终得到 {len(processed_items)} 条有效新闻")

    # 9. 标记为已处理
    for item in processed_items:
        duplicate_remover.add_processed_id(item.id)
    duplicate_remover.save_processed_ids()

    # 10. 最终格式校验
    logger.info("开始JSON格式校验...")
    try:
        # 校验所有新闻项是否可以正常序列化
        for item in processed_items:
            item_dict = item.to_dict()
            json.dumps(item_dict, ensure_ascii=False)
        logger.info("✓ JSON格式校验通过")
    except json.JSONDecodeError as e:
        logger.error(f"✗ JSON格式校验失败: {e}")
        return 1

    # 11. 发布
    if not args.no_publish and publisher:
        logger.info("开始发布到GitHub Pages...")
        if publisher.publish(processed_items):
            logger.info("发布成功！")
        else:
            logger.error("发布失败")
            return 1

    logger.info("处理完成！")
    logger.info("=" * 60)

    # 输出统计信息
    logger.info(f"处理统计:")
    logger.info(f"  原始新闻: {len(all_raw_items)} 条")
    logger.info(f"  去重后: {len(unique_items)} 条")
    logger.info(f"  预筛选后: {len(filtered_items)} 条")
    logger.info(f"  AI处理后: {len(processed_items)} 条")

    return 0

if __name__ == "__main__":
    sys.exit(main())
