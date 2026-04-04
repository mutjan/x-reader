#!/usr/bin/env python3
"""
导入Agent事件分组复查结果
两步AI工作流的第二步：加载AI复查结果并应用到event_groups.json
"""
import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.processors.event_reviewer import EventGroupReviewer, load_review_corrections
from src.processors.event_grouper import EventGrouper, Event
from src.utils.common import setup_logger, save_json, load_json
from src.models.news import ProcessedNewsItem
from src.config.settings import EVENT_GROUPS_FILE, DATA_DIR, DATA_FILE
from datetime import datetime

logger = setup_logger("import_review_results")


def main():
    parser = argparse.ArgumentParser(description='导入Agent事件分组复查结果')
    parser.add_argument('--result-file', default='_event_grouping_review_result.json',
                        help='AI复查结果JSON文件路径 (默认: _event_grouping_review_result.json)')
    parser.add_argument('--batch-id', default=None,
                        help='批次标识 (默认: 根据时间自动生成)')
    parser.add_argument('--dry-run', action='store_true',
                        help='仅显示将应用的修正，不实际修改文件')
    args = parser.parse_args()

    logger.info("开始导入Agent复查结果...")

    # 1. 加载复查结果
    corrections = load_review_corrections(args.result_file)
    if not corrections:
        logger.info("复查结果中无修正项，退出")
        return 0

    logger.info(f"加载到 {len(corrections)} 条修正建议")
    for corr in corrections:
        logger.info(f"  - 新闻 {corr.get('news_id', '?')[:8]}...: "
                     f"{corr.get('current_event_id', 'null')} -> "
                     f"{corr.get('suggested_event_id', '?')} "
                     f"({corr.get('reason', '')})")

    if args.dry_run:
        logger.info("Dry run 模式，不修改文件")
        return 0

    # 2. 加载现有事件分组
    event_grouper = EventGrouper(entity_threshold=2, similarity_threshold=0.65)
    existing_groups = event_grouper.load_event_groups()
    if not existing_groups:
        logger.error("event_groups.json 为空或不存在")
        return 1

    # 3. 从现有分组 + 全量新闻数据重建完整 Event 对象
    news_data = load_json(DATA_FILE, {})
    news_by_id = {}

    # 展平 news_data.json（按日期分组的结构）
    if "news" in news_data:
        for date, items in news_data["news"].items():
            for item in items:
                news_by_id[item.get("id", "")] = item
    elif isinstance(news_data, dict) and "news" not in news_data:
        for date, items in news_data.items():
            for item in items:
                news_by_id[item.get("id", "")] = item

    # 将现有分组重建为 Event 对象
    events = []
    for group_dict in existing_groups:
        try:
            event_id = group_dict.get("group_id", group_dict.get("event_id", ""))
            title = group_dict.get("event_title", group_dict.get("title", "未命名事件"))
            max_grade = group_dict.get("max_grade", "B")
            max_score = group_dict.get("max_score", 0)
            entities = group_dict.get("entities", [])
            start_time = datetime.fromisoformat(group_dict.get("first_seen_at", datetime.now().isoformat()))
            end_time = datetime.fromisoformat(group_dict.get("last_seen_at", datetime.now().isoformat()))

            news_list = []
            for news_id in group_dict.get("news_ids", []):
                if news_id in news_by_id:
                    item_dict = news_by_id[news_id]
                    try:
                        news_item = ProcessedNewsItem.from_frontend_dict(item_dict)
                        news_list.append(news_item)
                    except Exception as e:
                        logger.warning(f"跳过无效新闻: {e}")

            if news_list:
                event = Event(
                    event_id=event_id,
                    title=title,
                    main_news=news_list[0],
                    news_list=news_list,
                    entities=entities,
                    max_grade=max_grade,
                    max_score=max_score,
                    start_time=start_time,
                    end_time=end_time,
                    news_count=len(news_list)
                )
                event_grouper._update_event_properties(event)
                events.append(event)

        except Exception as e:
            logger.warning(f"跳过无效事件分组: {e}")
            continue

    if not events:
        logger.error("未找到有效事件分组")
        return 1

    logger.info(f"已重建 {len(events)} 个Event对象")

    # 4. 应用修正
    reviewer = EventGroupReviewer(entity_threshold=2, review_similarity_threshold=0.55)
    batch_id = args.batch_id or datetime.now().strftime("%Y%m%d%H%M%S")
    success, audit_entry = reviewer.apply_corrections(corrections, events, batch_id=batch_id)

    if not success:
        logger.error("应用修正失败")
        return 1

    # 5. 保存修正后的 event_groups.json
    events_dict = event_grouper._events_to_dict(events)
    save_success = save_json(events_dict, EVENT_GROUPS_FILE)
    if not save_success:
        logger.error("event_groups.json 保存失败")
        return 1

    logger.info(f"已应用 {audit_entry.get('corrections_applied', 0)} 条复查修正")
    logger.info(f"event_groups.json 已更新: {EVENT_GROUPS_FILE}")
    logger.info(f"审计日志已记录: {DATA_DIR}/event_review_log.json")

    return 0


if __name__ == "__main__":
    sys.exit(main())
