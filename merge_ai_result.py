#!/usr/bin/env python3
"""
AI结果合并脚本
手动触发AI结果文件与现有数据的合并

使用方法:
  python merge_ai_result.py [ai_result_file]
  如果不指定文件，默认使用 twitter_ai_result.json
"""

import json
import os
import sys
import subprocess
from datetime import datetime
import time
import logging

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

DATA_FILE = "news_data.json"
GITHUB_BRANCH = "main"


def generate_version():
    """生成版本号：YYYY.MM.DD-NNN"""
    today = datetime.now().strftime("%Y.%m.%d")
    version_file = ".version_counter"
    counter = 1

    if os.path.exists(version_file):
        with open(version_file, "r") as f:
            content = f.read().strip()
            if "-" in content:
                saved_date, saved_counter = content.rsplit("-", 1)
                if saved_date == today:
                    try:
                        counter = int(saved_counter) + 1
                    except ValueError:
                        counter = 1

    with open(version_file, "w") as f:
        f.write(f"{today}-{counter:03d}")

    return f"{today}-{counter:03d}"


def safe_json_loads(json_str, max_retries=1):
    """安全加载JSON字符串"""
    for attempt in range(max_retries):
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            if attempt == max_retries - 1:
                logger.error(f"JSON解析失败: {e}")
                return None
    return None


def load_existing_news():
    """加载当日已有新闻"""
    today = datetime.now().strftime("%Y-%m-%d")

    if not os.path.exists(DATA_FILE):
        return today, []

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            content = f.read()
        archive = safe_json_loads(content, max_retries=1) or {}
        return today, archive.get(today, [])
    except Exception as e:
        logger.error(f"[数据] 加载失败: {e}")
        return today, []


def save_news(today, news_data):
    """保存新闻数据到 JSON 文件"""
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                content = f.read()
            archive = safe_json_loads(content, max_retries=1) or {}
        else:
            archive = {}

        archive[today] = news_data

        # 只保留最近 30 天
        dates = sorted(archive.keys())
        if len(dates) > 30:
            for old_date in dates[:-30]:
                del archive[old_date]

        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(archive, f, ensure_ascii=False, indent=2)

        logger.info(f"[数据] 已保存: {today}, {len(news_data)} 条新闻")
        return True
    except Exception as e:
        logger.error(f"[数据] 保存失败: {e}")
        return False


def push_to_github():
    """推送到 GitHub"""
    try:
        env = os.environ.copy()
        env["GIT_AUTHOR_NAME"] = "OpenClaw Bot"
        env["GIT_AUTHOR_EMAIL"] = "bot@openclaw.ai"
        env["GIT_COMMITTER_NAME"] = "OpenClaw Bot"
        env["GIT_COMMITTER_EMAIL"] = "bot@openclaw.ai"

        subprocess.run(["git", "add", DATA_FILE], check=True, env=env)

        today = datetime.now().strftime("%Y-%m-%d")
        result = subprocess.run(
            ["git", "commit", "-m", f"Update Twitter news for {today}"],
            capture_output=True, text=True, env=env,
        )

        if result.returncode == 0 or "nothing to commit" in (result.stdout + result.stderr).lower():
            push = subprocess.run(
                ["git", "push", "origin", GITHUB_BRANCH],
                capture_output=True, text=True, env=env,
            )
            if push.returncode == 0:
                logger.info("[GitHub] 推送成功")
                return True
            else:
                logger.error(f"[GitHub] 推送失败: {push.stderr}")
        else:
            logger.error(f"[GitHub] 提交失败: {result.stderr}")

        return False
    except Exception as e:
        logger.error(f"[GitHub] 出错: {e}")
        return False


def merge_ai_result(ai_result_file):
    """合并AI结果文件"""
    if not os.path.exists(ai_result_file):
        logger.error(f"[合并] AI结果文件不存在: {ai_result_file}")
        return False

    try:
        with open(ai_result_file, "r", encoding="utf-8") as f:
            content = f.read()

        data = safe_json_loads(content)
        if data is None:
            logger.error("[合并] AI结果文件JSON解析失败")
            return False

        ai_results = data.get("results", [])
        if not ai_results:
            logger.warning("[合并] AI结果为空")
            return False

        logger.info(f"[合并] 加载 {len(ai_results)} 条AI处理结果")

        # 构建processed_items
        processed = []
        for result in ai_results:
            level = result.get("level", "B")
            score = result.get("score", 60)

            type_names = {
                "hot": "热点",
                "ai": "AI",
                "tech": "科技",
                "business": "商业",
            }

            processed.append({
                "title": result.get("title", ""),
                "title_en": "",
                "summary": result.get("summary", "点击链接查看详情"),
                "type": result.get("type", "tech"),
                "typeName": type_names.get(result.get("type", "tech"), "科技"),
                "score": score,
                "level": level,
                "reason": f"【{level}级】评分{score}分 | {result.get('reason', '')}",
                "entities": result.get("entities", [])[:5],
                "tags": result.get("tags", [])[:5],
                "url": "",
                "source": "AI",
                "sources": 1,
                "sourceLinks": [],
                "timestamp": int(time.time()),
                "version": generate_version(),
                "priority_score": 0,
            })

        # 按分数排序
        processed.sort(key=lambda x: x["score"], reverse=True)

        # 加载当日已有新闻并合并
        today, existing_news = load_existing_news()

        # 简单合并（不去重，因为自动合并模式主要用于快速合并）
        final_news = existing_news + processed

        # 保存数据
        save_success = save_news(today, final_news)

        if save_success:
            # 推送到 GitHub
            logger.info("\n[GitHub] 开始推送...")
            push_to_github()

            # 备份AI结果文件
            backup_file = f"{ai_result_file}.merged"
            os.rename(ai_result_file, backup_file)
            logger.info(f"[合并] AI结果文件已备份: {backup_file}")

            # 统计输出
            s_count = len([t for t in final_news if t["level"] == "S"])
            a_plus_count = len([t for t in final_news if t["level"] == "A+"])
            a_count = len([t for t in final_news if t["level"] == "A"])
            b_count = len([t for t in final_news if t["level"] == "B"])

            logger.info("\n" + "=" * 60)
            logger.info("合并完成!")
            logger.info("=" * 60)
            logger.info(f"  S级(必报): {s_count} 条")
            logger.info(f"  A+级(重要): {a_plus_count} 条")
            logger.info(f"  A级(优先): {a_count} 条")
            logger.info(f"  B级(可选): {b_count} 条")
            logger.info(f"  总计: {len(final_news)} 条")
            logger.info("=" * 60)

            return True

        return False

    except Exception as e:
        logger.error(f"[合并] 处理失败: {e}")
        return False


def main():
    ai_result_file = sys.argv[1] if len(sys.argv) > 1 else "twitter_ai_result.json"

    logger.info("=" * 60)
    logger.info(f"开始合并AI结果: {ai_result_file}")
    logger.info("=" * 60)

    success = merge_ai_result(ai_result_file)

    if success:
        logger.info("✓ 合并成功")
        sys.exit(0)
    else:
        logger.error("✗ 合并失败")
        sys.exit(1)


if __name__ == "__main__":
    main()
