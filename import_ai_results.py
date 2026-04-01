#!/usr/bin/env python3
"""
导入AI处理结果脚本
用于导入手动处理的AI基础结果和打分结果
"""
import sys
import os
import json
from typing import List, Dict, Any

# 添加src目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.processors.ai_processor import ManualProcessor, AIScorer
from src.models.news import RawNewsItem, ProcessedNewsItem
from src.utils.common import load_json, save_json, setup_logger
from src.processors.duplicate import DuplicateRemover
from src.publishers.factory import PublisherFactory
from src.config.settings import SNAPSHOT_DIR, TEMP_DIR

logger = setup_logger("import_ai_results")

def load_snapshot(snapshot_id: str) -> Dict[str, Any]:
    """加载快照文件"""
    snapshot_file = os.path.join(SNAPSHOT_DIR, f"snapshot_{snapshot_id}.json")
    if not os.path.exists(snapshot_file):
        logger.error(f"快照文件不存在: {snapshot_file}")
        return None

    return load_json(snapshot_file)

def snapshot_to_raw_items(snapshot: Dict[str, Any]) -> List[RawNewsItem]:
    """将快照中的条目转换为RawNewsItem对象"""
    from datetime import datetime

    raw_items = []
    for item_dict in snapshot.get("items", []):
        try:
            published_at = datetime.fromisoformat(item_dict["published_at"])
            raw_item = RawNewsItem(
                title=item_dict["title"],
                content=item_dict["content"],
                source=item_dict["source"],
                url=item_dict["url"],
                published_at=published_at
            )
            raw_items.append(raw_item)
        except Exception as e:
            logger.warning(f"转换快照条目失败: {e}")

    return raw_items

def import_base_results(snapshot_id: str, result_file: str) -> bool:
    """导入基础处理结果"""
    # 加载快照
    snapshot = load_snapshot(snapshot_id)
    if not snapshot:
        return False

    # 加载原始条目
    raw_items = snapshot_to_raw_items(snapshot)
    if not raw_items:
        logger.error("快照中没有有效条目")
        return False

    # 加载AI处理结果
    processor = ManualProcessor()
    processed_items = processor.load_manual_result(result_file, raw_items)
    if not processed_items:
        logger.error("加载AI处理结果失败")
        return False

    # 保存结果到快照并生成分打提示词
    if processor.save_base_results_to_snapshot(snapshot_id, processed_items):
        logger.info(f"基础结果导入成功，共处理 {len(processed_items)} 条新闻")
        logger.info(f"打分提示词已生成: {TEMP_DIR}/scoring_prompt_{snapshot_id}.txt")
        return True
    else:
        logger.error("保存基础结果到快照失败")
        return False

def import_scoring_results(snapshot_id: str, result_file: str, no_publish: bool = False) -> bool:
    """导入打分结果并完成后续流程"""
    # 加载快照
    snapshot = load_snapshot(snapshot_id)
    if not snapshot:
        return False

    # 加载基础处理结果
    processor = ManualProcessor()
    processed_items = processor.load_base_results_from_snapshot(snapshot_id)
    if not processed_items:
        logger.error("快照中没有基础处理结果")
        return False

    # 加载打分结果
    scorer = AIScorer()
    scored_items = scorer.load_manual_scoring_result(result_file, processed_items)
    if not scored_items:
        logger.error("加载打分结果失败或没有有效新闻")
        return False

    logger.info(f"打分结果导入成功，共 {len(scored_items)} 条有效新闻")

    # 后续流程：去重、标记已处理、发布
    duplicate_remover = DuplicateRemover()

    # 去重
    logger.info("处理后去重...")
    scored_items = duplicate_remover.deduplicate_processed(scored_items)

    if not scored_items:
        logger.warning("去重后没有剩余新闻")
        return False

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
        return False

    # 发布
    if not no_publish:
        publisher = PublisherFactory.get_publisher("github_pages")
        if publisher:
            logger.info("开始发布到GitHub Pages...")
            if publisher.publish(scored_items):
                logger.info("发布成功！")
            else:
                logger.error("发布失败")
                return False

    # 保存最终结果
    output_file = os.path.join(TEMP_DIR, f"final_news_{snapshot_id}.json")
    save_json([item.to_dict() for item in scored_items], output_file)
    logger.info(f"最终结果已保存到: {output_file}")

    # 输出统计
    logger.info("处理完成！")
    logger.info("=" * 60)
    logger.info(f"处理统计:")
    logger.info(f"  原始条目: {len(snapshot.get('items', []))} 条")
    logger.info(f"  基础处理后: {len(processed_items)} 条")
    logger.info(f"  打分后有效: {len(scored_items)} 条")

    return True

def main():
    import argparse

    parser = argparse.ArgumentParser(description='导入AI处理结果')
    parser.add_argument('snapshot_id', help='快照ID（8位哈希）')
    parser.add_argument('--base-result', help='基础处理结果JSON文件路径')
    parser.add_argument('--scoring-result', help='打分结果JSON文件路径')
    parser.add_argument('--no-publish', action='store_true', help='不发布到GitHub Pages')

    args = parser.parse_args()

    if args.base_result:
        # 导入基础结果
        success = import_base_results(args.snapshot_id, args.base_result)
        return 0 if success else 1
    elif args.scoring_result:
        # 导入打分结果
        success = import_scoring_results(args.snapshot_id, args.scoring_result, args.no_publish)
        return 0 if success else 1
    else:
        logger.error("必须指定 --base-result 或 --scoring-result 参数")
        parser.print_help()
        return 1

if __name__ == "__main__":
    sys.exit(main())
