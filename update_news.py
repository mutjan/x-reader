#!/usr/bin/env python3
"""
统一新闻选题更新脚本 v4.0
整合 Twitter RSS 和 Inoreader RSS 两个数据源

使用方法:
  python update_news.py [--source twitter|inoreader|all] [--auto-ai]

参数:
  --source    指定数据源 (默认: all)
  --auto-ai   自动调用 AI 处理（需要配置 API Key）

工作流程:
  1. 获取 RSS 内容 (Twitter/Inoreader)
  2. 关键词预筛选
  3. AI 处理 (本地模型或 API)
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
        "url": "http://localhost:1200/twitter/list/2026563584311108010?filter_time=86400",
        "type": "rss",
        "name": "Twitter"
    },
    "inoreader": {
        "api": "https://www.inoreader.com/reader/api/0",
        "type": "api",
        "name": "Inoreader"
    }
}

# Moonshot API 配置
AI_CONFIG = {
    "base_url": "https://api.moonshot.cn/v1",
    "model": "kimi-k2.5",
    "api_key": os.environ.get("MOONSHOT_API_KEY", ""),
    "timeout": 120,
}

# 文件配置
DATA_FILE = "news_data.json"
PROCESSED_IDS_FILE = ".processed_ids.json"
MAX_CACHED_IDS = 5000
GITHUB_BRANCH = "main"

# ==================== JSON 安全处理（增强版） ====================

def sanitize_json_string(text):
    """清理JSON字符串中的特殊字符，特别是中文引号"""
    if not isinstance(text, str):
        return text

    # 替换中文引号为英文引号
    text = text.replace('"', '"').replace('"', '"')
    text = text.replace(''', "'").replace(''', "'")
    text = text.replace('＂', '"').replace("＇", "'")

    # 修复属性名未加引号
    text = re.sub(r'([{,]\s*)([a-zA-Z_][a-zA-Z0-9_]*)(\s*:)', r'\1"\2"\3', text)

    # 修复尾部逗号
    text = re.sub(r',(\s*[}\]])', r'\1', text)

    # 修复字符串内的换行符
    def escape_newlines_in_string(match):
        content = match.group(1)
        content = content.replace('\\', '\\\\')
        content = content.replace('\n', '\\n')
        content = content.replace('\r', '\\r')
        content = content.replace('\t', '\\t')
        return f'"{content}"'

    text = re.sub(r'"((?:[^"\\]|\\.)*)"', escape_newlines_in_string, text)

    # 移除其他控制字符
    text = ''.join(char for char in text if ord(char) >= 32 or char in '\n\r\t')

    return text


def diagnose_json_error(json_str, error):
    """诊断JSON解析错误，返回详细的错误信息和建议"""
    error_info = {
        "error_type": type(error).__name__,
        "error_msg": str(error),
        "line": None,
        "column": None,
        "suggestions": []
    }

    match = re.search(r'line (\d+) column (\d+)', str(error))
    if match:
        error_info["line"] = int(match.group(1))
        error_info["column"] = int(match.group(2))

        lines = json_str.split('\n')
        if 0 <= error_info["line"] - 1 < len(lines):
            error_line = lines[error_info["line"] - 1]
            error_info["error_line_content"] = error_line

            if '"' in error_line or '"' in error_line:
                error_info["suggestions"].append("检测到中文引号，请替换为英文引号")
            if "'" in error_line and '"' not in error_line[:error_info["column"]]:
                error_info["suggestions"].append("检测到单引号，JSON标准使用双引号")
            if re.search(r'\w+\s*:', error_line) and not re.search(r'"\w+"\s*:', error_line):
                error_info["suggestions"].append("属性名可能缺少引号")
            if re.search(r',\s*[}\]]', error_line):
                error_info["suggestions"].append("检测到尾部逗号")

    if json_str.count('{') != json_str.count('}'):
        error_info["suggestions"].append("大括号不匹配")
    if json_str.count('[') != json_str.count(']'):
        error_info["suggestions"].append("方括号不匹配")

    return error_info


def safe_json_loads(json_str, max_retries=3, context=""):
    """安全加载JSON字符串，带重试和清理机制"""
    original_str = json_str
    last_error = None

    for attempt in range(max_retries):
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            last_error = e
            logger.warning(f"JSON解析失败 [{context}] (尝试 {attempt + 1}/{max_retries}): {e}")

            if attempt == 0:
                json_str = sanitize_json_string(json_str)
            elif attempt == 1:
                # 尝试提取代码块中的JSON
                json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', json_str, re.DOTALL)
                if json_match:
                    json_str = json_match.group(1)
                    json_str = sanitize_json_string(json_str)
            else:
                # 最后尝试：修复常见错误
                json_str = try_fix_json(json_str)

    # 所有重试失败，输出诊断信息
    diagnosis = diagnose_json_error(original_str, last_error)
    logger.error(f"[JSON诊断] 错误类型: {diagnosis['error_type']}")
    if diagnosis['line']:
        logger.error(f"[JSON诊断] 位置: 第{diagnosis['line']}行, 第{diagnosis['column']}列")
        if 'error_line_content' in diagnosis:
            logger.error(f"[JSON诊断] 错误行: {diagnosis['error_line_content'][:80]}")
    if diagnosis['suggestions']:
        logger.error(f"[JSON诊断] 修复建议:")
        for i, suggestion in enumerate(diagnosis['suggestions'], 1):
            logger.error(f"  {i}. {suggestion}")

    return None


def try_fix_json(json_str):
    """尝试修复常见的JSON格式错误"""
    if json_str.startswith('\ufeff'):
        json_str = json_str[1:]
    # 移除尾部逗号
    json_str = re.sub(r',(\s*[}\]])', r'\1', json_str)
    # 给未加引号的属性名添加引号
    json_str = re.sub(r'([{,]\s*)(\w+)(\s*:)', r'\1"\2"\3', json_str)
    return json_str


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

    sanitized = sanitize_obj(obj)
    return json.dumps(sanitized, ensure_ascii=ensure_ascii, indent=indent)


# ==================== AI 调用（增强版） ====================

def call_ai_api(prompt, temperature=0.7, max_tokens=4000, max_retries=3):
    """调用 Moonshot AI API，带重试机制"""
    if not AI_CONFIG["api_key"]:
        logger.warning("[AI] 未配置 API Key")
        return None

    for attempt in range(max_retries):
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
                    "max_tokens": max_tokens,
                },
                timeout=AI_CONFIG["timeout"],
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]
        except requests.exceptions.Timeout:
            logger.warning(f"[AI] 请求超时 (尝试 {attempt + 1}/{max_retries})")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # 指数退避
        except requests.exceptions.RequestException as e:
            logger.warning(f"[AI] 请求失败 (尝试 {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
        except Exception as e:
            logger.error(f"[AI] 意外错误: {e}")
            break

    return None


def validate_ai_result(result, expected_count=None):
    """验证 AI 返回的结果是否有效"""
    if not result:
        return False, "结果为空"

    if not isinstance(result, dict):
        return False, f"结果类型错误: {type(result)}"

    if "results" not in result:
        return False, "缺少 'results' 字段"

    results = result.get("results", [])
    if not isinstance(results, list):
        return False, "'results' 不是列表"

    if expected_count and len(results) == 0:
        return False, "结果列表为空"

    # 验证每个条目的必需字段
    required_fields = ["index", "score", "level", "title", "summary", "type"]
    for i, item in enumerate(results):
        missing = [f for f in required_fields if f not in item]
        if missing:
            logger.warning(f"[AI验证] 条目 {i} 缺少字段: {missing}")

    return True, "验证通过"


def fix_ai_result(raw_result):
    """尝试修复 AI 返回的不完整结果"""
    if not raw_result:
        return None

    # 如果是字符串，尝试解析
    if isinstance(raw_result, str):
        # 尝试提取 JSON 部分
        json_match = re.search(r'\{.*\}', raw_result, re.DOTALL)
        if json_match:
            data = safe_json_loads(json_match.group(), max_retries=3, context="AI结果")
            if data:
                return data

    # 如果已经是字典，验证并修复
    if isinstance(raw_result, dict):
        # 确保有 results 字段
        if "results" not in raw_result:
            # 可能直接返回了列表
            if "index" in raw_result or (isinstance(raw_result.get("results"), list) == False):
                return {"results": [raw_result] if not isinstance(raw_result, list) else raw_result}
        return raw_result

    return None


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
                "字节", "bytedance", "腾讯", "tencent", "阿里", "alibaba",
                "智谱", "zhipu", "月之暗面", "moonshot", "kimi", "minimax", "零一万物"],
    "chip": ["blackwell", "hopper", "h100", "h200", "b100", "b200",
             "tensor", "cuda", "quantum chip", "ai chip", "ai accelerator",
             "tsmc", "intel", "amd", "gpu shortage", "compute cluster"],
    "product": ["launch", "released", "announced", "unveiled", "available now",
                "open source", "github", "paper", "demo", "重磅", "突发"],
    "people": ["elon musk", "musk", "sam altman", "sundar pichai", "satya nadella",
               "tim cook", "mark zuckerberg", "demis hassabis", "ilya sutskever",
               "andrej karpathy", "dario amodei", "fei-fei li", "李彦宏",
               "jensen huang", "黄仁勋"],
    "research": ["nature", "science", "cell", "arxiv", "breakthrough",
                 "ai for science", "ai4science", "protein folding",
                 "mathematics", "theorem proving", "frontiermath",
                 "alphaevolve", "deepmind", "alphafold", "ramsey",
                 "materials discovery", "drug design"],
    "business": ["ipo", "上市", "收购", "并购", "融资", "估值", "独角兽",
                 "funding", "valuation", "unicorn", "investment"],
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

    # Twitter
    if "twitter.com" in url or "x.com" in url:
        match = re.search(r"status/(\d+)", url)
        if match:
            return f"twitter:{match.group(1)}"

    # 通用：使用URL本身作为ID
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

                items.append({
                    "title": title,
                    "content": content,
                    "url": url,
                    "source": source,
                    "published": parse_pub_date(pub_date),
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

            items.append({
                "title": title,
                "content": content,
                "url": url,
                "source": source,
                "published": parse_pub_date(pub_date),
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
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S %Z",
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
        cmd = [
            "curl", "-s",
            "--connect-timeout", "10",
            "--max-time", "30",
            "-H", f"Authorization: Bearer {token}",
            url,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=35)

        if result.returncode != 0:
            logger.error(f"[Inoreader] 获取失败: {result.stderr}")
            return []

        data = json.loads(result.stdout)
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
                "published": item.get("published", int(time.time())),
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

    # 类别加分
    if "ai" in matched_categories:
        score += 10
    if "bigtech" in matched_categories:
        score += 8
    if "chip" in matched_categories:
        score += 8
    if "people" in matched_categories:
        score += 7

    # 独家/突发加分
    exclusive_keywords = ['exclusive', '独家', 'breaking', '突发', 'first look', 'just announced']
    for kw in exclusive_keywords:
        if kw.lower() in text:
            score += 8
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


# ==================== AI 处理 ====================

def get_ai_prompt(items):
    """生成 AI 处理提示词"""
    items_for_ai = []
    for i, item in enumerate(items[:30]):
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

1. **筛选选题**（S级/A+级/A级/B级）：
   - S级（90-100分）：AI大模型重大发布、马斯克/SpaceX重大动态、Nature/Science顶刊
   - A+级（85-89分）：重要产品更新、知名人物重要观点、大额融资
   - A级（75-84分）：科技巨头动态、国产大模型、开源爆款、学术突破
   - B级（65-74分）：产品评测、技术解析
   - 过滤掉C级（<65分）

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
4. JSON字符串必须使用英文双引号"""

    return prompt


