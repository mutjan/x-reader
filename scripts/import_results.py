#!/usr/bin/env python3
"""
导入手动处理的AI结果并完成发布流程
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.processors.ai_processor import ManualProcessor
from src.fetchers.factory import FetcherFactory
from src.processors.filter import NewsFilter
from src.processors.duplicate import DuplicateRemover
from src.publishers.factory import PublisherFactory
from src.utils.common import setup_logger, save_json, load_json
import json
from datetime import datetime

logger = setup_logger("import_results")

def main():
    logger.info("开始导入AI处理结果并完成发布流程...")

    # 1. 获取和预处理新闻（与之前相同的步骤，确保数据一致）
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
    logger.info(f"预筛选后剩余 {len(filtered_items)} 条")

    # 2. 加载AI处理结果
    result_file = "_ai_result.json"
    if not os.path.exists(result_file):
        logger.error(f"结果文件 {result_file} 不存在")
        return 1

    ai_processor = ManualProcessor()
    processed_items = ai_processor.load_manual_result(result_file, filtered_items)
    logger.info(f"AI处理完成，得到 {len(processed_items)} 条有效新闻")

    if not processed_items:
        logger.warning("没有有效新闻，退出")
        return 0

    # 3. 处理后去重和合并
    logger.info("处理后去重...")
    processed_items = duplicate_remover.deduplicate_processed(processed_items)
    processed_items = duplicate_remover.merge_similar_news(processed_items)

    if not processed_items:
        logger.warning("去重合并后没有剩余新闻")
        return 0

    logger.info(f"最终得到 {len(processed_items)} 条有效新闻")

    # 4. 标记为已处理
    for item in processed_items:
        duplicate_remover.add_processed_id(item.id)
    duplicate_remover.save_processed_ids()

    # 5. 最终格式校验
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

    # 6. 发布到GitHub Pages
    logger.info("开始发布到GitHub Pages...")
    publisher = PublisherFactory.get_publisher("github_pages")
    if publisher:
        if publisher.publish(processed_items):
            logger.info("发布成功！")
        else:
            logger.error("发布失败")
            return 1

    # 7. 记录工作日志
    work_log_file = ".work_log.json"
    work_log = load_json(work_log_file, {"entries": [], "last_execution": ""})

    # 统计各级别数量
    level_counts = {}
    for item in processed_items:
        level = item.grade
        level_counts[level] = level_counts.get(level, 0) + 1

    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "sources": "all",
        "total_fetched": len(all_raw_items),
        "new_items": len(unique_items),
        "filtered": len(filtered_items),
        "ai_processed": len([item for item in load_json(result_file, []) if item.get("grade", "C") != "C"]),
        "added": len(processed_items),
        "updated": 0,
        "total_news": sum(level_counts.values()),
        "level_counts": level_counts,
        "github_pushed": True,
        "errors": [],
        "notes": []
    }

    work_log["entries"].append(log_entry)
    work_log["last_execution"] = log_entry["timestamp"]
    save_json(work_log, work_log_file)

    # 8. 输出统计信息
    logger.info("=" * 60)
    logger.info("处理完成！")
    logger.info("=" * 60)
    logger.info(f"处理统计:")
    logger.info(f"  原始新闻: {len(all_raw_items)} 条")
    logger.info(f"  去重后: {len(unique_items)} 条")
    logger.info(f"  预筛选后: {len(filtered_items)} 条")
    logger.info(f"  AI处理后有效新闻: {len(processed_items)} 条")
    logger.info(f"  级别分布: {level_counts}")

    # 保存结果到本地文件
    output_file = "news_data_latest.json"
    news_data = {}
    today = datetime.now().strftime("%Y-%m-%d")
    news_data[today] = [item.to_dict() for item in processed_items]
    save_json(news_data, output_file)
    logger.info(f"结果已保存到: {output_file}")

    return 0

if __name__ == "__main__":
    sys.exit(main())