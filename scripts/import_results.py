#!/usr/bin/env python3
"""
导入手动处理的AI结果并完成发布流程
"""
import sys
import os
import argparse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.processors.ai_processor import ManualProcessor
from src.processors.duplicate import DuplicateRemover
from src.publishers.factory import PublisherFactory
from src.utils.common import setup_logger, save_json, load_json
from src.models.news import RawNewsItem
import json
from datetime import datetime
from src.config.settings import SNAPSHOT_DIR, settings

logger = setup_logger("import_results")

def main():
    parser = argparse.ArgumentParser(description='导入手动处理的AI结果并完成发布流程')
    parser.add_argument('--snapshot-id', required=True, help='快照ID，用于加载原始条目快照')
    parser.add_argument('--result-file', default='_ai_result.json', help='AI处理结果JSON文件路径 (默认: _ai_result.json)')
    parser.add_argument('--dry-run', action='store_true', help='仅加载并验证数据，不发布')
    args = parser.parse_args()

    logger.info("开始导入AI处理结果并完成发布流程...")

    # 1. 加载快照数据
    snapshot_file = os.path.join(SNAPSHOT_DIR, f"snapshot_{args.snapshot_id}.json")
    if not os.path.exists(snapshot_file):
        logger.error(f"快照文件不存在: {snapshot_file}")
        return 1

    logger.info(f"加载快照: {snapshot_file}")
    snapshot = load_json(snapshot_file)
    snapshot_items = snapshot.get("items", [])

    # 反序列化为RawNewsItem对象
    filtered_items = []
    for item_dict in snapshot_items:
        try:
            item = RawNewsItem(
                url=item_dict["url"],
                title=item_dict["title"],
                content=item_dict["content"],
                source=item_dict["source"],
                published_at=datetime.fromisoformat(item_dict["published_at"])
            )
            filtered_items.append(item)
        except Exception as e:
            logger.warning(f"跳过无效快照条目: {e}")

    logger.info(f"从快照加载到 {len(filtered_items)} 条原始新闻")

    if args.dry_run:
        logger.info("Dry run 模式，加载完成后退出")
        return 0

    # 2. 加载AI处理结果
    result_file = args.result_file
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