def process_with_ai(items, auto_ai=False):
    """使用 AI 处理新闻"""
    logger.info(f"[AI] 开始处理 {len(items)} 条新闻...")

    prompt = get_ai_prompt(items)

    # 如果配置了 auto_ai 且 API Key 存在，直接调用 API
    if auto_ai and AI_CONFIG["api_key"]:
        logger.info("[AI] 自动调用 API 处理...")
        result_text = call_ai_api(prompt, max_tokens=8000)

        if result_text:
            # 解析结果
            json_match = re.search(r'\{.*\}', result_text, re.DOTALL)
            if json_match:
                data = safe_json_loads(json_match.group(), max_retries=3, context="AI API")
                if data:
                    is_valid, msg = validate_ai_result(data, expected_count=len(items))
                    if is_valid:
                        logger.info(f"[AI] API 处理成功，返回 {len(data.get('results', []))} 条结果")
                        return data.get("results", [])
                    else:
                        logger.warning(f"[AI] 结果验证失败: {msg}")

        logger.warning("[AI] API 调用失败或结果无效，切换到本地模型模式")

    # 本地模型模式：生成提示词文件
    prompt_file = "ai_prompt.txt"
    with open(prompt_file, "w", encoding="utf-8") as f:
        f.write(prompt)

    logger.info("=" * 60)
    logger.info("[本地模式] 请按以下步骤操作：")
    logger.info(f"  1. 读取 {prompt_file} 文件")
    logger.info("  2. 将内容发送给本地模型（Claude/ChatGPT等）")
    logger.info("  3. 将模型返回的 JSON 保存为 ai_result.json")
    logger.info("  4. 再次运行此脚本")
    logger.info("=" * 60)

    return None


