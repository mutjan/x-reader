#!/usr/bin/env python3
"""
量子位风格新闻选题更新脚本 v3.0 - AI 驱动版
- 选题筛选、标题生成、摘要生成全部由 AI 负责（调用 Moonshot API）
- 多源聚合优先：同一事件多源报道自动聚合并加分

使用方法:
1. 直接运行脚本获取新闻数据
2. 将输出的 JSON 发给 Claude 进行 AI 处理
3. 将 Claude 返回的结果保存为 news_ai_processed.json
4. 再次运行脚本完成发布
"""

import json
import subprocess
import os
import re
from datetime import datetime, timedelta
import time
from urllib.parse import urlparse
import requests

# ==================== 配置 ====================

INOREADER_API = "https://www.inoreader.com/reader/api/0"
PROXY = "socks5h://127.0.0.1:7890"

# Moonshot API 配置
AI_CONFIG = {
    "base_url": "https://api.moonshot.cn/v1",
    "model": "kimi-k2.5",
    "api_key": "sk-hITuckhWig7KmNl1V7HTOYanuJ2slD0tA3z6fi3O9V7LEwXc",
    "timeout": 120,
}

# AI 处理缓存文件
AI_CACHE_FILE = "news_ai_cache.json"

# 版本号生成（基于日期和序号）
def generate_version():
    """生成版本号：YYYY.MM.DD-NNN"""
    today = datetime.now().strftime('%Y.%m.%d')
    # 检查今天已有的版本号，递增序号
    version_file = ".version_counter"
    counter = 1
    if os.path.exists(version_file):
        with open(version_file, 'r') as f:
            content = f.read().strip()
            if '-' in content:
                saved_date, saved_counter = content.rsplit('-', 1)
                if saved_date == today:
                    try:
                        counter = int(saved_counter) + 1
                    except ValueError:
                        counter = 1
    with open(version_file, 'w') as f:
        f.write(f"{today}-{counter:03d}")
    return f"{today}-{counter:03d}"


# ==================== AI 调用函数 ====================

def call_ai(prompt, temperature=0.7, max_tokens=4000):
    """调用 Moonshot AI (OpenAI 兼容格式)
    如果远程 API 调用失败，返回 None，由上层处理回退逻辑
    """
    if not AI_CONFIG["api_key"]:
        print("[AI] 未配置 API Key")
        return None

    try:
        response = requests.post(
            f"{AI_CONFIG['base_url']}/chat/completions",
            headers={
                "Authorization": f"Bearer {AI_CONFIG['api_key']}",
                "Content-Type": "application/json",
            },
            json={
                "model": AI_CONFIG["model"],
                "messages": [{"role": "user", "content": prompt}],
                # kimi-k2.5 只支持 temperature=1
                "max_tokens": max_tokens,
            },
            timeout=AI_CONFIG["timeout"],
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"[AI] 远程 API 调用失败: {e}")
        # 打印详细错误信息
        if hasattr(e, 'response') and e.response is not None:
            print(f"[AI] 错误详情: {e.response.text[:500]}")
        print("[AI] 将回退到本地处理模式")
        return None


