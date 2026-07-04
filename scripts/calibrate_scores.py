#!/usr/bin/env python3
"""
评分校准脚本
每日离线执行，基于反馈数据校准新闻评分
"""
import sys
import os
import argparse
from datetime import datetime, timedelta
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.processors.score_calibrator import CalibrationRuleGenerator, CalibrationEngine
from src.publishers.github_pages import GitHubPagesPublisher
from src.models.news import ProcessedNewsItem
from src.utils.common import setup_logger, load_json, save_json
from src.config.settings import DATA_FILE

logger = setup_logger("calibrate_scores")

def main():
    parser = argparse.ArgumentParser(description='新闻评分校准脚本')
    parser.add_argument('--dry-run', action='store_true', help='仅生成校准报告，不实际修改数据')
    parser.add_argument('--days', type=int, default=7, help='校准最近多少天的新闻，默认7天')
    parser.add_argument('--generate-rules-only', action='store_true', help='仅生成校准规则，不执行校准')
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("新闻评分校准脚本")
    logger.info("=" * 60)

    # 1. 生成校准规则
    logger.info("\n[1/4] 生成校准规则...")
    rule_generator = CalibrationRuleGenerator()
    rules = rule_generator.generate_rules(days=30)  # 分析最近30天的反馈

    if args.generate_rules_only:
        logger.info("仅生成规则模式，退出")
        return 0

    if not rules:
        logger.info("没有有效校准规则，无需校准")
        return 0

    # 2. 加载新闻数据
    logger.info("\n[2/4] 加载新闻数据...")
    if not os.path.exists(DATA_FILE):
        logger.error(f"新闻数据文件不存在: {DATA_FILE}")
        return 1

    data = load_json(DATA_FILE, {})
    news_by_date = data.get("news", data)  # 兼容新旧格式

    # 筛选最近N天的新闻
    cutoff_date = (datetime.now() - timedelta(days=args.days)).strftime("%Y-%m-%d")
    all_news = []
    news_map = {}  # date -> index -> item

    for date in news_by_date:
        if date >= cutoff_date:
            news_list = news_by_date[date]
            news_map[date] = []
            for item_dict in news_list:
                try:
                    item = ProcessedNewsItem.from_dict(item_dict)
                    all_news.append(item)
                    news_map[date].append(item)
                except Exception as e:
                    logger.warning(f"跳过无效新闻: {e}")
                    news_map[date].append(item_dict)  # 保留原始数据

    if not all_news:
        logger.info(f"最近{args.days}天没有新闻数据，无需校准")
        return 0

    logger.info(f"加载到 {len(all_news)} 条最近{args.days}天的新闻")

    # 3. 执行校准
    logger.info("\n[3/4] 执行校准...")
    engine = CalibrationEngine()
    calibrated_items = engine.batch_calibrate(all_news)

    # 统计校准结果
    stats = {
        "total_news": len(all_news),
        "adjusted_count": 0,
        "average_adjustment": 0,
        "adjustments": []
    }

    for original, calibrated in zip(all_news, calibrated_items):
        if original.score != calibrated.score:
            stats["adjusted_count"] += 1
            adjustment = calibrated.score - original.score
            stats["average_adjustment"] += adjustment
            stats["adjustments"].append({
                "news_id": original.id,
                "title": original.chinese_title,
                "original_score": original.score,
                "original_grade": original.grade,
                "calibrated_score": calibrated.score,
                "calibrated_grade": calibrated.grade,
                "adjustment": adjustment
            })

    if stats["adjusted_count"] > 0:
        stats["average_adjustment"] /= stats["adjusted_count"]

    # 4. 生成报告
    logger.info("\n[4/4] 生成校准报告...")
    report = {
        "generated_at": datetime.now().isoformat(),
        "calibration_days": args.days,
        "rules_used": [rule.to_dict() for rule in engine.rules],
        "statistics": stats,
        "adjustment_details": stats["adjustments"]
    }

    # 保存报告
    os.makedirs("data/feedback/reports", exist_ok=True)
    report_file = f"data/feedback/reports/calibration_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    save_json(report, report_file)

    # 打印统计信息
    logger.info("\n校准统计:")
    logger.info(f"  总新闻数: {stats['total_news']}")
    logger.info(f"  调整条数: {stats['adjusted_count']}")
    if stats["adjusted_count"] > 0:
        logger.info(f"  平均调整: {stats['average_adjustment']:+.1f}分")

    # 列出调整较大的新闻
    if stats["adjustments"]:
        logger.info("\n调整幅度较大的新闻:")
        sorted_adjustments = sorted(stats["adjustments"], key=lambda x: abs(x["adjustment"]), reverse=True)
        for adj in sorted_adjustments[:5]:
            logger.info(f"  {adj['adjustment']:+3d}分 | {adj['original_grade']}→{adj['calibrated_grade']} | {adj['title'][:30]}...")

    if args.dry_run:
        logger.info("\nDry run 模式，未修改实际数据")
        logger.info(f"校准报告已保存到: {report_file}")
        return 0

    # 5. 保存校准后的数据
    logger.info("\n保存校准后的数据...")

    # 构建校准后的新闻数据
    calibrated_news_by_date = {}
    calibrated_index = 0
    for date in news_map:
        calibrated_news_by_date[date] = []
        for item in news_map[date]:
            if isinstance(item, ProcessedNewsItem):
                # 用校准后的替换
                calibrated_item = calibrated_items[calibrated_index]
                calibrated_news_by_date[date].append(calibrated_item.to_frontend_dict())
                calibrated_index += 1
            else:
                # 保留无法解析的原始数据
                calibrated_news_by_date[date].append(item)

    # 保存回原文件结构
    if "events" in data:
        # 新格式
        output_data = {
            "news": calibrated_news_by_date,
            "events": data.get("events", []),
            "last_updated": datetime.now().isoformat(),
            "total_news": sum(len(items) for items in calibrated_news_by_date.values()),
            "total_events": len(data.get("events", []))
        }
    else:
        # 旧格式
        output_data = calibrated_news_by_date

    # 备份原文件
    backup_file = f"{DATA_FILE}.bak.calibration_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    os.rename(DATA_FILE, backup_file)
    logger.info(f"原文件已备份到: {backup_file}")

    # 保存新数据
    save_json(output_data, DATA_FILE)
    logger.info(f"校准后的数据已保存到: {DATA_FILE}")

    # 6. 重新发布到GitHub Pages
    logger.info("\n重新发布到GitHub Pages...")
    publisher = GitHubPagesPublisher()
    # 直接推送更新，不需要重新处理
    if publisher._push_to_github(f"自动校准新闻评分: 调整{stats['adjusted_count']}条新闻"):
        logger.info("发布成功！")
    else:
        logger.error("发布失败")
        return 1

    logger.info("\n校准完成！")
    return 0

if __name__ == "__main__":
    sys.exit(main())