def load_local_ai_result():
    """加载本地 AI 处理结果"""
    result_file = "ai_result.json"

    if not os.path.exists(result_file):
        return None

    try:
        with open(result_file, "r", encoding="utf-8") as f:
            content = f.read()

        data = safe_json_loads(content, max_retries=3, context="本地AI结果")
        if data:
            # 备份并删除结果文件
            backup_file = f"{result_file}.processed"
            os.rename(result_file, backup_file)
            logger.info(f"[AI] 结果文件已备份: {backup_file}")

            is_valid, msg = validate_ai_result(data)
            if is_valid:
                return data.get("results", [])
            else:
                logger.error(f"[AI] 结果验证失败: {msg}")

    except Exception as e:
        logger.error(f"[AI] 加载本地结果失败: {e}")

    return None


# ==================== 数据合并与保存 ====================

def calculate_similarity(s1, s2):
    """计算两个字符串的相似度"""
    s1_lower, s2_lower = s1.lower(), s2.lower()
    if s1_lower in s2_lower or s2_lower in s1_lower:
        return 0.8

    words1 = set(re.findall(r'\b\w{4,}\b', s1_lower))
    words2 = set(re.findall(r'\b\w{4,}\b', s2_lower))

    if not words1 or not words2:
        return 0

    return len(words1 & words2) / len(words1 | words2)


