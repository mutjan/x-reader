#!/usr/bin/env python3
"""
导入手动处理的AI结果并完成发布流程
"""
import sys
import os
import argparse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.processors.ai_processor import ManualProcessor, AIScorer, EntityProcessor
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
    parser.add_argument('--base-result-file', default='_ai_base_result.json', help='基础处理结果JSON文件路径 (默认: _ai_base_result.json)')
    parser.add_argument('--entity-result-file', help='实体识别结果JSON文件路径，提供则导入实体识别结果')
    parser.add_argument('--scoring-result-file', help='打分结果JSON文件路径，提供则执行打分步骤')
    parser.add_argument('--continue', action='store_true', dest='continue_process', help='从快照中已有的基础处理结果继续，不需要重新导入基础结果')
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

    # 初始化公共组件
    duplicate_remover = DuplicateRemover()
    ai_processor = ManualProcessor()
    entity_processor = EntityProcessor()
    processed_items = []

    if args.dry_run:
        logger.info("Dry run 模式，加载完成后退出")
        return 0

    # 2. 处理实体识别结果（如果提供）
    if args.entity_result_file:
        if not os.path.exists(args.entity_result_file):
            logger.error(f"实体识别结果文件 {args.entity_result_file} 不存在")
            return 1

        entity_results = entity_processor.load_manual_result(args.entity_result_file, filtered_items)
        logger.info(f"实体识别完成，得到 {len(entity_results)} 条新闻的实体")

        if entity_results:
            # 保存实体识别结果到快照
            ai_processor.save_entity_results_to_snapshot(args.snapshot_id, entity_results)
            logger.info("实体识别结果已保存到快照")

    # 3. 处理基础处理结果
    if not args.continue_process:
        # 导入新的基础处理结果
        base_result_file = args.base_result_file
        if not os.path.exists(base_result_file):
            logger.error(f"基础处理结果文件 {base_result_file} 不存在")
            return 1

        processed_items = ai_processor.load_manual_result(base_result_file, filtered_items)
        logger.info(f"基础处理完成，得到 {len(processed_items)} 条有效新闻")

        if not processed_items:
            # 尝试从快照的items创建ProcessedNewsItem对象
            from src.models.news import ProcessedNewsItem
            processed_items = []
            for item_dict in snapshot_items:
                try:
                    item = ProcessedNewsItem(
                        id=item_dict.get("id", ""),
                        original_title=item_dict["title"],
                        original_content=item_dict["content"],
                        source=item_dict["source"],
                        url=item_dict["url"],
                        published_at=datetime.fromisoformat(item_dict["published_at"]),
                        chinese_title="",
                        summary="",
                        news_type="",
                        extension=""
                    )
                    processed_items.append(item)
                except Exception as e:
                    logger.warning(f"跳过无效快照条目: {e}")
            logger.info(f"从快照创建了 {len(processed_items)} 条ProcessedNewsItem对象")

        if not processed_items:
            logger.warning("没有有效新闻，退出")
            return 0

        # 保存基础处理结果到快照（会自动填充已有的实体结果）
        ai_processor.save_base_results_to_snapshot(args.snapshot_id, processed_items)

        # 如果没有提供打分结果文件，流程在此结束，等待用户处理打分
        if not args.scoring_result_file:
            logger.info("已完成基础处理并保存到快照，请处理生成的打分提示词后再次运行脚本并指定 --scoring-result-file 参数")
            return 0
    else:
        # 从快照加载已有的基础处理结果
        processed_items = ai_processor.load_base_results_from_snapshot(args.snapshot_id)
        if not processed_items:
            logger.error("快照中没有可继续处理的基础结果，请先运行不带 --continue 参数的命令导入基础结果")
            return 1
        logger.info(f"从快照加载到 {len(processed_items)} 条已完成基础处理的新闻")

        # 如果提供了实体识别结果文件，先导入实体结果
        if args.entity_result_file:
            if not os.path.exists(args.entity_result_file):
                logger.error(f"实体识别结果文件 {args.entity_result_file} 不存在")
                return 1
            entity_results = entity_processor.load_manual_result(args.entity_result_file, filtered_items)
            logger.info(f"实体识别完成，得到 {len(entity_results)} 条新闻的实体")
            if entity_results:
                ai_processor.save_entity_results_to_snapshot(args.snapshot_id, entity_results)
                logger.info("实体识别结果已保存到快照")

        # 加载实体识别结果并填充（无论是之前导入还是刚导入）
        entity_results = ai_processor.load_entity_results_from_snapshot(args.snapshot_id)
        if entity_results:
            logger.info("从快照加载到实体识别结果，正在填充...")
            for item in processed_items:
                if item.url in entity_results:
                    item.entities = entity_results[item.url]
            logger.info(f"已为 {len([item for item in processed_items if item.entities])} 条新闻填充实体")

    # 3. 处理打分结果（如果提供）
    if args.scoring_result_file:
        if not os.path.exists(args.scoring_result_file):
            logger.error(f"打分结果文件 {args.scoring_result_file} 不存在")
            return 1

        scorer = AIScorer()
        processed_items = scorer.load_manual_scoring_result(args.scoring_result_file, processed_items)
        logger.info(f"打分完成，得到 {len(processed_items)} 条有效新闻（已过滤C级）")

        if not processed_items:
            logger.warning("打分后没有剩余有效新闻，退出")
            return 0

    # 4. 处理后去重
    logger.info("处理后去重...")
    processed_items = duplicate_remover.deduplicate_processed(processed_items)

    if not processed_items:
        logger.warning("去重后没有剩余新闻")
        return 0

    logger.info(f"最终得到 {len(processed_items)} 条有效新闻")

    # 5. 标记为已处理
    for item in processed_items:
        duplicate_remover.add_processed_id(item.id)
    duplicate_remover.save_processed_ids()

    # 6. 最终格式校验
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

    # 7. 发布到GitHub Pages（只有完成打分步骤才发布）
    if args.scoring_result_file:
        logger.info("开始发布到GitHub Pages...")
        publisher = PublisherFactory.get_publisher("github_pages")
        if publisher:
            if publisher.publish(processed_items):
                logger.info("发布成功！")
            else:
                logger.error("发布失败")
                return 1

    # 8. 记录工作日志
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
        "total_fetched": len(filtered_items),
        "new_items": len(filtered_items),
        "filtered": len(filtered_items),
        "ai_processed": len(processed_items),
        "added": len(processed_items),
        "updated": 0,
        "total_news": sum(level_counts.values()),
        "level_counts": level_counts,
        "github_pushed": args.scoring_result_file is not None,
        "errors": [],
        "notes": []
    }

    work_log["entries"].append(log_entry)
    work_log["last_execution"] = log_entry["timestamp"]
    save_json(work_log, work_log_file)

    # 9. 输出统计信息
    logger.info("=" * 60)
    logger.info("处理完成！")
    logger.info("=" * 60)
    logger.info(f"处理统计:")
    logger.info(f"  原始新闻: {len(filtered_items)} 条")
    logger.info(f"  有效处理结果: {len(processed_items)} 条")
    if args.scoring_result_file:
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