#!/usr/bin/env python3
"""
Twitter RSS 新闻选题更新脚本
- 从 Twitter List RSS 获取内容
- 选题筛选由本地模型完成
- 与当日已有选题去重合并
- 推送到 GitHub Pages
"""

import json
import subprocess
import os
import re
from datetime import datetime, timedelta
import time
from urllib.parse import urlparse
import requests
import xml.etree.ElementTree as ET

# ==================== 配置 ====================

RSS_URL = "http://localhost:1200/twitter/list/2026563584311108010?filter_time=86400"
PROXY = "socks5h://127.0.0.1:7890"
DATA_FILE = "news_data.json"

# GitHub 配置
GITHUB_REPO = "x-reader"  # 根据实际情况修改
GITHUB_BRANCH = "main"

# ==================== RSS 获取 ====================

def fetch_rss():
    """从 RSS 源获取内容"""
    try:
        cmd = [
            "curl", "-s", "-L",
            "--connect-timeout", "10",
            "--max-time", "30",
            "--socks5-hostname", PROXY.replace("socks5h://", ""),
            "-A", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            RSS_URL,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=35)

        if result.returncode != 0:
            print(f"[RSS] 获取失败: {result.stderr}")
            return None

        return result.stdout
    except Exception as e:
        print(f"[RSS] 获取出错: {e}")
        return None


def parse_rss(xml_content):
    """解析 RSS XML 内容"""
    items = []
    try:
        root = ET.fromstring(xml_content)

        # 处理 RSS 2.0 格式
        channel = root.find("channel")
        if channel is not None:
            for item in channel.findall("item"):
                title = item.findtext("title", "").strip()
                content = item.findtext("description", "").strip()
                url = item.findtext("link", "").strip()
                pub_date = item.findtext("pubDate", "")
                source = item.findtext("author", "Twitter")

                # 解析发布时间
                published = parse_pub_date(pub_date)

                items.append({
                    "title": title,
                    "content": content,
                    "url": url,
                    "source": source,
                    "published": published,
                })

        # 处理 Atom 格式
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        for entry in root.findall("atom:entry", ns):
            title = entry.findtext("atom:title", "").strip()
            content = entry.findtext("atom:content", "").strip()
            if not content:
                content = entry.findtext("atom:summary", "").strip()

            url = ""
            link_elem = entry.find("atom:link", ns)
            if link_elem is not None:
                url = link_elem.get("href", "")

            pub_date = entry.findtext("atom:published", "")
            if not pub_date:
                pub_date = entry.findtext("atom:updated", "")

            source = entry.findtext("atom:author/atom:name", "Twitter")

            published = parse_pub_date(pub_date)

            items.append({
                "title": title,
                "content": content,
                "url": url,
                "source": source,
                "published": published,
            })

    except Exception as e:
        print(f"[RSS] 解析出错: {e}")

    return items