def is_duplicate(item1, item2):
    """判断两条新闻是否重复"""
    # URL 相同
    if item1.get("url") == item2.get("url"):
        return True

    # 标题相似度
    title_sim = calculate_similarity(item1.get("title", ""), item2.get("title", ""))
    if title_sim > 0.7:
        return True

    # 实体重叠
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
                # 合并来源
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
    parser = argparse.ArgumentParser(description="新闻选题更新脚本")
    parser.add_argument("--source", choices=["twitter", "inoreader", "all"], default="all",
                        help="数据源 (默认: all)")
    parser.add_argument("--auto-ai", action="store_true",
                        help="自动调用 AI API 处理")
    args = parser.parse_args()

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

    if not new_items:
        logger.info("没有新内容，退出")
        return

    # 3. 关键词预筛选
    filtered = keyword_pre_filter(new_items)
    logger.info(f"[预筛选] 保留 {len(filtered)} 条高优先级内容")

    if not filtered:
        logger.info("没有高优先级内容，退出")
        return

    # 4. AI 处理
    # 先尝试加载本地结果
    ai_results = load_local_ai_result()

    if ai_results is None:
        # 没有本地结果，进行 AI 处理
        ai_results = process_with_ai(filtered, auto_ai=args.auto_ai)

        if ai_results is None:
            logger.info("\n需要本地模型处理，请按上述指引操作")
            return

    logger.info(f"[AI] 处理完成，获得 {len(ai_results)} 条结果")

    # 5. 构建最终数据
    ai_map = {r["index"]: r for r in ai_results if "index" in r}
    processed = []

    for item in filtered:
        idx = filtered.index(item)
        ai_result = ai_map.get(idx, {})

        if not ai_result:
            continue

        processed.append({
            "title": ai_result.get("title", item["title"]),
            "title_en": item["title"],
            "summary": ai_result.get("summary", ""),
            "type": ai_result.get("type", "tech"),
            "typeName": {"hot": "热点", "ai": "AI", "tech": "科技", "business": "商业"}.get(ai_result.get("type", "tech"), "科技"),
            "score": ai_result.get("score", 60),
            "level": ai_result.get("level", "B"),
            "reason": f"【{ai_result.get('level', 'B')}级】评分{ai_result.get('score', 60)}分 | {ai_result.get('reason', '')}",
            "entities": ai_result.get("entities", []),
            "url": item["url"],
            "source": item["source"],
            "sources": 1,
            "sourceLinks": [{"name": item["source"], "url": item["url"]}],
            "timestamp": int(time.time()),
            "version": generate_version(),
        })

    processed.sort(key=lambda x: x["score"], reverse=True)

    # 6. 合并并保存
    today, existing = load_existing_news()
    final_news, added, updated = merge_news(existing, processed)

    logger.info(f"[合并] 新增 {added} 条, 更新 {updated} 条")

    if save_news(today, final_news):
        push_to_github()

    # 7. 更新已处理ID
    for item in new_items:
        cid = extract_content_id(item.get("url"), item.get("_source_type", ""))
        if cid:
            processed_ids.add(cid)
    save_processed_ids(processed_ids)

    # 8. 统计
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
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
