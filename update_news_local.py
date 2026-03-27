#!/usr/bin/env python3
"""
新闻选题更新脚本 v5.0 - 本地 Agent 直接处理
去掉 API 调用，直接在 Agent 会话中处理新闻

使用方法:
  python update_news_local.py [--source twitter|inoreader|all]

工作流程:
  1. 获取 RSS 内容 (Twitter/Inoreader)
  2. 关键词预筛选
  3. 本地 Agent 处理（直接调用，无需 API）
  4. 合并去重
  5. 保存并推送到 GitHub
"""

import argparse
import json
import subprocess
import os
import re
import sys
from datetime import datetime, timedelta
import time
from urllib.parse import urlparse
import requests
import xml.etree.ElementTree as ET
import logging

# 导入预告事件管理模块
try:
    from upcoming_events import (
        load_upcoming_events,
        check_items_against_events,
        convert_matched_to_news,
        update_event_status,
        get_pending_events_summary,
        cleanup_expired_events
    )
    UPCOMING_EVENTS_AVAILABLE = True
except ImportError:
    UPCOMING_EVENTS_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.debug("[预告事件] 模块未加载")

# ==================== 配置 ====================

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# RSS 源配置
RSS_CONFIG = {
    "twitter": {
        "url": "http://localhost:1200/twitter/home/2026563584311108010?filter_time=86400",
        "type": "rss",
        "name": "Twitter"
    },
    "inoreader": {
        "api": "https://www.inoreader.com/reader/api/0",
        "type": "api",
        "name": "Inoreader"
    }
}

# 文件配置
DATA_FILE = "news_data.json"
PROCESSED_IDS_FILE = ".processed_ids.json"
MAX_CACHED_IDS = 5000
GITHUB_BRANCH = "main"

# 默认批量大小
DEFAULT_BATCH_SIZE = 30

# ==================== 关键词配置（优化版） ====================

PRIORITY_KEYWORDS = {
    "ai": ["gpt-5", "gpt-4.5", "gpt5.4", "claude 4", "gemini 2",
           "o3", "o4", "reasoning", "agent", "agents", "agi",
           "openai", "anthropic", "deepmind", "xai", "grok", "perplexity", "cursor", "manus", "sora",
           "chatgpt", "claude", "gemini", "deepseek", "grok-3",
           "llm", "foundation model", "moe", "mixture of experts",
           "mcp", "model context protocol", "function calling", "tool use"],
    "bigtech": ["apple intelligence", "google ai", "microsoft ai", "meta ai",
                "nvidia", "tesla fsd", "spacex", "neuralink", "starlink",
                "微信", "wechat", "微信小程序", "微信支付", "公众号",
                "字节", "bytedance", "腾讯", "tencent", "阿里", "alibaba",
                "智谱", "zhipu", "月之暗面", "moonshot", "kimi", "minimax", "零一万物",
                "qwen", "通义", "mistral", "cohere", "glm", "chatglm",
                "amazon", "aws", "apple", "microsoft", "google", "meta",
                "canva", "figma", "notion", "stripe", "palantir"],
    "chip": ["blackwell", "hopper", "h100", "h200", "b100", "b200",
             "tensor", "cuda", "quantum chip", "ai chip", "ai accelerator",
             "tsmc", "intel", "amd", "gpu shortage", "compute cluster"],
    "product": ["launch", "announced", "unveiled", "available now",
                "open source", "github", "paper", "demo", "重磅", "突发",
                "new model", "new feature", "update", "upgrade"],
    "people": ["elon musk", "musk", "sam altman", "sundar pichai", "satya nadella",
               "tim cook", "mark zuckerberg", "demis hassabis", "ilya sutskever",
               "andrej karpathy", "dario amodei", "fei-fei li", "李彦宏",
               "jensen huang", "黄仁勋", "greg brockman", "brockman",
               "demis hassabis", "hassabis", "pieter abbeel", "sergey brin",
               "demis", "jeff bezos", "bill gates", "larry page"],
    "research": ["nature", "science", "cell", "arxiv", "breakthrough",
                 "ai for science", "ai4science", "protein folding",
                 "mathematics", "theorem proving", "frontiermath",
                 "alphaevolve", "deepmind", "alphafold", "ramsey",
                 "materials discovery", "drug design"],
    "business": ["ipo", "上市", "收购", "并购", "融资", "估值", "独角兽",
                 "funding", "valuation", "unicorn", "investment",
                 "revenue", "run rate", "series a", "series b", "series c",
                 "raised", "billion", "million", "growth"],
    "multimodal": ["sora", "video generation", "text-to-video", "image generation",
                   "multimodal", "vision model", "vlm", "diffusion",
                   "runway", "pika", "heygen", "elevenlabs"],
    "coding": ["cursor", "windsurf", "github copilot", "code generation",
               "devin", "coding agent", "ide", "vscode", "ai engineer",
               "vibe coding", "vibecoding", "trae", "cline", "aider"],
    "robotics": ["robotics", "robot", "embodied ai", "humanoid",
                 "figure ai", "tesla bot", "optimus", "autonomous",
                 "agility robotics", "digit", "1x technologies",
                 "covariant", "physical intelligence", "pi",
                 "具身智能", "人形机器人", "sim2real", "unitree", "宇树"],
}