def parse_pub_date(date_str):
    """解析各种日期格式为时间戳，正确处理时区"""
    if not date_str:
        return int(time.time())

    date_str = date_str.strip()

    # 处理 RSS 格式: Mon, 09 Mar 2026 07:32:16 GMT
    # Python 的 %Z 无法正确识别 GMT/UTC，需要特殊处理
    rss_pattern = r"^(\w{3}, \d{2} \w{3} \d{4} \d{2}:\d{2}:\d{2}) (\w+)$"
    match = re.match(rss_pattern, date_str)
    if match:
        dt_str, tz_str = match.groups()
        try:
            # 解析无时区的日期时间
            dt = datetime.strptime(dt_str, "%a, %d %b %Y %H:%M:%S")
            # 处理常见时区
            tz_str = tz_str.upper()
            if tz_str in ("GMT", "UTC"):
                # GMT/UTC 时间，需要加上与本地时间的时差
                import time as time_module
                # 获取本地时区偏移（秒）
                local_offset = time_module.timezone if time_module.daylight == 0 else time_module.altzone
                # 本地偏移是负值（东八区为 -28800），所以减去偏移量得到 UTC 时间戳
                return int(dt.timestamp() - local_offset)
            # 其他时区尝试直接解析
            return int(dt.timestamp())
        except ValueError:
            pass

    # 处理带数字时区偏移的格式
    formats = [
        "%a, %d %b %Y %H:%M:%S %z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            return int(dt.timestamp())
        except ValueError:
            continue

    # 如果都解析失败，返回当前时间
    return int(time.time())


def filter_recent_items(items, hours=1):
    """筛选最近 N 小时的内容"""
    cutoff = int(time.time()) - (hours * 3600)
    recent = [item for item in items if item["published"] >= cutoff]
    print(f"[筛选] 最近 {hours} 小时: {len(recent)}/{len(items)} 条")
    return recent


# ==================== AI 处理（本地模型） ====================

def ai_process_items(items):
    """使用本地模型处理新闻选题

    构建提示词供本地模型处理，返回处理后的结果。
    """
    if not items:
        return []

    # 准备输入数据
    items_for_ai = []
    for i, item in enumerate(items[:30]):  # 最多处理30条
        items_for_ai.append({
            "index": i,
            "title": item["title"],
            "content": item["content"][:500] if item["content"] else "",
            "source": item["source"],
            "url": item["url"],
        })

    prompt = f"""你是一位资深科技媒体编辑，负责筛选和加工科技新闻选题。

请对以下新闻进行批量处理，返回 JSON 格式结果：

输入新闻：
{json.dumps(items_for_ai, ensure_ascii=False, indent=2)}

处理要求：

1. **筛选选题**（S级/A级/B级）：
   - S级（90-100分）：AI大模型重大发布、马斯克/SpaceX重大动态、Nature/Science顶刊
   - A级（75-89分）：科技巨头动态、国产大模型、开源爆款、学术突破、人物故事
   - B级（60-74分）：产品评测、技术解析、航天/芯片
   - 过滤掉C级（<60分）：一般商业新闻、消费电子

2. **生成量子位风格中文标题**：
   - 纯中文，无类型前缀
   - 情绪饱满，可用"炸裂"、"刚刚"、"颠覆"、"首次"等词
   - 20-40字，突出核心信息

3. **生成一句话摘要**：
   - 50-100字
   - 概括核心信息，突出关键数据

4. **标注类型**：hot(热点)/ai(AI相关)/tech(科技)/business(商业)

5. **识别核心实体**：
   - 从新闻中提取1-3个核心实体（公司、产品、人物、技术、事件等）
   - 实体名称简洁，2-6字为宜
   - 示例：OpenAI、ChatGPT、马斯克、量子计算、IPO

返回格式（JSON）：
{{
  "results": [
    {{
      "index": 0,
      "score": 85,
      "level": "A",
      "title": "效果炸裂！OpenAI发布新一代模型，能力全面升级",
      "summary": "OpenAI最新发布的大模型在多项基准测试中创下新高，支持更长的上下文窗口和更复杂的推理任务。",
      "type": "ai",
      "reason": "OpenAI重大发布，属于AI领域顶级动态",
      "entities": ["OpenAI", "GPT-5"]
    }}
  ]
}}

注意：
1. 只返回 JSON，不要其他解释
2. 最多选择15条最有价值的
3. 相似主题的新闻合并为一条，标注多来源"""

    print(f"[AI] 准备处理 {len(items_for_ai)} 条新闻...")
    print("[AI] 请将以下提示词发送给本地模型处理：")
    print("=" * 80)
    print(prompt)
    print("=" * 80)
    print("[AI] 处理完成后，将结果保存为 twitter_ai_result.json")

    # 保存提示词到文件，方便处理
    with open("twitter_ai_prompt.txt", "w", encoding="utf-8") as f:
        f.write(prompt)

    return "NEEDS_LOCAL_PROCESSING"


def load_ai_results():
    """加载本地模型处理的结果"""
    result_file = "twitter_ai_result.json"
    if not os.path.exists(result_file):
        return None

    try:
        with open(result_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        # 备份并清理结果文件
        backup_file = f"{result_file}.processed"
        os.rename(result_file, backup_file)
        print(f"[AI] 结果文件已备份: {backup_file}")

        return data.get("results", [])
    except Exception as e:
        print(f"[AI] 加载结果失败: {e}")
        return None


def ai_detect_type_name(type_code):
    """将类型代码转换为中文名称"""
    type_names = {
        "hot": "热点",
        "ai": "AI",
        "tech": "科技",
        "business": "商业",
    }
    return type_names.get(type_code, "科技")


# ==================== 去重与合并 ====================

def calculate_similarity(s1, s2):
    """计算两个字符串的 Jaccard 相似度"""
    s1_lower, s2_lower = s1.lower(), s2.lower()
    if s1_lower in s2_lower or s2_lower in s1_lower:
        return 0.8

    stop_words = {"the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with", "by", "is", "are", "was", "were"}

    def extract_kw(text):
        words = re.findall(r"\b\w{4,}\b", re.sub(r"[^\w\s]", " ", text.lower()))
        return set(w for w in words if w not in stop_words)

    kw1, kw2 = extract_kw(s1), extract_kw(s2)
    if not kw1 or not kw2:
        return 0
    return len(kw1 & kw2) / len(kw1 | kw2)


def find_duplicate(new_item, existing_items):
    """检查新选题是否与已有选题重复"""
    for existing in existing_items:
        # 比较标题相似度
        sim = calculate_similarity(new_item["title"], existing.get("title", ""))
        if sim > 0.5:
            return existing

        # 比较英文标题相似度
        sim_en = calculate_similarity(new_item.get("title_en", ""), existing.get("title_en", ""))
        if sim_en > 0.5:
            return existing

    return None


def merge_source_links(existing_links, new_links):
    """合并来源链接，去重"""
    seen_urls = {link["url"] for link in existing_links}
    merged = existing_links.copy()

    for link in new_links:
        if link["url"] not in seen_urls:
            merged.append(link)
            seen_urls.add(link["url"])

    return merged


# ==================== 版本号生成 ====================

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


# ==================== GitHub Pages 更新 ====================

def load_existing_news():
    """加载当日已有新闻"""
    today = datetime.now().strftime("%Y-%m-%d")

    if not os.path.exists(DATA_FILE):
        return today, []

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            archive = json.load(f)
        return today, archive.get(today, [])
    except Exception as e:
        print(f"[数据] 加载失败: {e}")
        return today, []


def save_news(today, news_data):
    """保存新闻数据到 JSON 文件"""
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                archive = json.load(f)
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

        print(f"[数据] 已保存: {today}, {len(news_data)} 条新闻")
        return True
    except Exception as e:
        print(f"[数据] 保存失败: {e}")
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
                print("[GitHub] 推送成功")
                return True
            else:
                print(f"[GitHub] 推送失败: {push.stderr}")
        else:
            print(f"[GitHub] 提交失败: {result.stderr}")

        return False
    except Exception as e:
        print(f"[GitHub] 出错: {e}")
        return False


# ==================== 主流程 ====================

def process_with_ai(items):
    """处理新闻：筛选 + 生成标题/摘要/类型"""
    # 第一步：AI 批量处理
    print(f"[AI] 开始处理 {len(items)} 条新闻...")

    # 检查是否有本地处理结果
    ai_results = load_ai_results()
    if ai_results is None:
        # 需要本地模型处理
        ai_process_items(items)
        return "NEEDS_LOCAL_PROCESSING"

    print(f"[AI] 返回 {len(ai_results)} 条处理结果")

    if not ai_results:
        return []

    # 建立索引映射
    ai_results_map = {r["index"]: r for r in ai_results if "index" in r}

    # 为原始数据添加索引标记
    for i, item in enumerate(items):
        item["_index"] = i

    # 筛选出有 AI 结果的条目
    selected_items = [items[r["index"]] for r in ai_results if "index" in r and r["index"] < len(items)]

    # 构建最终输出
    processed = []
    for item in selected_items:
        ai_result = ai_results_map.get(item.get("_index", -1), {})
        if not ai_result:
            continue

        level = ai_result.get("level", "B")
        score = ai_result.get("score", 60)

        processed.append({
            "title": ai_result.get("title", item["title"]),
            "title_en": item["title"],
            "summary": ai_result.get("summary", "点击链接查看详情"),
            "type": ai_result.get("type", "tech"),
            "typeName": ai_detect_type_name(ai_result.get("type", "tech")),
            "score": score,
            "level": level,
            "reason": f"【{level}级】评分{score}分 | {ai_result.get('reason', '')}",
            "entities": ai_result.get("entities", []),
            "url": item["url"],
            "source": item["source"],
            "sources": 1,
            "sourceLinks": [{"name": item["source"], "url": item["url"]}],
            "timestamp": int(time.time()),
            "version": generate_version(),
        })

    # 按分数排序
    processed.sort(key=lambda x: x["score"], reverse=True)
    return processed


def merge_with_existing(new_items, existing_items):
    """将新选题与已有选题合并，处理重复"""
    merged = existing_items.copy()
    added_count = 0
    updated_count = 0

    for new_item in new_items:
        duplicate = find_duplicate(new_item, merged)

        if duplicate:
            # 更新来源链接
            existing_links = duplicate.get("sourceLinks", [])
            new_links = new_item.get("sourceLinks", [])
            merged_links = merge_source_links(existing_links, new_links)

            if len(merged_links) > len(existing_links):
                duplicate["sourceLinks"] = merged_links
                duplicate["sources"] = len(merged_links)
                updated_count += 1
                print(f"[合并] 更新来源: {new_item['title'][:30]}...")
        else:
            # 添加新选题
            merged.append(new_item)
            added_count += 1
            print(f"[合并] 新增选题: {new_item['title'][:30]}...")

    print(f"[合并] 新增 {added_count} 条, 更新 {updated_count} 条")
    return merged


def main():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 开始 Twitter RSS 新闻选题更新...")

    # 1. 获取 RSS 内容
    print("[RSS] 获取内容...")
    xml_content = fetch_rss()
    if not xml_content:
        print("[RSS] 获取失败，退出")
        return

    # 2. 解析 RSS
    items = parse_rss(xml_content)
    print(f"[RSS] 解析到 {len(items)} 条内容")

    if not items:
        print("[RSS] 没有内容，退出")
        return

    # 3. 筛选最近 12 小时内容
    recent_items = filter_recent_items(items, hours=12)

    if not recent_items:
        print("[筛选] 最近 12 小时无新内容，退出")
        return

    # 4. AI 处理（本地模型）
    processed = process_with_ai(recent_items)

    if processed == "NEEDS_LOCAL_PROCESSING":
        print("\n[提示] 需要本地模型处理，请：")
        print("1. 读取 twitter_ai_prompt.txt 文件内容")
        print("2. 将内容发送给本地模型处理")
        print("3. 将模型返回的 JSON 保存为 twitter_ai_result.json")
        print("4. 再次运行此脚本")
        return

    print(f"[AI] 最终产出 {len(processed)} 条新闻")

    if not processed:
        print("[AI] 没有高潜力新闻，退出")
        return

    # 5. 加载当日已有新闻并合并
    today, existing_news = load_existing_news()
    final_news = merge_with_existing(processed, existing_news)

    # 6. 保存数据
    if save_news(today, final_news):
        # 7. 推送到 GitHub
        print("\n[GitHub] 开始推送...")
        push_to_github()

    # 8. 统计输出
    s_count = len([t for t in final_news if t["level"] == "S"])
    a_count = len([t for t in final_news if t["level"] == "A"])
    b_count = len([t for t in final_news if t["level"] == "B"])
    multi_source = len([t for t in final_news if t.get("sources", 1) > 1])

    print(f"\n完成!")
    print(f"\n选题统计:")
    print(f"  S级(必报): {s_count} 条")
    print(f"  A级(优先): {a_count} 条")
    print(f"  B级(可选): {b_count} 条")
    print(f"  多源报道: {multi_source} 条")
    print(f"  总计: {len(final_news)} 条")


if __name__ == "__main__":
    main()
