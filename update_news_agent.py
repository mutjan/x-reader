#!/usr/bin/env python3
"""
新闻选题更新脚本 v5.1 - 完全本地 Agent 处理
直接在 Agent 会话中处理新闻，无需 API 调用，无需手动传递文件

使用方法:
  方式1 - 全自动模式（推荐）:
    在 LobsterAI 中直接运行: python update_news_agent.py
    Agent 会自动处理所有新闻并输出结果

  方式2 - 分步模式（调试）:
    python update_news_agent.py --step fetch    # 只获取 RSS
    python update_news_agent.py --step process  # 只处理已获取的内容

工作流程:
  1. 获取 RSS 内容 (Twitter/Inoreader)
  2. 关键词预筛选
  3. Agent 直接处理（当前会话）
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
STATE_FILE = ".agent_state.json"
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


# ==================== 状态管理 ====================

def save_state(state):
    """保存处理状态"""
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"[状态] 保存失败: {e}")


def load_state():
    """加载处理状态"""
    if not os.path.exists(STATE_FILE):
        return None
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"[状态] 加载失败: {e}")
        return None


def clear_state():
    """清除处理状态"""
    if os.path.exists(STATE_FILE):
        try:
            os.remove(STATE_FILE)
        except:
            pass


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

1. **生成扩展性分析**（每条新闻都要分析）：
   - 分析该选题的延伸价值：行业影响、关联话题、后续发展可能性
   - 30-50字，说明这个话题可以往哪些方向深挖
   - 这是评分的重要参考维度

2. **筛选选题并评分**（S级/A+级/A级/B级），综合以下四个维度打分：
   - **话题热度**（社交转发量、讨论量、舆论爆发点）
   - **独特性**（颠覆认知/反预期/稀缺视角，而非常规进展）
   - **读者价值**（对目标读者的实际影响、认知增益、决策参考；微信是国民级APP，凡涉及微信生态的新闻读者价值自动+10分）
   - **可延伸深度**（基于步骤1的扩展性分析，评估话题是否可深挖）

   **降分规则（重要）**：
   - 脑机接口类（如fMRI、脑编码、神经接口、TRIBE等）：最终得分 **-5分**（受众面窄，技术落地周期长）
   - 语音识别/ASR类（如语音转文字、语音识别模型、Transcribe等）：最终得分 **-5分**（相对成熟，读者关注度较低）
   - 小众垂直模型（如特定领域专用模型，非通用大模型）：最终得分 **-3分**

   四维综合得分（应用降分后）决定级别：
   - S级（90-100分）：四维均高，必须报道。典型：AI大模型重大发布、马斯克/SpaceX重大动态、Nature/Science顶刊、AGI里程碑
   - A+级（85-89分）：至少三维突出，尤其独特性或可延伸深度强。典型：重要产品更新、反预期的行业内幕、大额融资、知名人物重要观点
   - A级（75-84分）：两维以上较好，有一定读者价值。典型：科技巨头动态、国产大模型、开源爆款、学术突破
   - B级（65-74分）：单维亮点，读者价值有限。典型：产品评测、技术解析
   - 过滤掉C级（<65分）：四维均弱，信息密度低，无独特角度

3. **生成量子位风格中文标题**：
   - 纯中文，15-35字
   - 情绪饱满，可用"刚刚"、"突发"、"炸裂"等词
   - 突出核心信息

4. **生成一句话摘要**：
   - AI基于理解生成，50-100字
   - 严禁直接复制原文
   - 不含HTML标签

5. **标注类型**：hot(热点)/ai(AI相关)/tech(科技)/business(商业)

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
      "expansion": "该发布将引发AI行业格局重塑，可能加速AGI竞赛，影响云计算市场格局和开发者生态...",
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


def process_with_agent(items, batch_size=None):
    """
    使用本地 Agent 处理新闻条目
    返回提示词，由调用方将提示词发送给 Agent 处理
    """
    if batch_size is None:
        batch_size = DEFAULT_BATCH_SIZE

    logger.info(f"[AI] 准备处理 {len(items)} 条新闻...")

    # 生成提示词
    prompt = generate_ai_prompt(items[:batch_size])

    return {
        "prompt": prompt,
        "items": items[:batch_size],
        "item_count": len(items[:batch_size]),
    }


def parse_ai_result(result_text, items):
    """解析 AI 返回的结果"""
    if not result_text:
        logger.error("[AI] 结果为空")
        return None

    # 尝试提取 JSON
    json_match = re.search(r'\{{.*\}}', result_text, re.DOTALL)
    if not json_match:
        json_match = re.search(r'```json\s*(\{{.*?\}})\s*```', result_text, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            logger.error("[AI] 无法从结果中提取 JSON")
            return None
    else:
        json_str = json_match.group()

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

    # 为每个结果添加 _original_index
    for result in results:
        if "index" in result:
            result["_original_index"] = result["index"]

    return results


# ==================== 推送前自查验证 ====================

def validate_news_item(item, index=0):
    """
    验证单条新闻的标题、摘要、实体和链接是否匹配
    返回 (is_valid, errors, warnings)
    """
    errors = []
    warnings = []

    title = item.get("title", "")
    summary = item.get("summary", "")
    url = item.get("url", "")
    entities = item.get("entities", [])
    level = item.get("level", "")

    # 1. 标题验证
    if not title:
        errors.append("标题为空")
    elif len(title) < 5:
        errors.append(f"标题过短 ({len(title)}字): {title}")
    elif len(title) > 50:
        warnings.append(f"标题过长 ({len(title)}字)")

    # 检查标题是否包含英文引号（可能导致JSON问题）
    if '"' in title:
        errors.append("标题包含英文双引号，应使用书名号或单引号")

    # 检查标题是否为纯中文（允许数字和常见标点）
    chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', title))
    if chinese_chars < len(title) * 0.3 and len(title) > 10:
        warnings.append(f"标题中文比例较低 ({chinese_chars}/{len(title)})")

    # 2. 摘要验证
    if not summary:
        errors.append("摘要为空")
    elif len(summary) < 20:
        warnings.append(f"摘要过短 ({len(summary)}字)")
    elif len(summary) > 200:
        warnings.append(f"摘要过长 ({len(summary)}字)")

    # 检查摘要是否直接复制标题
    if summary and title and summary.strip() == title.strip():
        errors.append("摘要与标题完全相同")

    # 检查摘要是否包含HTML标签
    if summary and re.search(r'<[^>]+>', summary):
        errors.append("摘要包含HTML标签")

    # 3. 实体验证
    if not entities:
        warnings.append("实体列表为空")
    elif len(entities) < 2:
        warnings.append(f"实体数量过少 ({len(entities)}个)")

    # 检查实体是否与标题/摘要匹配
    title_summary = f"{title} {summary}".lower()
    for entity in entities:
        entity_lower = entity.lower()
        # 处理常见变体
        entity_variants = [entity_lower]
        if entity_lower == "openai":
            entity_variants.extend(["gpt", "o3", "o4", "chatgpt"])
        elif entity_lower == "google":
            entity_variants.extend(["gemini", "deepmind"])
        elif entity_lower == "anthropic":
            entity_variants.extend(["claude"])

        found = any(var in title_summary for var in entity_variants)
        if not found:
            warnings.append(f"实体 '{entity}' 未在标题/摘要中出现")

    # 4. 链接验证
    if not url:
        errors.append("链接为空")
    elif not url.startswith(("http://", "https://")):
        errors.append(f"链接格式异常: {url}")
    else:
        # 检查链接域名是否与来源匹配
        source = item.get("source", "").lower()
        domain_match = False
        if "twitter" in source or "x.com" in url:
            domain_match = "twitter.com" in url or "x.com" in url
        elif "github" in source:
            domain_match = "github.com" in url

        if source and not domain_match:
            # 放宽检查，只记录警告
            if source not in url.lower():
                warnings.append(f"链接域名与来源 '{source}' 可能不匹配")

    # 5. 级别与分数一致性检查
    score = item.get("score", 0)
    if level == "S" and score < 90:
        warnings.append(f"S级新闻分数偏低 ({score}分)")
    elif level == "A+" and (score < 85 or score >= 90):
        warnings.append(f"A+级新闻分数异常 ({score}分，应在85-89之间)")
    elif level == "A" and (score < 75 or score >= 85):
        warnings.append(f"A级新闻分数异常 ({score}分，应在75-84之间)")
    elif level == "B" and (score < 65 or score >= 75):
        warnings.append(f"B级新闻分数异常 ({score}分，应在65-74之间)")

    is_valid = len(errors) == 0
    return is_valid, errors, warnings


def validate_before_push(news_data, max_items_to_check=20):
    """
    推送前自查：验证新闻数据质量
    返回 (is_valid, report)
    """
    logger.info("=" * 60)
    logger.info("【推送前自查】验证标题、摘要、实体和链接匹配性")
    logger.info("=" * 60)

    if not news_data:
        logger.warning("[自查] 新闻数据为空")
        return True, "无数据需要验证"

    # 只检查最新的条目
    items_to_check = news_data[:max_items_to_check]

    total_errors = 0
    total_warnings = 0
    invalid_items = []

    for idx, item in enumerate(items_to_check):
        is_valid, errors, warnings = validate_news_item(item, idx)

        if not is_valid:
            total_errors += len(errors)
            invalid_items.append({
                "index": idx,
                "title": item.get("title", "N/A"),
                "errors": errors,
                "warnings": warnings
            })
            logger.error(f"\n❌ [条目 {idx+1}] {item.get('title', 'N/A')[:40]}...")
            for error in errors:
                logger.error(f"   错误: {error}")

        if warnings:
            total_warnings += len(warnings)
            if is_valid:  # 只在没有错误时显示警告
                logger.warning(f"\n⚠️ [条目 {idx+1}] {item.get('title', 'N/A')[:40]}...")
                for warning in warnings:
                    logger.warning(f"   警告: {warning}")

    # 生成报告
    report_lines = [
        "=" * 60,
        "【自查报告】",
        "=" * 60,
        f"检查条目: {len(items_to_check)} 条",
        f"发现错误: {total_errors} 个",
        f"发现警告: {total_warnings} 个",
    ]

    if invalid_items:
        report_lines.append("\n【问题条目详情】")
        for item_info in invalid_items:
            report_lines.append(f"\n条目 {item_info['index']+1}: {item_info['title'][:50]}")
            for error in item_info['errors']:
                report_lines.append(f"  ❌ {error}")

    report_lines.append("=" * 60)

    if total_errors > 0:
        report_lines.append("❌ 自查未通过：存在错误，请修复后再推送")
        is_valid = False
    elif total_warnings > 0:
        report_lines.append("⚠️ 自查通过：存在警告，但无严重错误")
        is_valid = True
    else:
        report_lines.append("✅ 自查通过：所有检查项正常")
        is_valid = True

    report = "\n".join(report_lines)
    logger.info("\n" + report)

    return is_valid, report


# ==================== 数据合并与保存 ====================

def calculate_similarity(s1, s2):
    s1_lower, s2_lower = s1.lower(), s2.lower()
    if s1_lower in s2_lower or s2_lower in s1_lower:
        return 0.8
    words1 = set(re.findall(r'\b\w{{4,}}\b', s1_lower))
    words2 = set(re.findall(r'\b\w{{4,}}\b', s2_lower))
    if not words1 or not words2:
        return 0
    return len(words1 & words2) / len(words1 | words2)


def is_duplicate(item1, item2):
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


def push_to_github(force=False):
    """
    推送数据到 GitHub

    Args:
        force: 是否跳过自查直接推送（仅用于紧急修复）
    """
    try:
        # 先加载数据进行检查
        today = datetime.now().strftime('%Y-%m-%d')
        if not os.path.exists(DATA_FILE):
            logger.error("[GitHub] 数据文件不存在")
            return False

        with open(DATA_FILE, "r", encoding="utf-8") as f:
            content = f.read()
        archive = safe_json_loads(content, max_retries=1) or {}
        news_data = archive.get(today, [])

        # 推送前自查（除非强制推送）
        if not force:
            is_valid, report = validate_before_push(news_data)
            if not is_valid:
                logger.error("[GitHub] 推送被阻止：自查未通过")
                logger.error("[GitHub] 如需强制推送，请使用 force=True 参数")
                return False
        else:
            logger.warning("[GitHub] 强制推送模式，跳过自查")

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


def step_fetch(source):
    """步骤1：获取 RSS 内容"""
    logger.info("=" * 60)
    logger.info("步骤 1/3: 获取 RSS 内容")
    logger.info("=" * 60)

    processed_ids = load_processed_ids()
    logger.info(f"[缓存] 已加载 {len(processed_ids)} 条历史ID")

    items = fetch_items(source)
    if not items:
        logger.error("没有获取到内容")
        return None

    # 过滤已处理
    new_items = []
    for item in items:
        cid = extract_content_id(item.get("url"), item.get("_source_type", ""))
        if cid and cid not in processed_ids:
            new_items.append(item)

    logger.info(f"[去重] 新内容: {len(new_items)}/{len(items)} 条")

    # 预告事件检查
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
                push_to_github(force=False)

    if not new_items:
        logger.info("没有新内容需要处理")
        return None

    # 关键词预筛选
    filtered = keyword_pre_filter(new_items)
    logger.info(f"[预筛选] 保留 {len(filtered)} 条高优先级内容")

    if not filtered:
        logger.info("没有高优先级内容")
        return None

    # 保存状态
    state = {
        "step": "fetch_complete",
        "filtered_items": filtered,
        "new_items": new_items,
        "timestamp": datetime.now().isoformat(),
    }
    save_state(state)
    logger.info(f"[状态] 已保存，等待 AI 处理")

    return state


def step_process():
    """步骤2：生成提示词供 Agent 处理"""
    logger.info("=" * 60)
    logger.info("步骤 2/3: 准备 AI 处理")
    logger.info("=" * 60)

    state = load_state()
    if not state or state.get("step") != "fetch_complete":
        logger.error("[错误] 没有待处理的状态，请先运行 --step fetch")
        return None

    filtered = state.get("filtered_items", [])
    if not filtered:
        logger.error("[错误] 没有待处理的条目")
        return None

    # 准备 Agent 处理
    agent_data = process_with_agent(filtered)

    # 更新状态
    state["step"] = "waiting_agent"
    state["prompt"] = agent_data["prompt"]
    state["item_count"] = agent_data["item_count"]
    save_state(state)

    logger.info("\n" + "=" * 60)
    logger.info("【请将以下内容发送给 AI Agent 处理】")
    logger.info("=" * 60)
    print("\n" + agent_data["prompt"] + "\n")
    logger.info("=" * 60)
    logger.info("【处理完成后，将返回的 JSON 保存到 _agent_response.json，然后运行 --step finalize】")
    logger.info("=" * 60)

    return state


def step_finalize(agent_response_file="_agent_response.json", force=False):
    """步骤3：解析 Agent 结果并保存"""
    logger.info("=" * 60)
    logger.info("步骤 3/3: 解析结果并保存")
    logger.info("=" * 60)

    state = load_state()
    if not state:
        logger.error("[错误] 没有状态文件")
        return False

    filtered = state.get("filtered_items", [])
    new_items = state.get("new_items", [])

    # 读取 Agent 响应
    if not os.path.exists(agent_response_file):
        logger.error(f"[错误] 找不到 Agent 响应文件: {agent_response_file}")
        return False

    try:
        with open(agent_response_file, "r", encoding="utf-8") as f:
            result_text = f.read()
    except Exception as e:
        logger.error(f"[错误] 读取响应文件失败: {e}")
        return False

    # 解析结果
    ai_results = parse_ai_result(result_text, filtered)
    if not ai_results:
        logger.error("[错误] 无法解析 AI 结果")
        return False

    # 构建最终数据
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
            "expansion": ai_result.get("expansion", ""),
            "type": ai_result.get("type", "tech"),
            "typeName": {"hot": "热点", "ai": "AI", "tech": "科技", "business": "商业"}.get(ai_result.get("type", "tech"), "科技"),
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

    # 合并并保存
    today, existing = load_existing_news()
    final_news, added, updated = merge_news(existing, processed)

    logger.info(f"[合并] 新增 {added} 条, 更新 {updated} 条")

    if save_news(today, final_news):
        push_to_github(force=force)

    # 更新已处理ID
    processed_ids = load_processed_ids()
    for item in new_items:
        cid = extract_content_id(item.get("url"), item.get("_source_type", ""))
        if cid:
            processed_ids.add(cid)
    save_processed_ids(processed_ids)

    # 统计
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
        cleanup_expired_events()

    logger.info("=" * 60)

    # 清理状态
    clear_state()

    # 清理临时文件
    for f in ["_agent_response.json"]:
        if os.path.exists(f):
            try:
                os.remove(f)
            except:
                pass

    return True


def main():
    parser = argparse.ArgumentParser(description="新闻选题更新脚本（Agent 版）")
    parser.add_argument("--source", choices=["twitter", "inoreader", "all"], default="all",
                        help="数据源 (默认: all)")
    parser.add_argument("--step", choices=["fetch", "process", "finalize"], default=None,
                        help="执行指定步骤 (默认: 全部执行)")
    parser.add_argument("--agent-response", type=str, default="_agent_response.json",
                        help="Agent 响应文件路径 (默认: _agent_response.json)")
    parser.add_argument("--force", "-f", action="store_true",
                        help="强制推送，跳过自查验证（仅用于紧急修复）")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="显示详细日志")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # 如果指定了步骤，执行单步
    if args.step:
        if args.step == "fetch":
            step_fetch(args.source)
        elif args.step == "process":
            step_process()
        elif args.step == "finalize":
            step_finalize(args.agent_response, force=args.force)
        return

    # 自动模式：检测当前状态并执行相应步骤
    state = load_state()

    if not state:
        # 全新开始
        state = step_fetch(args.source)
        if state:
            step_process()
    elif state.get("step") == "fetch_complete":
        # 等待 AI 处理
        logger.info("[恢复] 检测到已获取的数据，继续处理...")
        step_process()
    elif state.get("step") == "waiting_agent":
        # 等待 Agent 响应
        logger.info("[恢复] 等待 Agent 处理结果...")
        logger.info(f"提示词已准备好，请查看之前输出的提示词并发送给 AI Agent")
        logger.info(f"处理完成后，将 JSON 结果保存到 _agent_response.json")
        logger.info(f"然后运行: python update_news_agent.py --step finalize")
    else:
        # 未知状态，重新开始
        clear_state()
        state = step_fetch(args.source)
        if state:
            step_process()


if __name__ == "__main__":
    main()