ALL_PRIORITY_KEYWORDS = []
for category, keywords in PRIORITY_KEYWORDS.items():
    ALL_PRIORITY_KEYWORDS.extend(keywords)


# ==================== JSON 安全处理 ====================

def sanitize_json_string(text):
    """清理JSON字符串中的特殊字符"""
    if not isinstance(text, str):
        return text
    text = text.replace('"', '"').replace('"', '"')
    text = text.replace(''', "'").replace(''', "'")
    text = text.replace('＂', '"').replace("＇", "'")
    text = re.sub(r'([{,]\s*)([a-zA-Z_][a-zA-Z0-9_]*)(\s*:)', r'\1"\2"\3', text)
    text = re.sub(r',(\s*[}\]])', r'\1', text)
    return text


def safe_json_loads(json_str, max_retries=3, context=""):
    """安全加载JSON字符串"""
    for attempt in range(max_retries):
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            if attempt == 0:
                json_str = sanitize_json_string(json_str)
            elif attempt == 1:
                json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', json_str, re.DOTALL)
                if json_match:
                    json_str = sanitize_json_string(json_match.group(1))
    return None


def safe_json_dumps(obj, ensure_ascii=False, indent=2):
    """安全地将Python对象转为JSON字符串"""
    def sanitize_obj(obj):
        if isinstance(obj, dict):
            return {k: sanitize_obj(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [sanitize_obj(item) for item in obj]
        elif isinstance(obj, str):
            return sanitize_json_string(obj)
        return obj
    return json.dumps(sanitize_obj(obj), ensure_ascii=ensure_ascii, indent=indent)


# ==================== 实体标准化 ====================

def normalize_entities(entities):
    """标准化实体列表"""
    if not entities:
        return []

    entity_mapping = {
        "openai": "OpenAI", "OPENAI": "OpenAI",
        "anthropic": "Anthropic", "deepmind": "DeepMind",
        "google": "Google", "meta": "Meta", "microsoft": "Microsoft",
        "nvidia": "NVIDIA", "tesla": "Tesla", "spacex": "SpaceX",
        "xai": "xAI", "grok": "Grok", "chatgpt": "ChatGPT",
        "claude": "Claude", "gemini": "Gemini", "deepseek": "DeepSeek",
        "cursor": "Cursor", "github": "GitHub", "vercel": "Vercel",
        "elon musk": "Elon Musk", "musk": "Elon Musk",
        "sam altman": "Sam Altman", "altman": "Sam Altman",
        "sundar pichai": "Sundar Pichai", "satya nadella": "Satya Nadella",
        "tim cook": "Tim Cook", "mark zuckerberg": "Mark Zuckerberg",
        "zuckerberg": "Mark Zuckerberg", "demis hassabis": "Demis Hassabis",
        "hassabis": "Demis Hassabis", "ilya sutskever": "Ilya Sutskever",
        "andrej karpathy": "Andrej Karpathy", "karpathy": "Andrej Karpathy",
        "dario amodei": "Dario Amodei", "fei-fei li": "李飞飞",
        "jensen huang": "Jensen Huang", "黄仁勋": "Jensen Huang",
        "gpt-4": "GPT-4", "gpt-5": "GPT-5", "gpt4": "GPT-4", "gpt5": "GPT-5",
        "llm": "LLM", "ai": "AI", "agi": "AGI", "mcp": "MCP",
    }

    normalized = []
    seen = set()

    for entity in entities:
        if not entity or not isinstance(entity, str):
            continue
        entity = entity.strip()
        if not entity:
            continue
        lower = entity.lower()
        if lower in entity_mapping:
            entity = entity_mapping[lower]
        if lower not in seen:
            seen.add(lower)
            normalized.append(entity)

    return normalized


# ==================== 工具函数 ====================

def load_processed_ids():
    """加载已处理的内容ID缓存"""
    if not os.path.exists(PROCESSED_IDS_FILE):
        return set()
    try:
        with open(PROCESSED_IDS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return set(data.get("ids", []))
    except Exception as e:
        logger.warning(f"[缓存] 加载已处理ID失败: {e}")
        return set()


def save_processed_ids(ids):
    """保存已处理的内容ID缓存"""
    try:
        ids_list = list(ids)
        if len(ids_list) > MAX_CACHED_IDS:
            ids_list = ids_list[-MAX_CACHED_IDS:]
        with open(PROCESSED_IDS_FILE, "w", encoding="utf-8") as f:
            json.dump({"ids": ids_list, "updated_at": datetime.now().isoformat()}, f)
    except Exception as e:
        logger.warning(f"[缓存] 保存已处理ID失败: {e}")


def extract_content_id(url, source_type=""):
    """从URL中提取内容ID"""
    if not url:
        return None
    if "twitter.com" in url or "x.com" in url:
        match = re.search(r"status/(\d+)", url)
        if match:
            return f"twitter:{match.group(1)}"
    return f"{source_type}:{url}"


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


# ==================== RSS 获取 ====================

def fetch_rss(url, timeout=30):
    """从 RSS 源获取内容"""
    try:
        cmd = [
            "curl", "-s", "-L",
            "--connect-timeout", "10",
            "--max-time", str(timeout),
            "-A", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            url,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 5)
        if result.returncode != 0:
            logger.error(f"[RSS] 获取失败: {result.stderr}")
            return None
        return result.stdout
    except Exception as e:
        logger.error(f"[RSS] 获取出错: {e}")
        return None


def clean_retweet_content(title, content):
    """清理 Twitter 转发格式"""
    if not title:
        return title, content, False, None
    rt_pattern = r'^RT\s+@?([^:]+):\s*(.+)$'
    match = re.match(rt_pattern, title, re.DOTALL)
    if match:
        original_author = match.group(1)
        original_content = match.group(2).strip()
        if not content or content.strip() == title.strip():
            content = original_content
        return original_content, content, True, original_author
    return title, content, False, None


def parse_rss(xml_content):
    """解析 RSS XML 内容"""
    items = []
    try:
        root = ET.fromstring(xml_content)
        channel = root.find("channel")
        if channel is not None:
            for item in channel.findall("item"):
                title = item.findtext("title", "").strip()
                content = item.findtext("description", "").strip()
                url = item.findtext("link", "").strip()
                pub_date = item.findtext("pubDate", "")
                source = item.findtext("author", "RSS")
                title, content, is_rt, rt_author = clean_retweet_content(title, content)
                items.append({
                    "title": title, "content": content, "url": url,
                    "source": source, "published": parse_pub_date(pub_date),
                    "_is_retweet": is_rt, "_rt_author": rt_author,
                })

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
            source = entry.findtext("atom:author/atom:name", "RSS")
            title, content, is_rt, rt_author = clean_retweet_content(title, content)
            items.append({
                "title": title, "content": content, "url": url,
                "source": source, "published": parse_pub_date(pub_date),
                "_is_retweet": is_rt, "_rt_author": rt_author,
            })
    except Exception as e:
        logger.error(f"[RSS] 解析出错: {e}")
    return items


def parse_pub_date(date_str):
    """解析各种日期格式为时间戳"""
    if not date_str:
        return int(time.time())
    date_str = date_str.strip()
    formats = [
        "%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z",
        "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            return int(dt.timestamp())
        except ValueError:
            continue
    return int(time.time())


# ==================== Inoreader API ====================

def get_inoreader_token():
    """从本地配置读取 Inoreader access token"""
    config_path = os.path.expanduser("~/.openclaw/agents/main/agent/auth-profiles.json")
    try:
        with open(config_path) as f:
            config = json.load(f)
        return config.get("inoreader", {}).get("access_token")
    except Exception as e:
        logger.error(f"[Inoreader] 无法读取token: {e}")
        return None


def fetch_inoreader_items(token, hours=24, limit=200):
    """获取 Inoreader 最近 N 小时内容"""
    since = int(time.time()) - (hours * 3600)
    url = f"{RSS_CONFIG['inoreader']['api']}/stream/contents/user/-/state/com.google/reading-list?n={limit}&ot={since}"
    try:
        headers = {"Authorization": f"Bearer {token}"}
        resp = requests.get(url, headers=headers, timeout=30)
        if resp.status_code != 200:
            logger.error(f"[Inoreader] 获取失败: HTTP {resp.status_code}")
            return []
        data = resp.json()
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
                "title": title, "content": content, "url": url,
                "source": source, "published": item.get("published", int(time.time())),
            })
        return items
    except Exception as e:
        logger.error(f"[Inoreader] 获取出错: {e}")
        return []


# ==================== 关键词预筛选 ====================

def calculate_priority_score(item):
    """计算新闻的优先级得分"""
    text = f"{item.get('title', '')} {item.get('content', '')}".lower()
    matched_keywords = []
    matched_categories = {}

    for category, keywords in PRIORITY_KEYWORDS.items():
        category_matches = []
        for keyword in keywords:
            if keyword.lower() in text:
                matched_keywords.append(keyword)
                category_matches.append(keyword)
        if category_matches:
            matched_categories[category] = category_matches

    score = len(matched_keywords) * 5
    if "ai" in matched_categories:
        score += 10
    if "bigtech" in matched_categories:
        score += 8
    if "chip" in matched_categories:
        score += 8
    if "people" in matched_categories:
        score += 7

    exclusive_keywords = ['exclusive', '独家', 'breaking', '突发', 'first look', 'just announced']
    for kw in exclusive_keywords:
        if kw.lower() in text:
            score += 8
            break

    ceo_opinion_patterns = [
        (r'\b(sam altman|greg brockman|elon musk|demis hassabis|sundar pichai|altman|brockman)\b.*\b(says|said|thinks?|believes?|predicts?|claims?|argues?|points? out|announces?|reveals?)\b', 12),
        (r'\b(says|said|thinks?|believes?|predicts?|claims?|argues?|points? out|announces?|reveals?)\b.*\b(sam altman|greg brockman|elon musk|demis hassabis|sundar pichai|altman|brockman)\b', 12),
        (r'\b(ceo|cto|chief executive|founder)\b.*\b(says|said|thinks?|believes?|predicts?|announces?|reveals?)\b', 8),
    ]
    for pattern, bonus in ceo_opinion_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            score += bonus
            matched_keywords.append(f"[CEO观点+{bonus}]")
            break

    return max(score, 0), matched_keywords, matched_categories


def keyword_pre_filter(items, min_score=5, max_items=40):
    """关键词预筛选"""
    scored_items = []
    for item in items:
        score, keywords, categories = calculate_priority_score(item)
        if score >= min_score:
            item_copy = item.copy()
            item_copy["_priority_score"] = score
            item_copy["_keywords"] = keywords
            item_copy["_categories"] = categories
            scored_items.append(item_copy)
    scored_items.sort(key=lambda x: x["_priority_score"], reverse=True)
    return scored_items[:max_items]


# ==================== AI 处理（本地 Agent 直接处理） ====================

def get_ai_prompt(items, batch_size=None):
    """生成 AI 处理提示词"""
    if batch_size is None:
        batch_size = DEFAULT_BATCH_SIZE

    items_for_ai = []
    for i, item in enumerate(items[:batch_size]):
        items_for_ai.append({
            "index": i,
            "title": item["title"],
            "content": item["content"][:400] if item["content"] else "",
            "source": item["source"],
            "url": item["url"],
        })

    prompt = f"""你是一位资深科技媒体编辑，负责筛选和加工科技新闻选题。

请对以下新闻进行批量处理，返回 JSON 格式结果：

输入新闻：
{json.dumps(items_for_ai, ensure_ascii=False, indent=2)}

处理要求：

1. **筛选选题**（S级/A+级/A级/B级），综合以下四个维度打分：
   - **话题热度**（社交转发量、讨论量、舆论爆发点）
   - **独特性**（颠覆认知/反预期/稀缺视角，而非常规进展）
   - **读者价值**（对目标读者的实际影响、认知增益、决策参考；微信是国民级APP，凡涉及微信生态的新闻读者价值自动+10分）
   - **可延伸深度**（话题是否可深挖，有无背景故事/数据/关联线索）

   四维综合得分决定级别：
   - S级（90-100分）：四维均高，必须报道。典型：AI大模型重大发布、马斯克/SpaceX重大动态、Nature/Science顶刊、AGI里程碑
   - A+级（85-89分）：至少三维突出，尤其独特性或可延伸深度强。典型：重要产品更新、反预期的行业内幕、大额融资、知名人物重要观点
   - A级（75-84分）：两维以上较好，有一定读者价值。典型：科技巨头动态、国产大模型、开源爆款、学术突破
   - B级（65-74分）：单维亮点，读者价值有限。典型：产品评测、技术解析
   - 过滤掉C级（<65分）：四维均弱，信息密度低，无独特角度

2. **生成量子位风格中文标题**：
   - 纯中文，15-35字
   - 情绪饱满，可用"刚刚"、"突发"、"炸裂"等词
   - 突出核心信息

3. **生成一句话摘要**：
   - AI基于理解生成，50-100字
   - 严禁直接复制原文
   - 不含HTML标签

4. **标注类型**：hot(热点)/ai(AI相关)/tech(科技)/business(商业)

5. **识别核心实体**（2-5个）：公司、产品、人物、技术/概念

返回格式（JSON）：
{{
  "results": [
    {{
      "index": 0,
      "score": 95,
      "level": "S",
      "title": "重磅！OpenAI发布GPT-5，能力全面升级",
      "summary": "OpenAI最新发布的大模型在多项基准测试中创下新高...",
      "type": "ai",
      "reason": "AI大模型重大发布",
      "entities": ["OpenAI", "GPT-5"]
    }}
  ]
}}

注意：
1. 只返回 JSON，不要其他解释
2. 最多选择15条最有价值的
3. 相似主题的新闻合并为一条
4. JSON字符串必须使用英文双引号
5. title/summary/reason 等文本字段内部不得出现英文双引号，如需引用请用书名号《》或单引号'代替"""

    return prompt


def process_items_with_agent(items, batch_size=None):
    """
    使用本地 Agent 直接处理新闻条目
    这个函数会在当前 Python 进程中直接调用 AI 处理，不需要外部 API
    """
    if batch_size is None:
        batch_size = DEFAULT_BATCH_SIZE

    logger.info(f"[AI] 开始处理 {len(items)} 条新闻...")

    # 生成提示词
    prompt = get_ai_prompt(items, batch_size=batch_size)

    # 保存提示词到临时文件（供调试使用）
    prompt_file = "_agent_prompt.txt"
    with open(prompt_file, "w", encoding="utf-8") as f:
        f.write(prompt)
    logger.info(f"[AI] 提示词已保存到: {prompt_file}")

    # 返回提示词和待处理条目，由外部 Agent 处理
    return {
        "prompt": prompt,
        "items": items[:batch_size],
        "prompt_file": prompt_file,
    }


def parse_agent_result(result_text, items):
    """
    解析 Agent 返回的结果
    """
    if not result_text:
        logger.error("[AI] 结果为空")
        return None

    # 尝试提取 JSON
    json_match = re.search(r'\{{.*\}}', result_text, re.DOTALL)
    if not json_match:
        # 尝试查找 ```json 代码块
        json_match = re.search(r'```json\s*(\{{.*?\}})\s*```', result_text, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            logger.error("[AI] 无法从结果中提取 JSON")
            return None
    else:
        json_str = json_match.group()

    # 解析 JSON
    data = safe_json_loads(json_str, max_retries=3, context="Agent结果")
    if not data:
        logger.error("[AI] JSON 解析失败")
        return None

    # 验证结果
    if "results" not in data:
        logger.error("[AI] 结果缺少 'results' 字段")
        return None

    results = data.get("results", [])
    if not isinstance(results, list):
        logger.error("[AI] 'results' 不是列表")
        return None

    logger.info(f"[AI] 处理完成，返回 {len(results)} 条结果")

    # 为每个结果添加 _original_index
    for result in results:
        if "index" in result:
            result["_original_index"] = result["index"]

    return results


# ==================== 数据合并与保存 ====================

def calculate_similarity(s1, s2):
    """计算两个字符串的相似度"""
    s1_lower, s2_lower = s1.lower(), s2.lower()
    if s1_lower in s2_lower or s2_lower in s1_lower:
        return 0.8
    words1 = set(re.findall(r'\b\w{{4,}}\b', s1_lower))
    words2 = set(re.findall(r'\b\w{{4,}}\b', s2_lower))
    if not words1 or not words2:
        return 0
    return len(words1 & words2) / len(words1 | words2)


def is_duplicate(item1, item2):
    """判断两条新闻是否重复"""
    if item1.get("url") == item2.get("url"):
        return True
    title_sim = calculate_similarity(item1.get("title", ""), item2.get("title", ""))
    if title_sim > 0.7:
        return True
    entities1 = set(item1.get("entities", []))
    entities2 = set(item2.get("entities", []))
    if entities1 and entities2:
        common = entities1 & entities2
        if len(common) >= 2:
            return True
    return False


def merge_news(existing, new_items):
    """合并新闻，去重"""
    merged = existing.copy()
    added = 0
    updated = 0

    for new_item in new_items:
        is_dup = False
        for existing_item in merged:
            if is_duplicate(new_item, existing_item):
                existing_links = existing_item.get("sourceLinks", [])
                new_links = new_item.get("sourceLinks", [])
                seen = {l["url"] for l in existing_links}
                for link in new_links:
                    if link["url"] not in seen:
                        existing_links.append(link)
                        seen.add(link["url"])
                existing_item["sourceLinks"] = existing_links
                existing_item["sources"] = len(existing_links)
                updated += 1
                is_dup = True
                break

        if not is_dup:
            merged.append(new_item)
            added += 1

    return merged, added, updated


def load_existing_news():
    """加载当日已有新闻"""
    today = datetime.now().strftime('%Y-%m-%d')
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
    """保存新闻数据"""
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                content = f.read()
            archive = safe_json_loads(content, max_retries=1) or {}
        else:
            archive = {}

        archive[today] = news_data

        # 只保留30天
        dates = sorted(archive.keys())
        if len(dates) > 30:
            for old_date in dates[:-30]:
                del archive[old_date]

        safe_content = safe_json_dumps(archive, ensure_ascii=False, indent=2)

        with open(DATA_FILE, "w", encoding="utf-8") as f:
            f.write(safe_content)

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

        today = datetime.now().strftime('%Y-%m-%d')
        result = subprocess.run(
            ["git", "commit", "-m", f"Update news for {today}"],
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


# ==================== 主流程 ====================

def fetch_items(source):
    """根据数据源获取内容"""
    items = []

    if source in ("twitter", "all"):
        logger.info("[Twitter] 获取 RSS 内容...")
        xml = fetch_rss(RSS_CONFIG["twitter"]["url"])
        if xml:
            twitter_items = parse_rss(xml)
            logger.info(f"[Twitter] 获取到 {len(twitter_items)} 条")
            for item in twitter_items:
                item["_source_type"] = "twitter"
            items.extend(twitter_items)

    if source in ("inoreader", "all"):
        logger.info("[Inoreader] 获取 API 内容...")
        token = get_inoreader_token()
        if token:
            inoreader_items = fetch_inoreader_items(token)
            logger.info(f"[Inoreader] 获取到 {len(inoreader_items)} 条")
            for item in inoreader_items:
                item["_source_type"] = "inoreader"
            items.extend(inoreader_items)

    return items


def main():
    parser = argparse.ArgumentParser(description="新闻选题更新脚本（本地 Agent 版）")
    parser.add_argument("--source", choices=["twitter", "inoreader", "all"], default="all",
                        help="数据源 (默认: all)")
    parser.add_argument("--batch-size", type=int, default=None,
                        help=f"批量处理大小 (默认: {DEFAULT_BATCH_SIZE})")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="显示详细日志")
    parser.add_argument("--agent-result", type=str, default=None,
                        help="传入 Agent 处理结果的 JSON 文件路径")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    logger.info("=" * 60)
    logger.info(f"开始新闻选题更新 [源: {args.source}]")
    logger.info("=" * 60)

    # 加载已处理ID
    processed_ids = load_processed_ids()
    logger.info(f"[缓存] 已加载 {len(processed_ids)} 条历史ID")

    # 1. 获取内容
    items = fetch_items(args.source)
    if not items:
        logger.error("没有获取到内容，退出")
        return

    # 2. 过滤已处理
    new_items = []
    for item in items:
        cid = extract_content_id(item.get("url"), item.get("_source_type", ""))
        if cid and cid not in processed_ids:
            new_items.append(item)

    logger.info(f"[去重] 新内容: {len(new_items)}/{len(items)} 条")

    # 3. 预告事件检查
    upcoming_news_items = []
    if UPCOMING_EVENTS_AVAILABLE:
        summary = get_pending_events_summary()
        if summary["pending"] > 0:
            logger.info(f"[预告事件] 发现 {summary['pending']} 个待处理预告")
            check_result = check_items_against_events(new_items)
            if check_result["matched"]:
                logger.info(f"[预告事件] 匹配到 {len(check_result['matched'])} 个预告事件！")
                for event, item, match_details in check_result["matched"]:
                    news_item = convert_matched_to_news(event, item, match_details)
                    upcoming_news_items.append(news_item)
                    update_event_status(event["id"], "found", news_item)
                    logger.info(f"[预告事件] 已转换: {event['title'][:50]}...")
                new_items = check_result["unmatched"]
                logger.info(f"[预告事件] 剩余未匹配新内容: {len(new_items)} 条")

        if upcoming_news_items:
            today, existing = load_existing_news()
            final_news, added, updated = merge_news(existing, upcoming_news_items)
            logger.info(f"[预告事件] 已加入 {len(upcoming_news_items)} 条落地新闻")
            if save_news(today, final_news):
                push_to_github()
                logger.info("[预告事件] 已保存到新闻列表")

    if not new_items:
        logger.info("没有新内容，退出")
        return

    # 4. 关键词预筛选
    filtered = keyword_pre_filter(new_items)
    logger.info(f"[预筛选] 保留 {len(filtered)} 条高优先级内容")

    if not filtered:
        logger.info("没有高优先级内容，退出")
        return

    # 5. AI 处理 - 本地 Agent 模式
    if args.agent_result:
        # 从文件加载 Agent 处理结果
        logger.info(f"[AI] 从文件加载处理结果: {args.agent_result}")
        try:
            with open(args.agent_result, "r", encoding="utf-8") as f:
                result_text = f.read()
            ai_results = parse_agent_result(result_text, filtered)
        except Exception as e:
            logger.error(f"[AI] 加载结果失败: {e}")
            return
    else:
        # 生成提示词，等待外部 Agent 处理
        agent_data = process_items_with_agent(filtered, batch_size=args.batch_size)

        logger.info("\n" + "=" * 60)
        logger.info("[本地 Agent 模式]")
        logger.info("=" * 60)
        logger.info(f"提示词已保存到: {agent_data['prompt_file']}")
        logger.info(f"待处理条目: {len(agent_data['items'])} 条")
        logger.info("\n请执行以下操作：")
        logger.info(f"  1. 读取文件: {agent_data['prompt_file']}")
        logger.info("  2. 将内容发送给 AI Agent 处理")
        logger.info("  3. 将返回的 JSON 保存为 _agent_result.json")
        logger.info("  4. 重新运行: python update_news_local.py --agent-result _agent_result.json")
        logger.info("=" * 60)

        # 保存待处理条目供后续使用
        with open("_agent_items.json", "w", encoding="utf-8") as f:
            json.dump(filtered, f, ensure_ascii=False, indent=2)

        return

    if not ai_results:
        logger.error("[AI] 处理结果无效")
        return

    logger.info(f"[AI] 处理完成，获得 {len(ai_results)} 条结果")

    # 6. 构建最终数据
    ai_map = {r.get("_original_index", r.get("index", 0)): r for r in ai_results}
    processed = []

    for idx, item in enumerate(filtered):
        ai_result = ai_map.get(idx, {})

        if not ai_result:
            logger.warning(f"[AI] 索引 {idx} 无对应结果: {item.get('title', '')[:40]}...")
            continue

        entities = normalize_entities(ai_result.get("entities", []))
        level = ai_result.get("level", "B")
        score = ai_result.get("score", 60)

        processed.append({
            "title": ai_result.get("title", item["title"]),
            "title_en": item["title"],
            "summary": ai_result.get("summary", ""),
            "type": ai_result.get("type", "tech"),
            "typeName": {
                "product": "产品发布",
                "funding": "融资上市",
                "personnel": "人事变动",
                "opinion": "观点访谈",
                "industry": "行业动态",
                "safety": "安全伦理",
                "research": "研究成果",
                "financial": "商业数据",
                "breaking": "突发事件",
                "tool": "工具技巧",
                "society": "社会影响",
                "hardware": "硬件基建"
            }.get(ai_result.get("type", "product"), "产品发布"),
            "score": score,
            "level": level,
            "rating": level,
            "reason": f"【{level}级】评分{score}分 | {ai_result.get('reason', '')}",
            "entities": entities,
            "url": item["url"],
            "source": item["source"],
            "sources": 1,
            "sourceLinks": [{"name": item["source"], "url": item["url"]}],
            "timestamp": int(time.time()),
            "version": generate_version(),
        })

    processed.sort(key=lambda x: x["score"], reverse=True)

    # 7. 合并并保存
    today, existing = load_existing_news()
    final_news, added, updated = merge_news(existing, processed)

    logger.info(f"[合并] 新增 {added} 条, 更新 {updated} 条")

    if save_news(today, final_news):
        push_to_github()

    # 8. 更新已处理ID
    for item in new_items:
        cid = extract_content_id(item.get("url"), item.get("_source_type", ""))
        if cid:
            processed_ids.add(cid)
    save_processed_ids(processed_ids)

    # 9. 统计
    s_count = len([t for t in final_news if t["level"] == "S"])
    a_plus_count = len([t for t in final_news if t["level"] == "A+"])
    a_count = len([t for t in final_news if t["level"] == "A"])
    b_count = len([t for t in final_news if t["level"] == "B"])

    logger.info("\n" + "=" * 60)
    logger.info("执行完成!")
    logger.info("=" * 60)
    logger.info(f"\n【选题统计】")
    logger.info(f"  S级(必报): {s_count} 条")
    logger.info(f"  A+级(重要): {a_plus_count} 条")
    logger.info(f"  A级(优先): {a_count} 条")
    logger.info(f"  B级(可选): {b_count} 条")
    logger.info(f"  总计: {len(final_news)} 条")

    if UPCOMING_EVENTS_AVAILABLE:
        summary = get_pending_events_summary()
        if summary["pending"] > 0:
            logger.info(f"\n【预告事件】")
            logger.info(f"  待处理: {summary['pending']} 个")
            for e in summary["pending_list"][:3]:
                logger.info(f"    - {e['title'][:40]}...")
        cleanup_expired_events()

    logger.info("=" * 60)

    # 清理临时文件
    for f in ["_agent_prompt.txt", "_agent_items.json", "_agent_result.json"]:
        if os.path.exists(f):
            try:
                os.remove(f)
                logger.info(f"[清理] 已删除临时文件: {f}")
            except:
                pass


if __name__ == "__main__":
    main()
