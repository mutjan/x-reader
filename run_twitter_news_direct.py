#!/usr/bin/env python3
"""
Twitter RSS 新闻选题更新脚本 - AI助手直接调用版

使用方法：
  1. 运行脚本获取待处理新闻: python3 run_twitter_news_direct.py
  2. 脚本会输出需要AI处理的新闻prompt
  3. AI助手在当前会话中处理prompt，生成JSON结果
  4. 将AI结果保存到 twitter_ai_result.json
  5. 再次运行脚本完成后续流程: python3 run_twitter_news_direct.py

或者直接使用Python交互模式：
  from run_twitter_news_direct import run_fetch_and_filter, process_ai_results
  result = run_fetch_and_filter()  # 获取新闻和prompt
  # AI助手处理 result['prompt']
  process_ai_results(result['items'], ai_results)  # 完成后续流程
"""

import json
import os
import sys
import time
from datetime import datetime

# 导入主脚本的功能
from run_twitter_news import (
    setup_json_logging,
    check_python_version,
    load_processed_ids,
    get_cache_stats,
    check_rss_health,
    fetch_rss,
    parse_rss,
    filter_processed_items,
    filter_recent_items,
    keyword_pre_filter,
    get_ai_processing_prompt,
    process_with_ai_results,
    extract_tweet_id,
    save_processed_ids,
    generate_report,
    logger
)


def run_fetch_and_filter():
    """
    执行RSS获取和预筛选流程，返回待处理的新闻和prompt

    Returns:
        dict: {
            "items": 预筛选后的新闻列表,
            "prompt": AI处理prompt,
            "cache_data": 缓存数据（用于后续更新）
        }
    """
    check_python_version()
    setup_json_logging()

    timing = {
        "start": time.time(),
        "rss_fetch": 0,
        "rss_parse": 0,
        "filter": 0,
    }

    logger.info("=" * 60)
    logger.info("开始 Twitter RSS 新闻获取与预筛选...")
    logger.info("=" * 60)

    # 加载已处理的推文ID
    cache_data = load_processed_ids()
    cache_stats = get_cache_stats(cache_data)
    logger.info(f"[缓存] 已加载 {cache_stats['total']} 条历史推文ID (近1天: {cache_stats['recent_1d']}, 近7天: {cache_stats['recent_7d']})")

    # RSS健康检查
    logger.info("[RSS] 健康检查...")
    health = check_rss_health()
    if health["status"] == "healthy":
        logger.info(f"[RSS] 健康状态: 正常 | 响应时间: {health['response_time']:.2f}s | 内容数: {health['items_count']}")
    elif health["status"] == "stale":
        logger.warning(f"[RSS] 健康状态: 内容陈旧 | 平均内容年龄: {health['avg_age_hours']}小时")
    else:
        logger.error(f"[RSS] 健康状态: 异常 | 错误: {'; '.join(health['errors'])}")

    # 1. 获取 RSS 内容
    logger.info("[RSS] 获取内容...")
    t0 = time.time()
    xml_content = fetch_rss()
    timing["rss_fetch"] = time.time() - t0

    if not xml_content:
        logger.error("[RSS] 获取失败，退出")
        return None

    # 2. 解析 RSS
    t0 = time.time()
    items = parse_rss(xml_content)
    timing["rss_parse"] = time.time() - t0
    logger.info(f"[RSS] 解析到 {len(items)} 条内容 (耗时: {timing['rss_parse']:.2f}s)")

    if not items:
        logger.warning("[RSS] 没有内容，退出")
        return None

    # 2.5 过滤已处理的推文
    items, processed_ids_set = filter_processed_items(items, cache_data)

    # 3. 筛选最近内容（智能时间窗口）
    t0 = time.time()
    smart_target = int(os.getenv("SMART_WINDOW_TARGET", "20"))
    recent_items = filter_recent_items(items, hours=1, smart_mode=True)
    timing["filter"] = time.time() - t0

    if not recent_items:
        logger.info("[筛选] 智能时间窗口内无新内容，退出")
        current_time = time.time()
        for item in items:
            tweet_id = extract_tweet_id(item.get("url", ""))
            if tweet_id:
                cache_data[tweet_id] = current_time
        save_processed_ids(cache_data)
        return None

    # 4. 关键词预筛选
    logger.info("\n" + "-" * 40)
    logger.info("[预筛选] 执行关键词预筛选...")
    filtered_items = keyword_pre_filter(recent_items, min_priority_score=5, ensure_top_n=40)
    logger.info(f"[预筛选] 保留 {len(filtered_items)} 条新闻进入AI处理")
    logger.info("-" * 40)

    if not filtered_items:
        logger.info("[预筛选] 没有符合条件的新闻，退出")
        return None

    # 5. 生成AI处理prompt
    prompt = get_ai_processing_prompt(filtered_items)

    logger.info("\n" + "=" * 60)
    logger.info("[直接模式] 请在当前会话中处理以下新闻")
    logger.info("=" * 60)

    return {
        "items": filtered_items,
        "prompt": prompt,
        "cache_data": cache_data,
        "timing": timing
    }