def ai_process_all(items):
    """使用 AI 批量处理所有新闻：筛选 + 生成标题/摘要/类型

    Args:
        items: 新闻条目列表，每个包含 title, content, url, source

    Returns:
        list: AI 处理后的条目，包含 title, summary, type, score, level 等
    """
    # 准备输入数据（限制数量避免超出 token 限制）
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

    print(f"[AI] 发送 {len(items_for_ai)} 条新闻进行处理...")
    result = call_ai(prompt, temperature=0.5, max_tokens=8000)

    if not result:
        # 远程 API 失败，保存待处理数据到缓存文件，供本地处理
        cache_data = {
            "timestamp": int(time.time()),
            "items": items_for_ai,
            "status": "pending_local_processing"
        }
        with open(AI_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)
        print(f"[AI] 已保存 {len(items_for_ai)} 条新闻到缓存文件: {AI_CACHE_FILE}")
        print("[AI] 请使用本地模型处理此缓存文件")
        return []

    try:
        # 提取 JSON
        json_match = re.search(r'\{.*\}', result, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            return data.get("results", [])
    except Exception as e:
        print(f"[AI] 解析结果失败: {e}")
        print(f"[AI] 原始输出: {result[:500]}")

    return []


def load_local_processed_results():
    """加载本地模型处理后的结果

    读取 news_local_result.json 中的本地处理结果。
    这个函数在远程 API 失败时使用，加载本地模型（Claude）处理的结果。

    Returns:
        list: AI 处理后的条目，包含 title, summary, type, score, level 等
    """
    LOCAL_RESULT_FILE = "news_local_result.json"

    if not os.path.exists(LOCAL_RESULT_FILE):
        return None

    try:
        with open(LOCAL_RESULT_FILE, 'r', encoding='utf-8') as f:
            result_data = json.load(f)

        results = result_data.get("results", [])
        if not results:
            print("[本地处理] 本地结果文件为空")
            return None

        print(f"[本地处理] 从本地结果文件加载 {len(results)} 条处理结果")
        return results

    except Exception as e:
        print(f"[本地处理] 加载本地结果失败: {e}")
        return None


def apply_local_results(ai_results):
    """应用本地模型处理的结果

    将本地模型处理后的结果应用到缓存数据上，并清理缓存文件。

    Args:
        ai_results: 本地模型返回的处理结果列表

    Returns:
        list: 处理后的条目
    """
    if not os.path.exists(AI_CACHE_FILE):
        return ai_results

    try:
        # 备份并清理缓存文件
        backup_file = f"{AI_CACHE_FILE}.processed"
        os.rename(AI_CACHE_FILE, backup_file)
        print(f"[本地处理] 缓存文件已备份: {backup_file}")
    except Exception as e:
        print(f"[本地处理] 备份缓存文件失败: {e}")

    return ai_results


def ai_detect_type_name(type_code):
    """将类型代码转换为中文名称"""
    type_names = {
        "hot": "热点",
        "ai": "AI",
        "tech": "科技",
        "business": "商业",
    }
    return type_names.get(type_code, "科技")


# ==================== 工具函数 ====================

def clean_html(html_text):
    """清理 HTML 标签，提取纯文本"""
    if not html_text:
        return ""
    text = re.sub(r'<(script|style)[^>]*>[^<]*</\1>', ' ', html_text, flags=re.IGNORECASE)
    text = re.sub(r'<img[^>]*>', ' ', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'https?://\S+', '', text)
    return ' '.join(text.split()).strip()


def extract_article_content(url, timeout=10):
    """尝试抓取文章正文内容"""
    if not url:
        return ""

    try:
        cmd = [
            "curl", "-s", "-L",
            "--connect-timeout", str(timeout),
            "--max-time", str(timeout * 2),
            "--socks5-hostname", PROXY.replace("socks5h://", ""),
            "-A", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "-k", url,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout * 2 + 5)

        if result.returncode != 0:
            return ""

        html = result.stdout
        if not html:
            return ""

        text = re.sub(r'<(script|style|nav|header|footer|aside)[^>]*>.*?</\1>', ' ', html, flags=re.IGNORECASE | re.DOTALL)
        paragraphs = re.findall(r'<p[^>]*>(.*?)</p>', text, flags=re.IGNORECASE | re.DOTALL)
        content_parts = []
        for p in paragraphs[:5]:
            clean = re.sub(r'<[^>]+>', ' ', p)
            clean = ' '.join(clean.split())
            if len(clean) > 30:
                content_parts.append(clean)

        return ' '.join(content_parts)[:800]

    except Exception as e:
        return ""


# ==================== 多源聚合与去重 ====================

def calculate_similarity(s1, s2):
    """计算两个字符串的 Jaccard 相似度"""
    s1_lower, s2_lower = s1.lower(), s2.lower()
    if s1_lower in s2_lower or s2_lower in s1_lower:
        return 0.8

    stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'is', 'are', 'was', 'were'}

    def extract_kw(text):
        words = re.findall(r'\b\w{4,}\b', re.sub(r'[^\w\s]', ' ', text.lower()))
        return set(w for w in words if w not in stop_words)

    kw1, kw2 = extract_kw(s1), extract_kw(s2)
    if not kw1 or not kw2:
        return 0
    return len(kw1 & kw2) / len(kw1 | kw2)


def extract_core_entities_for_grouping(title, content=""):
    """提取用于事件分组的核心实体

    返回一个标准化后的实体集合，用于判断两条新闻是否属于同一事件
    """
    text = (title + " " + content).lower()

    # 提取公司名称
    companies = set()
    company_keywords = [
        'grammarly', 'openai', 'google', '微软', '英伟达', 'nvidia',
        'amazon', '亚马逊', 'meta', 'apple', '特斯拉', 'tesla',
        'github', 'spacex', 'xbox', 'windows',
        'lovable', 'wiz', 'nemotron', 'nemoclaw', 'nemo',
        'lecun', 'yann lecun', 'swe-bench', 'anthropic', 'claude',
        'deepseek', 'mistral', 'meta', 'facebook', 'twitter', 'x',
    ]
    for kw in company_keywords:
        if kw in text:
            companies.add(kw)

    # 提取关键产品/功能/事件名称
    products = set()
    product_keywords = [
        'expert review', 'health ai', 'xbox模式', 'xbox mode',
        'class action', '集体诉讼', '开源模型', 'open weight', 'open-weight',
        '收购', 'acquisition', 'ipo', 'layoff', '裁员',
        'generative ai', '生成式ai', 'ai反馈', 'ai feedback',
    ]
    for kw in product_keywords:
        if kw in text:
            products.add(kw)

    return companies, products


