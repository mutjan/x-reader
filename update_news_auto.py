#!/usr/bin/env python3
"""
新闻选题更新脚本 v5.2 - 全自动本地 Agent 处理
直接在 Agent 会话中处理新闻，无需 API 调用，无需手动步骤

使用方法:
  python update_news_auto.py [--source twitter|inoreader|all]

工作流程（全自动）:
  1. 获取 RSS 内容 (Twitter/Inoreader)
  2. 关键词预筛选
  3. Agent 直接处理（当前会话通过 subprocess 调用自身）
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
import tempfile

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
WORK_LOG_FILE = ".work_log.json"
MAX_CACHED_IDS = 5000
GITHUB_BRANCH = "main"

# 默认批量大小
DEFAULT_BATCH_SIZE = 30

# ==================== 关键词配置 ====================

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


# ==================== JSON 工具 ====================

def sanitize_json_string(text):
    if not isinstance(text, str):
        return text
    text = text.replace('"', '"').replace('"', '"')
    text = text.replace(''', "'").replace(''', "'")
    text = text.replace('＂', '"').replace("＇", "'")
    text = re.sub(r'([{,]\s*)([a-zA-Z_][a-zA-Z0-9_]*)(\s*:)', r'\1"\2"\3', text)
    text = re.sub(r',(\s*[}\]])', r'\1', text)
    return text


def safe_json_loads(json_str, max_retries=3, context=""):
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
    if not entities:
        return []

    entity_mapping = {
        # 公司/品牌
        "openai": "OpenAI", "OPENAI": "OpenAI",
        "anthropic": "Anthropic", "deepmind": "DeepMind",
        "google": "Google", "meta": "Meta", "microsoft": "Microsoft",
        "nvidia": "NVIDIA", "tesla": "Tesla", "spacex": "SpaceX",
        "xai": "xAI", "grok": "Grok", "chatgpt": "GPT", "chatglm": "GLM",
        "claude": "Claude", "gemini": "Gemini", "deepseek": "DeepSeek",
        "cursor": "Cursor", "github": "GitHub", "vercel": "Vercel",
        "manus ai": "Manus", "manus": "Manus", "MANUS": "Manus",
        "perplexity": "Perplexity", "midjourney": "Midjourney",
        "stability ai": "Stability AI", "stability": "Stability AI",
        "elevenlabs": "ElevenLabs", "runway": "Runway",
        "字节": "字节跳动", "bytedance": "字节跳动",
        "腾讯": "腾讯", "tencent": "腾讯",
        "阿里": "阿里巴巴", "alibaba": "阿里巴巴",
        "智谱": "智谱AI", "zhipu": "智谱AI",
        "月之暗面": "月之暗面", "moonshot": "月之暗面",
        # 产品系列（去版本号）
        "gpt-4": "GPT", "gpt-5": "GPT", "gpt4": "GPT", "gpt5": "GPT",
        "gpt-4o": "GPT", "gpt-3": "GPT", "gpt3": "GPT",
        "o1": "OpenAI", "o3": "OpenAI", "o4": "OpenAI",
        "claude 3": "Claude", "claude 3.5": "Claude", "claude 4": "Claude",
        "gemini 1.5": "Gemini", "gemini 2": "Gemini", "gemini 2.5": "Gemini",
        "gemini ultra": "Gemini", "gemini pro": "Gemini",
        "grok-2": "Grok", "grok-3": "Grok", "grok 2": "Grok", "grok 3": "Grok",
        # 人物
        "elon musk": "Elon Musk", "musk": "Elon Musk",
        "sam altman": "Sam Altman", "altman": "Sam Altman",
        "sundar pichai": "Sundar Pichai", "satya nadella": "Satya Nadella",
        "tim cook": "Tim Cook", "mark zuckerberg": "Mark Zuckerberg",
        "zuckerberg": "Mark Zuckerberg", "demis hassabis": "Demis Hassabis",
        "hassabis": "Demis Hassabis", "ilya sutskever": "Ilya Sutskever",
        "andrej karpathy": "Andrej Karpathy", "karpathy": "Andrej Karpathy",
        "dario amodei": "Dario Amodei", "fei-fei li": "李飞飞",
        "jensen huang": "Jensen Huang", "黄仁勋": "Jensen Huang",
        "李彦宏": "李彦宏", "李开复": "李开复",
        "greg brockman": "Greg Brockman", "brockman": "Greg Brockman",
        # 技术/概念
        "llm": "LLM", "ai": "AI", "agi": "AGI", "mcp": "MCP",
        "rag": "RAG", "agent": "Agent", "agents": "Agent",
        "lmm": "LMM", "vlm": "VLM", "moe": "MoE",
        "diffusion": "Diffusion", "transformer": "Transformer",
        "quantum": "Quantum", "quantum computing": "Quantum",
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
    try:
        ids_list = list(ids)
        if len(ids_list) > MAX_CACHED_IDS:
            ids_list = ids_list[-MAX_CACHED_IDS:]
        with open(PROCESSED_IDS_FILE, "w", encoding="utf-8") as f:
            json.dump({"ids": ids_list, "updated_at": datetime.now().isoformat()}, f)
    except Exception as e:
        logger.warning(f"[缓存] 保存已处理ID失败: {e}")


# ==================== 工作日志 ====================

def load_work_log():
    """加载工作日志"""
    if not os.path.exists(WORK_LOG_FILE):
        return {"entries": [], "last_execution": None}
    try:
        with open(WORK_LOG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"[工作日志] 加载失败: {e}")
        return {"entries": [], "last_execution": None}


def save_work_log(log_entry):
    """保存工作日志条目"""
    try:
        log_data = load_work_log()
        log_entry["timestamp"] = datetime.now().isoformat()
        log_data["entries"].append(log_entry)
        # 只保留最近 50 条记录
        if len(log_data["entries"]) > 50:
            log_data["entries"] = log_data["entries"][-50:]
        log_data["last_execution"] = log_entry["timestamp"]
        with open(WORK_LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(log_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"[工作日志] 保存失败: {e}")


def print_last_execution_summary():
    """打印上次执行的摘要信息"""
    log_data = load_work_log()
    if log_data["last_execution"] and log_data["entries"]:
        last_entry = log_data["entries"][-1]
        logger.info("=" * 60)
        logger.info("【上次执行摘要】")
        logger.info(f"  执行时间: {last_entry.get('timestamp', 'N/A')}")
        logger.info(f"  数据源: {last_entry.get('sources', 'N/A')}")
        logger.info(f"  获取数量: {last_entry.get('total_fetched', 0)} 条")
        logger.info(f"  新增/更新: {last_entry.get('added', 0)} / {last_entry.get('updated', 0)} 条")
        logger.info(f"  当前总计: {last_entry.get('total_news', 0)} 条")
        if last_entry.get('errors'):
            logger.info(f"  ⚠️ 上次错误: {last_entry['errors']}")
        logger.info("=" * 60)


def extract_content_id(url, source_type=""):
    if not url:
        return None
    if "twitter.com" in url or "x.com" in url:
        match = re.search(r"status/(\d+)", url)
        if match:
            return f"twitter:{match.group(1)}"
    return f"{source_type}:{url}"


def generate_version():
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
    config_path = os.path.expanduser("~/.openclaw/agents/main/agent/auth-profiles.json")
    try:
        with open(config_path) as f:
            config = json.load(f)
        return config.get("inoreader", {}).get("access_token")
    except Exception as e:
        logger.error(f"[Inoreader] 无法读取token: {e}")
        return None


def fetch_inoreader_items(token, hours=24, limit=200):
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


# ==================== AI 处理（Agent 直接处理） ====================

def generate_ai_prompt(items):
    """生成 AI 处理提示词"""
    items_for_ai = []
    for i, item in enumerate(items):
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
   - **扩展性**（事件可能引发的连锁反应和延伸报道角度，如：技术突破→产业链影响→资本市场反应→政策监管动向）

   五维综合得分决定级别：
   - S级（90-100分）：四维均高，必须报道。典型：AI大模型重大发布、马斯克/SpaceX重大动态、Nature/Science顶刊、AGI里程碑
   - A+级（85-89分）：至少三维突出，尤其独特性或可延伸深度强。典型：重要产品更新、反预期的行业内幕、大额融资、知名人物重要观点
   - A级（75-84分）：两维以上较好，有一定读者价值。典型：科技巨头动态、国产大模型、开源爆款、学术突破
   - B级（65-74分）：单维亮点，读者价值有限。典型：产品评测、技术解析
   - 过滤掉C级（<65分）：四维均弱，信息密度低，无独特角度

   **特殊降分规则**：
   - 元宇宙/Metaverse/VR/AR/MR相关内容（除非与AI大模型深度结合或有重大突破），总分自动-20分，最高不超过B级
   - 军事/政治相关内容（如涉及军方、政府打压、国际冲突等），总分自动-15分，最高不超过A级
   - 不知名公司融资新闻（公司知名度低、缺乏行业影响力），总分自动-20分，最高不超过B级
   - 一般法律诉讼/败诉/赔偿新闻（常规商业纠纷、专利诉讼等），总分自动-15分，最高不超过A级。但具有重大新闻价值的戏剧性案件除外，如"马斯克起诉OpenAI"、"重大反垄断判决"等

2. **生成量子位风格中文标题**：
   - 纯中文，15-35字
   - 情绪饱满但克制，避免过度使用"刚刚"、"突发"、"炸裂"等感叹词
   - 突出核心信息，用内容本身的新闻性吸引读者

3. **生成一句话摘要**：
   - AI基于理解生成，50-100字
   - 严禁直接复制原文
   - 不含HTML标签

4. **标注类型**（从以下12种类型中选择最贴切的一种）：
   - product(产品发布): 新产品、新功能、开源项目发布
   - funding(融资上市): 融资、IPO、并购、估值变动
   - personnel(人事变动): 高管离职/入职、团队变动、人才挖角
   - opinion(观点访谈): 行业领袖观点、深度访谈、公开发言
   - industry(行业动态): 公司战略调整、市场竞争、合作变动
   - safety(安全伦理): AI安全事件、监管政策、伦理争议
   - research(研究成果): 论文发表、技术突破、基准测试
   - financial(商业数据): 营收、用户数据、业绩报告
   - breaking(突发事件): 突发新闻、内幕消息、独家报道
   - tool(工具技巧): 开发者工具、效率应用、使用技巧
   - society(社会影响): AI对社会结构、文化现象、生活方式的影响
   - hardware(硬件基建): 芯片、算力、数据中心、硬件设备

5. **分析扩展性**：
   - 思考该事件可能引发的连锁反应和延伸报道角度
   - 例如：谷歌新技术→影响美股芯片→影响A股芯片；产品发布→竞品反应→用户迁移→市场份额变化
   - 用1-2句话简洁描述扩展角度

6. **识别核心实体**（2-5个）：公司、产品、人物、技术/概念

   **实体提取规则（重要）**：
   - **产品系列统一**：提取基础产品名，不带版本号。如 `Gemini 2.5 Pro` → `Gemini`，`GPT-4o` → `GPT`，`Claude 3.5` → `Claude`
   - **公司/品牌统一**：同一主体的不同表述统一。如 `Manus AI` 和 `Manus` 都提取为 `Manus`，`OpenAI o3` 和 `o3` 都提取为 `OpenAI`
   - **人物用全名**：如 `Sam Altman` 而非 `Altman`，`Elon Musk` 而非 `Musk`
   - **技术概念保持简洁**：如 `MCP`、`RAG`、`Agent` 而非 `Model Context Protocol`
   - **避免过度细分**：相似概念合并，如 `ChatGPT` 和 `GPT` 统一为 `GPT`

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
      "expansion": "该技术可能推动存储芯片需求增长，进而影响美股和A股相关板块走势"
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


def call_agent_direct(prompt):
    """
    直接调用当前 Agent 会话处理提示词
    通过环境变量检测是否在 LobsterAI 环境中，如果是则使用内置处理
    """
    # 检查是否在 LobsterAI 环境中
    if os.environ.get("LOBSTERAI_SESSION") or os.environ.get("__CFBundleIdentifier") == "ai.lobster.claw":
        logger.info("[Agent] 检测到 LobsterAI 环境，使用内置处理")
        # 在 LobsterAI 中，直接返回提示词，由外层 Agent 处理
        return {"mode": "lobsterai", "prompt": prompt}

    # 检查是否有可用的本地 AI
    try:
        # 尝试使用 anthropic SDK
        import anthropic
        client = anthropic.Anthropic()

        logger.info("[Agent] 使用本地 Claude 处理...")
        response = client.messages.create(
            model="claude-opus-4-5-20251101",
            max_tokens=8000,
            temperature=0.3,
            messages=[{"role": "user", "content": prompt}]
        )
        return {"mode": "local", "result": response.content[0].text}
    except ImportError:
        logger.warning("[Agent] 未安装 anthropic SDK")
    except Exception as e:
        logger.warning(f"[Agent] 本地 Claude 调用失败: {e}")

    # 回退到手动模式
    return {"mode": "manual", "prompt": prompt}


def parse_ai_result(result_text, items):
    """解析 AI 返回的结果"""
    if not result_text:
        logger.error("[AI] 结果为空")
        return None

    # 首先尝试直接解析整个文本为 JSON
    try:
        data = json.loads(result_text.strip())
        if "results" in data:
            logger.info(f"[AI] 直接解析 JSON 成功")
            results = data.get("results", [])
            for result in results:
                if "index" in result:
                    result["_original_index"] = result["index"]
            return results
    except json.JSONDecodeError:
        pass

    # 尝试从代码块中提取
    json_match = re.search(r'```json\s*(\{.*?\})\s*```', result_text, re.DOTALL)
    if json_match:
        json_str = json_match.group(1)
    else:
        # 尝试匹配最外层的大括号
        json_match = re.search(r'\{.*\}', result_text, re.DOTALL)
        if json_match:
            json_str = json_match.group()
        else:
            logger.error("[AI] 无法从结果中提取 JSON")
            return None

    data = safe_json_loads(json_str, max_retries=3, context="AI结果")
    if not data:
        logger.error("[AI] JSON 解析失败")
        return None

    if "results" not in data:
        logger.error("[AI] 结果缺少 'results' 字段")
        return None

    results = data.get("results", [])
    if not isinstance(results, list):
        logger.error("[AI] 'results' 不是列表")
        return None

    logger.info(f"[AI] 处理完成，返回 {len(results)} 条结果")

    for result in results:
        if "index" in result:
            result["_original_index"] = result["index"]

    return results


# ==================== 数据合并与保存 ====================

def calculate_similarity(s1, s2):
    """计算两段文本的相似度，支持中英文"""
    s1_lower, s2_lower = s1.lower(), s2.lower()

    # 完全包含关系
    if s1_lower in s2_lower or s2_lower in s1_lower:
        return 0.8

    # 提取英文单词（4字符以上）
    words1 = set(re.findall(r'\b\w{4,}\b', s1_lower))
    words2 = set(re.findall(r'\b\w{4,}\b', s2_lower))

    # 提取中文字符（2-gram，即连续两个中文字）
    def chinese_ngrams(text, n=2):
        chars = re.findall(r'[\u4e00-\u9fff]', text)
        return set(''.join(chars[i:i+n]) for i in range(len(chars)-n+1)) if len(chars) >= n else set()

    chinese1 = chinese_ngrams(s1_lower, 2)
    chinese2 = chinese_ngrams(s2_lower, 2)

    # 合并中英文特征
    all_features1 = words1 | chinese1
    all_features2 = words2 | chinese2

    if not all_features1 or not all_features2:
        return 0

    # 计算 Jaccard 相似度
    return len(all_features1 & all_features2) / len(all_features1 | all_features2)


def is_duplicate(item1, item2):
    if item1.get("url") == item2.get("url"):
        return True
    title_sim = calculate_similarity(item1.get("title", ""), item2.get("title", ""))
    if title_sim > 0.5:  # 降低标题相似度阈值
        return True
    # 基于摘要的相似度判断
    summary1 = item1.get("summary", "")
    summary2 = item2.get("summary", "")
    if summary1 and summary2:
        summary_sim = calculate_similarity(summary1, summary2)
        if summary_sim > 0.4:  # 降低摘要相似度阈值
            return True
    # 标题+摘要组合相似度
    combined1 = item1.get("title", "") + " " + summary1
    combined2 = item2.get("title", "") + " " + summary2
    combined_sim = calculate_similarity(combined1, combined2)
    if combined_sim > 0.3:  # 降低组合相似度阈值
        return True
    # 核心关键词匹配：提取标题中的关键实体
    def extract_key_entities(title):
        entities = set()
        # 英文品牌/产品名（大写开头或全大写）
        entities.update(re.findall(r'\b[A-Z][a-zA-Z0-9]*\b', title))
        # 数字+单位
        entities.update(re.findall(r'\b\d+\s*(?:亿美元|万|亿|美元|元)\b', title.lower()))
        # 中文核心词（从标题中提取2-4字的关键词）
        chinese_chars = re.findall(r'[\u4e00-\u9fff]{2,4}', title)
        entities.update(chinese_chars)
        return entities

    key_entities1 = extract_key_entities(item1.get("title", ""))
    key_entities2 = extract_key_entities(item2.get("title", ""))
    # 如果标题中有2个以上相同的关键实体，认为是同一新闻
    if key_entities1 and key_entities2:
        common_entities = key_entities1 & key_entities2
        if len(common_entities) >= 2:
            return True
    # 保留实体检查作为辅助手段
    entities1 = set(item1.get("entities", []))
    entities2 = set(item2.get("entities", []))
    if entities1 and entities2:
        common = entities1 & entities2
        if len(common) >= 2:
            return True
    return False


def merge_news(existing, new_items):
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
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                content = f.read()
            archive = safe_json_loads(content, max_retries=1) or {}
        else:
            archive = {}

        archive[today] = news_data
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
    parser = argparse.ArgumentParser(description="新闻选题更新脚本（全自动 Agent 版）")
    parser.add_argument("--source", choices=["twitter", "inoreader", "all"], default="all",
                        help="数据源 (默认: all)")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE,
                        help=f"批量处理大小 (默认: {DEFAULT_BATCH_SIZE})")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="显示详细日志")
    parser.add_argument("--ai-result", type=str, default=None,
                        help="传入 AI 处理结果的 JSON 文件（用于手动模式）")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # 打印上次执行摘要
    print_last_execution_summary()

    logger.info("=" * 60)
    logger.info(f"开始新闻选题更新 [源: {args.source}]")
    logger.info("=" * 60)

    # 初始化工作日志条目
    log_entry = {
        "sources": args.source,
        "total_fetched": 0,
        "new_items": 0,
        "filtered": 0,
        "ai_processed": 0,
        "added": 0,
        "updated": 0,
        "total_news": 0,
        "errors": [],
        "level_counts": {"S": 0, "A+": 0, "A": 0, "B": 0},
        "notes": []
    }

    # 1. 获取内容
    items = fetch_items(args.source)
    log_entry["total_fetched"] = len(items)
    if not items:
        log_entry["errors"].append("没有获取到内容")
        save_work_log(log_entry)
        logger.error("没有获取到内容，退出")
        return

    # 2. 过滤已处理
    processed_ids = load_processed_ids()
    logger.info(f"[缓存] 已加载 {len(processed_ids)} 条历史ID")

    new_items = []
    for item in items:
        cid = extract_content_id(item.get("url"), item.get("_source_type", ""))
        if cid and cid not in processed_ids:
            new_items.append(item)

    logger.info(f"[去重] 新内容: {len(new_items)}/{len(items)} 条")
    log_entry["new_items"] = len(new_items)

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
                new_items = check_result["unmatched"]

        if upcoming_news_items:
            today, existing = load_existing_news()
            final_news, added, updated = merge_news(existing, upcoming_news_items)
            if save_news(today, final_news):
                push_to_github()

    if not new_items:
        log_entry["notes"].append("没有新内容需要处理")
        save_work_log(log_entry)
        logger.info("没有新内容需要处理，退出")
        return

    # 4. 关键词预筛选
    filtered = keyword_pre_filter(new_items, max_items=args.batch_size)
    logger.info(f"[预筛选] 保留 {len(filtered)} 条高优先级内容")
    log_entry["filtered"] = len(filtered)

    if not filtered:
        log_entry["notes"].append("没有高优先级内容")
        save_work_log(log_entry)
        logger.info("没有高优先级内容，退出")
        return

    # 5. AI 处理
    if args.ai_result:
        # 从文件加载 AI 结果（手动模式）
        logger.info(f"[AI] 从文件加载结果: {args.ai_result}")
        try:
            with open(args.ai_result, "r", encoding="utf-8") as f:
                result_text = f.read()
            ai_results = parse_ai_result(result_text, filtered)
        except Exception as e:
            logger.error(f"[AI] 加载结果失败: {e}")
            return
    else:
        # 调用 Agent 处理
        prompt = generate_ai_prompt(filtered)
        agent_response = call_agent_direct(prompt)

        if agent_response["mode"] == "manual" or agent_response["mode"] == "lobsterai":
            # 需要手动处理
            prompt_file = "_ai_prompt.txt"
            with open(prompt_file, "w", encoding="utf-8") as f:
                f.write(agent_response["prompt"])

            logger.info("\n" + "=" * 60)
            logger.info("【请将以下内容发送给 AI Agent 处理】")
            logger.info("=" * 60)
            print("\n" + agent_response["prompt"] + "\n")
            logger.info("=" * 60)
            logger.info(f"提示词已保存到: {prompt_file}")
            logger.info("【处理完成后，将返回的 JSON 保存到 _ai_result.json】")
            logger.info("【然后运行: python update_news_auto.py --ai-result _ai_result.json】")
            logger.info("=" * 60)
            log_entry["notes"].append("需要手动处理 AI 提示词")
            save_work_log(log_entry)
            return
        else:
            # 本地处理成功
            ai_results = parse_ai_result(agent_response["result"], filtered)

    if not ai_results:
        log_entry["errors"].append("AI 处理结果无效")
        save_work_log(log_entry)
        logger.error("[AI] 处理结果无效")
        return

    logger.info(f"[AI] 处理完成，获得 {len(ai_results)} 条结果")
    log_entry["ai_processed"] = len(ai_results)

    # 6. 构建最终数据
    ai_map = {r.get("_original_index", r.get("index", 0)): r for r in ai_results}
    processed = []

    for idx, item in enumerate(filtered):
        ai_result = ai_map.get(idx, {})
        if not ai_result:
            logger.warning(f"[AI] 索引 {idx} 无对应结果")
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
            "expansion": ai_result.get("expansion", ""),
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
    log_entry["added"] = added
    log_entry["updated"] = updated

    github_success = False
    if save_news(today, final_news):
        github_success = push_to_github()

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

    log_entry["total_news"] = len(final_news)
    log_entry["level_counts"] = {"S": s_count, "A+": a_plus_count, "A": a_count, "B": b_count}
    log_entry["github_pushed"] = github_success

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
        cleanup_expired_events()

    logger.info("=" * 60)

    # 10. 保存工作日志
    save_work_log(log_entry)

    # 清理临时文件
    for f in ["_ai_prompt.txt", "_ai_result.json"]:
        if os.path.exists(f):
            try:
                os.remove(f)
            except:
                pass


if __name__ == "__main__":
    main()