def process_ai_results(filtered_items, ai_results, cache_data=None, timing=None):
    """
    使用AI处理结果完成后续流程

    Args:
        filtered_items: 预筛选后的新闻列表
        ai_results: AI处理后的结果列表（JSON格式）
        cache_data: 可选的缓存数据
        timing: 可选的时间统计

    Returns:
        dict: 执行结果统计
    """
    if timing is None:
        timing = {"start": time.time(), "rss_fetch": 0, "rss_parse": 0, "filter": 0}

    # 处理AI结果
    result = process_with_ai_results(filtered_items, ai_results, timing=timing)

    if result.get("success"):
        # 更新已处理的推文ID缓存
        if cache_data is not None:
            current_time = time.time()
            for item in filtered_items:
                tweet_id = extract_tweet_id(item.get("url", ""))
                if tweet_id:
                    cache_data[tweet_id] = current_time

            stats_before = get_cache_stats(cache_data)
            save_processed_ids(cache_data)
            stats_after = get_cache_stats(cache_data)
            logger.info(f"[缓存] 已更新推文ID缓存（总缓存: {stats_after['total']}条）")

        # 生成报告
        generate_report(result["final_news"], timing)

    return result


def main():
    """主流程"""
    # 检查是否存在AI处理结果文件
    result_file = "twitter_ai_result.json"

    if os.path.exists(result_file):
        # 有结果文件，执行后续流程
        logger.info("[直接模式] 检测到AI处理结果，执行后续流程...")

        # 需要先获取filtered_items（可以从缓存或重新运行）
        # 这里我们重新运行获取流程，但使用缓存避免重复处理
        fetch_result = run_fetch_and_filter()

        if fetch_result is None:
            logger.error("[直接模式] 无法获取新闻列表")
            return

        # 读取AI处理结果
        try:
            with open(result_file, "r", encoding="utf-8") as f:
                content = f.read()

            from run_twitter_news import safe_json_loads
            data = safe_json_loads(content, max_retries=3)

            if not data or "results" not in data:
                logger.error("[直接模式] AI处理结果格式错误")
                return

            ai_results = data["results"]

            # 执行后续流程
            result = process_ai_results(
                fetch_result["items"],
                ai_results,
                cache_data=fetch_result["cache_data"],
                timing=fetch_result["timing"]
            )

            if result.get("success"):
                # 备份并删除结果文件
                backup_file = f"{result_file}.processed"
                os.rename(result_file, backup_file)
                logger.info(f"[直接模式] 结果文件已备份: {backup_file}")
                logger.info("[直接模式] 任务完成！")
            else:
                logger.error(f"[直接模式] 处理失败: {result.get('reason', 'unknown')}")

        except Exception as e:
            logger.error(f"[直接模式] 处理出错: {e}")
            import traceback
            traceback.print_exc()

    else:
        # 没有结果文件，执行获取流程
        fetch_result = run_fetch_and_filter()

        if fetch_result:
            # 输出prompt供AI助手使用
            print("\n" + "=" * 80)
            print("【AI助手处理指引】")
            print("=" * 80)
            print("1. 请读取上面的 prompt 内容")
            print("2. 在当前会话中处理这些新闻，生成JSON结果")
            print("3. 将结果保存到 twitter_ai_result.json 文件")
            print("4. 再次运行本脚本完成后续流程")
            print("=" * 80)
            print("\n【Prompt内容】（已保存到 twitter_ai_prompt.txt）:\n")
            print(fetch_result["prompt"][:500] + "..." if len(fetch_result["prompt"]) > 500 else fetch_result["prompt"])

            # 同时保存到文件（便于查看）
            with open("twitter_ai_prompt.txt", "w", encoding="utf-8") as f:
                f.write(fetch_result["prompt"])

            return fetch_result
        else:
            logger.info("[直接模式] 没有新内容需要处理")
            return None


if __name__ == "__main__":
    result = main()
    # 如果是直接模式返回的结果，可以在交互式环境中使用
    if result and isinstance(result, dict) and "items" in result:
        # 供交互式使用
        pass