def is_same_event(item1, item2, entities1, entities2):
    """判断两条新闻是否属于同一事件

    基于以下规则：
    1. 标题相似度 > 0.5
    2. 同一公司 + 同一产品/功能
    3. 同一公司 + 同一类型的事件（诉讼、下架、道歉等）
    4. 同一公司 + 时间窗口内（24小时内）+ 相似主题词
    """
    title1 = item1.get("title", "")
    title2 = item2.get("title", "")
    content1 = item1.get("content", "")
    content2 = item2.get("content", "")

    # 1. 标题相似度判断
    sim = calculate_similarity(title1, title2)
    if sim > 0.5:
        return True

    companies1, products1 = entities1
    companies2, products2 = entities2

    # 2. 必须有共同的公司
    if not companies1 or not companies2:
        return False

    common_companies = companies1 & companies2
    if len(common_companies) == 0:
        return False

    # 3. 同一公司 + 有共同产品关键词
    common_products = products1 & products2
    if len(common_products) >= 1:
        return True

    # 4. 同一公司 + 都是关于特定事件的报道
    # 合并标题和内容用于事件类型检测
    full_text1 = (title1 + " " + content1).lower()
    full_text2 = (title2 + " " + content2).lower()

    # 定义事件类型关键词组
    event_patterns = [
        # 法律相关
        {'lawsuit', 'class action', '集体诉讼', '诉讼', '被告', '原告', '起诉'},
        # 产品下架/禁用
        {'disables', '下架', '禁用', '移除', 'removes', 'shuts down', '关闭'},
        # 道歉/回应
        {'apolog', '道歉', '回应', 'address', '回应'},
        # 发布/推出
        {'debuts', '发布', '推出', 'announces', 'launches', 'introduces'},
        # 收购/合并
        {'acquisition', '收购', 'acquires', 'buys', 'merges'},
        # 人事变动
        {'resigns', 'resigned', '离职', '辞职', 'joins', 'hires', '任命'},
        # 财务/收入
        {'revenue', '收入', 'funding', '融资', 'ipo', '上市'},
    ]

    for pattern in event_patterns:
        match1 = any(kw in full_text1 for kw in pattern)
        match2 = any(kw in full_text2 for kw in pattern)
        if match1 and match2:
            return True

    return False


def group_by_event(items):
    """按事件分组：相似标题或相同核心实体归为同一事件"""
    groups = []
    used = set()

    # 预计算每个条目的核心实体
    item_entities = {}
    for i, item in enumerate(items):
        companies, products = extract_core_entities_for_grouping(
            item.get("title", ""), item.get("content", "")
        )
        item_entities[i] = (companies, products)

    for i, item in enumerate(items):
        if i in used:
            continue

        group = [item]
        used.add(i)

        for j, other in enumerate(items[i + 1:], i + 1):
            if j in used:
                continue

            if is_same_event(item, other, item_entities[i], item_entities[j]):
                group.append(other)
                used.add(j)

        groups.append(group)

    return groups


def merge_event_group(group, ai_results_map):
    """合并同一事件的多个来源"""
    if not group:
        return None

    # 取 AI 评分最高的作为代表
    representative = max(group, key=lambda x: ai_results_map.get(x.get("_index", -1), {}).get("score", 0))

    all_links = []
    seen_urls = set()

    for item in group:
        url = item.get("url", "")
        source = item.get("source", "Unknown")
        if url and url not in seen_urls:
            all_links.append({"name": source, "url": url})
            seen_urls.add(url)

    ai_result = ai_results_map.get(representative.get("_index", -1), {})

    merged = {
        "title_en": representative["title"],
        "content": representative.get("content", ""),
        "url": representative.get("url", ""),
        "source": representative.get("source", "Unknown"),
        "published": representative.get("published", 0),
        "_ai_result": ai_result,
        "_sourceLinks": all_links,
        "_sourceCount": len(all_links),
    }

    return merged


# ==================== Inoreader API ====================

def curl_request(url, headers=None, timeout=30):
    """通过 curl + SOCKS5 代理发送请求"""
    cmd = [
        "curl", "-s",
        "--connect-timeout", str(timeout),
        "--max-time", str(timeout * 2),
        "--socks5-hostname", PROXY.replace("socks5h://", ""),
        "-k", url,
    ]
    if headers:
        for key, value in headers.items():
            cmd.extend(["-H", f"{key}: {value}"])
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout


def get_token():
    """从本地配置读取 Inoreader access token"""
    config_path = os.path.expanduser("~/.openclaw/agents/main/agent/auth-profiles.json")
    with open(config_path) as f:
        config = json.load(f)
    return config.get("inoreader", {}).get("access_token")


def get_recent_items(token, hours=24, limit=200):
    """获取 Inoreader 最近 N 小时内容"""
    since = int(time.time()) - (hours * 3600)
    url = f"{INOREADER_API}/stream/contents/user/-/state/com.google/reading-list?n={limit}&ot={since}"
    response = curl_request(url, headers={"Authorization": f"Bearer {token}"})
    return json.loads(response)


def parse_items(data):
    """解析 Inoreader 返回的 items"""
    items = []
    for item in data.get("items", []):
        title = item.get("title", "")
        content = ""
        if "summary" in item and "content" in item["summary"]:
            content = item["summary"]["content"]
        elif "content" in item and isinstance(item["content"], dict):
            content = item["content"].get("content", "")
        content = re.sub(r'<[^>]+>', '', content)

        links = item.get("alternate", [])
        url = links[0].get("href", "") if links else ""
        source = item.get("origin", {}).get("title", "Unknown")

        items.append({
            "title": title,
            "content": content,
            "url": url,
            "source": source,
            "published": item.get("published", 0),
        })
    return items


# ==================== GitHub Pages 更新 ====================

def update_github_pages(news_data):
    """更新 news_data.json 并推送到 GitHub Pages"""
    try:
        today = datetime.now().strftime('%Y-%m-%d')
        data_file = "news_data.json"

        if os.path.exists(data_file):
            with open(data_file, 'r', encoding='utf-8') as f:
                archive = json.load(f)
        else:
            archive = {}

        archive[today] = news_data

        dates = sorted(archive.keys())
        if len(dates) > 30:
            for old_date in dates[:-30]:
                del archive[old_date]

        with open(data_file, 'w', encoding='utf-8') as f:
            json.dump(archive, f, ensure_ascii=False, indent=2)

        print(f"[GitHub Pages] 数据已保存: {today}, {len(news_data)} 条新闻")

        env = os.environ.copy()
        env["GIT_AUTHOR_NAME"] = "OpenClaw Bot"
        env["GIT_AUTHOR_EMAIL"] = "bot@openclaw.ai"
        env["GIT_COMMITTER_NAME"] = "OpenClaw Bot"
        env["GIT_COMMITTER_EMAIL"] = "bot@openclaw.ai"

        subprocess.run(["git", "add", data_file], check=True, env=env)
        result = subprocess.run(
            ["git", "commit", "-m", f"Update news data for {today}"],
            capture_output=True, text=True, env=env,
        )

        if result.returncode == 0 or "nothing to commit" in (result.stdout + result.stderr).lower():
            push = subprocess.run(
                ["git", "push", "origin", "main"],
                capture_output=True, text=True, env=env,
            )
            if push.returncode == 0:
                print("[GitHub Pages] 推送成功")
                return True
            else:
                print(f"[GitHub Pages] 推送失败: {push.stderr}")
        else:
            print(f"[GitHub Pages] 提交失败: {result.stderr}")
        return False
    except Exception as e:
        print(f"[GitHub Pages] 更新出错: {e}")
        return False


# ==================== 主流程 ====================

def process_with_ai(items, local_results=None):
    """使用 AI 处理新闻：筛选 + 生成标题/摘要/类型

    Args:
        items: 新闻条目列表
        local_results: 本地模型处理的结果（当远程 API 失败时使用）

    Returns:
        list: 处理后的新闻条目
    """

    # 第一步：AI 批量处理
    print(f"[AI] 开始处理 {len(items)} 条新闻...")

    # 如果提供了本地处理结果，直接使用
    if local_results:
        print("[AI] 使用本地模型处理结果")
        ai_results = local_results
    else:
        ai_results = ai_process_all(items)

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

    # 第二步：按事件分组（多源聚合）
    event_groups = group_by_event(selected_items)
    print(f"[聚合] 分为 {len(event_groups)} 个独立事件")

    # 第三步：合并并构建最终输出
    processed = []
    for group in event_groups:
        merged = merge_event_group(group, ai_results_map)
        if not merged or not merged.get("_ai_result"):
            continue

        ai_result = merged["_ai_result"]

        # 构建选题理由
        level_labels = {"S": "S级必报", "A": "A级优先", "B": "B级可选"}
        level = ai_result.get("level", "B")
        score = ai_result.get("score", 60)
        reason_text = f"【{level_labels.get(level, level)}】评分{score}分"
        if merged["_sourceCount"] > 1:
            reason_text += f" | {merged['_sourceCount']}个来源报道"
        if ai_result.get("reason"):
            reason_text += f" | {ai_result['reason']}"

        processed.append({
            "title": ai_result.get("title", merged["title_en"]),
            "title_en": merged["title_en"],
            "summary": ai_result.get("summary", "点击链接查看详情"),
            "type": ai_result.get("type", "tech"),
            "typeName": ai_detect_type_name(ai_result.get("type", "tech")),
            "score": score,
            "level": level,
            "reason": reason_text,
            "entities": ai_result.get("entities", []),
            "url": merged["url"],
            "source": merged["source"],
            "sources": merged["_sourceCount"],
            "sourceLinks": merged["_sourceLinks"],
            "timestamp": int(time.time()),
            "version": generate_version(),
        })

    # 按分数排序
    processed.sort(key=lambda x: x["score"], reverse=True)

    return processed


def main():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 开始 AI 驱动的新闻选题更新...")

    # 检查是否有本地处理结果
    local_results = None
    if os.path.exists(AI_CACHE_FILE):
        try:
            with open(AI_CACHE_FILE, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            if cache_data.get("status") == "pending_local_processing":
                print("\n[本地处理模式] 检测到待处理的缓存文件")
                print(f"[本地处理模式] 缓存时间: {datetime.fromtimestamp(cache_data.get('timestamp', 0)).strftime('%Y-%m-%d %H:%M:%S')}")

                # 尝试加载本地处理结果
                local_results = load_local_processed_results()
                if local_results is None:
                    print("[本地处理模式] 未找到本地处理结果 (news_local_result.json)")
                    print("[本地处理模式] 请使用本地模型处理缓存文件，然后将结果保存为 news_local_result.json")
                    print("[本地处理模式] 或者删除缓存文件重新尝试远程 API\n")
                    return
                else:
                    print("[本地处理模式] 成功加载本地处理结果，将继续执行...\n")
        except Exception:
            pass

    try:
        items = []

        # 如果有本地处理结果，从缓存文件加载原始items
        if local_results:
            print("[本地处理模式] 从缓存加载原始新闻数据...")
            try:
                with open(AI_CACHE_FILE, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                items = cache_data.get("items", [])
                # 添加 _index 字段和 published 字段
                import time
                for i, item in enumerate(items):
                    item["_index"] = i
                    if "published" not in item:
                        item["published"] = int(time.time())
                print(f"[本地处理模式] 加载了 {len(items)} 条原始新闻")
            except Exception as e:
                print(f"[本地处理模式] 加载缓存失败: {e}")
                return
        else:
            # 1. 获取 Token
            token = get_token()
            if not token:
                print("无法获取 Inoreader token")
                return

            # 2. 获取最近 24 小时内容
            print("获取最近 24 小时的内容...")
            data = get_recent_items(token, hours=24, limit=200)
            items = parse_items(data)
            print(f"获取到 {len(items)} 条内容")

        if not items:
            print("没有获取到新闻内容")
            return

        # 3. AI 处理（筛选 + 生成）
        processed = process_with_ai(items, local_results=local_results)
        print(f"最终产出 {len(processed)} 条新闻")

        # 4. 更新 GitHub Pages
        if processed:
            print("\n[GitHub Pages] 开始更新...")
            update_github_pages(processed)
        else:
            print("没有高潜力新闻需要更新")

        # 5. 统计输出
        s_count = len([t for t in processed if t["level"] == "S"])
        a_count = len([t for t in processed if t["level"] == "A"])
        b_count = len([t for t in processed if t["level"] == "B"])
        multi_source = len([t for t in processed if t["sources"] > 1])

        print(f"\n完成!")
        print(f"\n选题统计:")
        print(f"  S级(必报): {s_count} 条")
        print(f"  A级(优先): {a_count} 条")
        print(f"  B级(可选): {b_count} 条")
        print(f"  多源报道: {multi_source} 条")

    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
