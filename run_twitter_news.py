#!/usr/bin/env python3
"""
Twitter RSS 新闻选题更新脚本 - 优化版
专为 AI 助手直接调用设计

优化内容：
1. 修复中文引号JSON解析问题
2. 支持直接调用模式（无需文件IO）
3. 改进关键词预筛选（AI for Science、具身智能）
4. 优化分级标准（S/A+/A/B/C）
5. 增强错误诊断

使用方法：
  直接调用模式: AI_DIRECT_MODE=true python run_twitter_news.py
  本地模型模式: python run_twitter_news.py
"""

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
from logging.handlers import RotatingFileHandler

# ==================== 结构化JSON日志 ====================

class StructuredJSONFormatter(logging.Formatter):
    """结构化JSON日志格式化器"""

    def __init__(self, include_timestamp=True, service_name="twitter-news"):
        super().__init__()
        self.include_timestamp = include_timestamp
        self.service_name = service_name

    def format(self, record):
        log_entry = {
            "service": self.service_name,
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
        }

        if self.include_timestamp:
            log_entry["timestamp"] = datetime.fromtimestamp(record.created).isoformat()

        if record.exc_info:
            log_entry["exc_info"] = self.formatException(record.exc_info)

        extra_fields = ['stage', 'items_count', 'duration', 'rss_url', 'response_time',
                       'items_count', 'avg_age_hours', 'errors', 'score', 'level',
                       'title', 'url', 'source', 's_count', 'a_count', 'b_count',
                       'c_count', 'multi_source', 'high_priority_count', 'total_count']

        for field in extra_fields:
            if hasattr(record, field):
                log_entry[field] = getattr(record, field)

        return json.dumps(log_entry, ensure_ascii=False)


def setup_json_logging(log_file="twitter_news_struct.log", max_bytes=10*1024*1024, backup_count=5):
    """配置结构化JSON日志"""
    logger = logging.getLogger()

    json_handler = RotatingFileHandler(
        log_file,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding='utf-8'
    )
    json_handler.setFormatter(StructuredJSONFormatter())

    logger.addHandler(json_handler)

    logger.info("结构化JSON日志已启用", extra={"stage": "init", "service": "twitter-news"})
    return logger


# ==================== Python 版本检测 ====================

def check_python_version():
    """检查 Python 版本，确保使用 Python 3"""
    if sys.version_info.major < 3:
        print("错误: 需要使用 Python 3 运行此脚本")
        sys.exit(1)
    return True

# ==================== 日志配置 ====================

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


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


def safe_json_loads(json_str, max_retries=3):
    """安全加载JSON字符串，带重试和清理机制"""
    original_str = json_str

    for attempt in range(max_retries):
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.warning(f"JSON解析失败 (尝试 {attempt + 1}/{max_retries}): {e}")

            if attempt == max_retries - 1:
                diagnosis = diagnose_json_error(original_str, e)
                logger.error(f"[JSON诊断] 错误类型: {diagnosis['error_type']}")
                if diagnosis['line']:
                    logger.error(f"[JSON诊断] 位置: 第{diagnosis['line']}行, 第{diagnosis['column']}列")
                    if 'error_line_content' in diagnosis:
                        logger.error(f"[JSON诊断] 错误行: {diagnosis['error_line_content'][:80]}")
                if diagnosis['suggestions']:
                    logger.error(f"[JSON诊断] 修复建议:")
                    for i, suggestion in enumerate(diagnosis['suggestions'], 1):
                        logger.error(f"  {i}. {suggestion}")

            if attempt == 0:
                json_str = sanitize_json_string(json_str)
            elif attempt == 1:
                json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', json_str, re.DOTALL)
                if json_match:
                    json_str = json_match.group(1)
                    json_str = sanitize_json_string(json_str)
            else:
                json_str = try_fix_json(json_str)

    logger.error(f"JSON解析失败，已达到最大重试次数")
    return None


def try_fix_json(json_str):
    """尝试修复常见的JSON格式错误"""
    if json_str.startswith('\ufeff'):
        json_str = json_str[1:]
    json_str = re.sub(r',(\s*[}\]])', r'\1', json_str)
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


# ==================== 配置（优化版） ====================

RSS_URL = "http://localhost:1200/twitter/list/2026563584311108010?filter_time=86400"
DATA_FILE = "news_data.json"

# 优化后的关键词配置
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

GITHUB_REPO = "x-reader"
GITHUB_BRANCH = "main"
PROCESSED_IDS_FILE = ".processed_tweet_ids.json"
MAX_CACHED_IDS = 5000
CACHE_RETENTION_DAYS = 30  # 缓存保留30天


# ==================== 工具函数 ====================

def load_processed_ids():
    """加载已处理的推文ID缓存（带LRU和时间清理）"""
    if not os.path.exists(PROCESSED_IDS_FILE):
        return {}

    try:
        with open(PROCESSED_IDS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        # 支持两种格式：旧版{"ids": [...] } 和新版 {"cache": {id: timestamp, ...}}
        if "cache" in data:
            cache_data = data["cache"]
        else:
            # 旧版数据迁移：将列表转换为带时间戳的字典
            now = time.time()
            cache_data = {tid: now for tid in data.get("ids", [])}

        # 清理过期缓存（超过CACHE_RETENTION_DAYS天的）
        cutoff_time = time.time() - (CACHE_RETENTION_DAYS * 24 * 3600)
        expired_ids = [tid for tid, last_used in cache_data.items() if last_used < cutoff_time]

        if expired_ids:
            logger.info(f"[缓存] 清理过期ID: {len(expired_ids)} 条（超过{CACHE_RETENTION_DAYS}天未使用）")
            for tid in expired_ids:
                del cache_data[tid]

        # 统计信息
        total_ids = len(cache_data)
        if total_ids > MAX_CACHED_IDS:
            logger.warning(f"[缓存] 缓存数量({total_ids})超过限制({MAX_CACHED_IDS})，将进行LRU清理")

        return cache_data

    except Exception as e:
        logger.warning(f"[缓存] 加载已处理ID失败: {e}")
        return {}


def save_processed_ids(cache_data):
    """
    保存已处理的推文ID缓存（LRU策略）

    Args:
        cache_data: dict {tweet_id: last_used_timestamp}
    """
    try:
        # 如果超过限制，删除最久未使用的（LRU）
        if len(cache_data) > MAX_CACHED_IDS:
            # 按最后使用时间排序
            sorted_items = sorted(cache_data.items(), key=lambda x: x[1])
            # 保留最新的MAX_CACHED_IDS条
            to_remove = len(cache_data) - MAX_CACHED_IDS
            removed_ids = [tid for tid, _ in sorted_items[:to_remove]]
            for tid in removed_ids:
                del cache_data[tid]
            logger.info(f"[缓存] LRU清理: 删除 {to_remove} 条最久未使用的ID")

        # 确保当前处理的ID有访问记录（在调用此函数前，应该已经更新了cache_data）
        # 这里只负责保存

        with open(PROCESSED_IDS_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "cache": cache_data,
                "updated_at": datetime.now().isoformat(),
                "total_count": len(cache_data)
            }, f, ensure_ascii=False, indent=2)

        logger.debug(f"[缓存] 保存成功: {len(cache_data)} 条ID")

    except Exception as e:
        logger.warning(f"[缓存] 保存已处理ID失败: {e}")


def get_cache_stats(cache_data):
    """获取缓存统计信息"""
    if not cache_data:
        return {"total": 0, "recent_1d": 0, "recent_7d": 0, "oldest": None, "newest": None}

    now = time.time()
    one_day_ago = now - 86400
    seven_days_ago = now - 7 * 86400

    timestamps = list(cache_data.values())
    recent_1d = sum(1 for ts in timestamps if ts >= one_day_ago)
    recent_7d = sum(1 for ts in timestamps if ts >= seven_days_ago)

    return {
        "total": len(cache_data),
        "recent_1d": recent_1d,
        "recent_7d": recent_7d,
        "oldest": min(timestamps) if timestamps else None,
        "newest": max(timestamps) if timestamps else None
    }


def extract_tweet_id(url):
    """从Twitter URL中提取推文ID"""
    if not url:
        return None
    match = re.search(r"status/(\d+)", url)
    if match:
        return match.group(1)
    return None


def filter_processed_items(items, cache_data):
    """
    过滤掉已处理的推文

    Args:
        items: 新闻列表
        cache_data: dict {tweet_id: last_used_timestamp}
    """
    new_items = []
    skipped_count = 0
    processed_ids_set = set(cache_data.keys())

    for item in items:
        tweet_id = extract_tweet_id(item.get("url", ""))
        if tweet_id and tweet_id in processed_ids_set:
            skipped_count += 1
            continue
        new_items.append(item)

    if skipped_count > 0:
        logger.info(f"[去重] 跳过 {skipped_count} 条已处理的推文")

    return new_items, processed_ids_set


# ==================== RSS 获取 ====================

def fetch_rss():
    """从 RSS 源获取内容"""
    try:
        cmd = [
            "curl", "-s", "-L",
            "--connect-timeout", "10",
            "--max-time", "30",
            "-A", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            RSS_URL,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=35)

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
                source = item.findtext("author", "Twitter")

                published = parse_pub_date(pub_date)

                items.append({
                    "title": title,
                    "content": content,
                    "url": url,
                    "source": source,
                    "published": published,
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
        logger.error(f"[RSS] 解析出错: {e}")

    return items


def parse_pub_date(date_str):
    """解析各种日期格式为时间戳"""
    if not date_str:
        return int(time.time())

    date_str = date_str.strip()

    rss_pattern = r"^(\w{3}, \d{2} \w{3} \d{4} \d{2}:\d{2}:\d{2}) (\w+)$"
    match = re.match(rss_pattern, date_str)
    if match:
        dt_str, tz_str = match.groups()
        try:
            dt = datetime.strptime(dt_str, "%a, %d %b %Y %H:%M:%S")
            tz_str = tz_str.upper()
            if tz_str in ("GMT", "UTC"):
                import time as time_module
                local_offset = time_module.timezone if time_module.daylight == 0 else time_module.altzone
                return int(dt.timestamp() - local_offset)
            return int(dt.timestamp())
        except ValueError:
            pass

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

    return int(time.time())


def analyze_content_freshness(items):
    """
    分析内容新鲜度分布
    返回: (最近1小时数量, 最近6小时数量, 最近24小时数量, 平均年龄小时数)
    """
    if not items:
        return 0, 0, 0, 0

    now = time.time()
    hour1 = 0
    hour6 = 0
    hour24 = 0
    ages = []

    for item in items:
        age_seconds = now - item.get("published", now)
        age_hours = age_seconds / 3600
        ages.append(age_hours)

        if age_hours <= 1:
            hour1 += 1
        if age_hours <= 6:
            hour6 += 1
        if age_hours <= 24:
            hour24 += 1

    avg_age = sum(ages) / len(ages) if ages else 0
    return hour1, hour6, hour24, avg_age


def calculate_smart_time_window(items, target_items=20, min_hours=1, max_hours=24):
    """
    智能计算时间窗口

    策略：
    - 目标：获取约 target_items 条新闻
    - 最小窗口：min_hours（默认1小时）
    - 最大窗口：max_hours（默认24小时）
    - 基于历史内容密度预测合适的窗口
    """
    if not items:
        return min_hours

    hour1, hour6, hour24, avg_age = analyze_content_freshness(items)
    total_items = len(items)

    # 估算发布频率（每小时发布多少条）
    if hour24 > 0:
        hourly_rate = hour24 / 24.0
    elif hour6 > 0:
        hourly_rate = hour6 / 6.0
    elif hour1 > 0:
        hourly_rate = hour1 / 1.0
    else:
        # 所有内容都超过1小时，使用更保守的估计
        hourly_rate = total_items / (avg_age + 0.1) if avg_age > 0 else 1.0

    # 计算所需窗口
    if hourly_rate > 0:
        estimated_window = target_items / hourly_rate
    else:
        estimated_window = min_hours

    # 应用边界限制
    window = max(min_hours, min(estimated_window, max_hours))

    # 特殊调整：如果最近1小时内容非常少，但最近6小时内容较多，说明更新频率较低
    if hour1 < 2 and hour6 >= 5:
        # 内容更新较慢，至少使用6小时窗口
        window = max(window, 6)

    # 如果最近1小时内容充足，可以使用较小窗口
    if hour1 >= target_items:
        window = min(window, 3)  # 但不要小于3小时，留有余地

    # 四舍五入到最接近的整数小时
    window_hours = round(window)

    logger.info(f"[智能窗口] 分析: 1h={hour1}, 6h={hour6}, 24h={hour24}, 频率≈{hourly_rate:.1f}/h, 目标≈{target_items}, 计算窗口={window:.1f}h → 取整={window_hours}h")

    return window_hours


def filter_recent_items(items, hours=1, smart_mode=True):
    """
    筛选最近 N 小时的内容（支持智能模式）

    Args:
        hours: 默认窗口（如果smart_mode=False则固定使用）
        smart_mode: 是否启用智能窗口计算
    """
    if smart_mode and hours == 1:  # 默认1小时窗口时才智能调整
        window_hours = calculate_smart_time_window(items)
    else:
        window_hours = hours

    cutoff = int(time.time()) - (window_hours * 3600)
    recent = [item for item in items if item["published"] >= cutoff]
    logger.info(f"[筛选] 最近 {window_hours} 小时: {len(recent)}/{len(items)} 条")
    return recent


# ==================== 关键词预筛选（优化版） ====================

def extract_priority_keywords(text):
    """从文本中提取匹配的高优先级关键词"""
    if not text:
        return [], {}

    text_lower = text.lower()
    matched_keywords = []
    matched_categories = {}

    # 短词汇（2-3字符）使用宽松匹配
    short_word_keywords = {'rl', 'pi', 'o1', 'o3', 'o4', 'gpt', 'vlm', 'moe'}

    # 精确边界匹配关键词（需要独立单词形式）
    precise_boundary_keywords = {'ai', 'ide', 'llm', 'agi', 'mcp'}

    for category, keywords in PRIORITY_KEYWORDS.items():
        category_matches = []
        for keyword in keywords:
            keyword_lower = keyword.lower()

            # 策略1: 短词汇 - 宽松子串匹配（保持原样）
            if keyword_lower in short_word_keywords:
                if keyword_lower in text_lower:
                    matched_keywords.append(keyword)
                    category_matches.append(keyword)

            # 策略2: 精确边界匹配 - 使用\b确保独立单词
            elif keyword_lower in precise_boundary_keywords:
                # 使用单词边界，不区分大小写
                pattern = r'\b' + re.escape(keyword_lower) + r'\b'
                if re.search(pattern, text_lower, re.IGNORECASE):
                    matched_keywords.append(keyword)
                    category_matches.append(keyword)

            # 策略3: 普通关键词 - 子串匹配
            else:
                if keyword_lower in text_lower:
                    matched_keywords.append(keyword)
                    category_matches.append(keyword)

        if category_matches:
            matched_categories[category] = category_matches

    return matched_keywords, matched_categories


def calculate_priority_score(item):
    """计算新闻的优先级得分"""
    text = f"{item.get('title', '')} {item.get('content', '')}"
    matched_keywords, matched_categories = extract_priority_keywords(text)

    score = 0
    score += len(matched_keywords) * 5

    if "ai" in matched_categories:
        score += 10
    if "bigtech" in matched_categories:
        score += 8
    if "chip" in matched_categories:
        score += 8
    if "product" in matched_categories:
        score += 6
    if "people" in matched_categories:
        score += 7
    if "research" in matched_categories:
        score += 6
    if "business" in matched_categories:
        score += 5

    exclusive_keywords = ['exclusive', '独家', 'breaking', '突发', 'first look',
                          'just announced', '首次', 'first time']
    text_lower = text.lower()
    for kw in exclusive_keywords:
        if kw.lower() in text_lower:
            score += 8
            matched_keywords.append(f"[独家]{kw}")
            break

    source_indicators = ['the information', 'bloomberg', 'reuters', 'techcrunch', 'nature', 'science']
    authoritative_sources = sum(1 for src in source_indicators if src.lower() in text_lower)
    if authoritative_sources >= 2:
        score += 5
        matched_keywords.append(f"[多源验证]{authoritative_sources}源")

    # 政治/军事/法律类新闻降权（除非是重大事件）
    political_keywords = ['trump', 'biden', '特朗普', '拜登', '政府', 'government', 'administration',
                          'policy', '政策', 'regulation', '监管', 'ban', '禁令']
    military_keywords = ['war', '战争', 'military', '军事', 'defense', '国防', 'weapon', '武器',
                         'attack', '攻击', 'conflict', '冲突']
    legal_keywords = ['lawsuit', '诉讼', '起诉', '被告', '原告', 'court', '法庭', 'judge', '法官',
                      'trial', '审判', 'patent', '专利', 'copyright', '版权', 'antitrust', '反垄断']

    political_count = sum(1 for kw in political_keywords if kw.lower() in text_lower)
    military_count = sum(1 for kw in military_keywords if kw.lower() in text_lower)
    legal_count = sum(1 for kw in legal_keywords if kw.lower() in text_lower)

    # 重大事件判定：多源权威报道 + 涉及科技巨头
    major_event_indicators = ['google', 'microsoft', 'apple', 'meta', 'amazon', 'openai', 'nvidia',
                              'bytedance', 'tencent', 'alibaba', '字节', '腾讯', '阿里']
    is_tech_major = any(ind in text_lower for ind in major_event_indicators)
    is_major_event = (authoritative_sources >= 2 or 'breaking' in text_lower or '突发' in text) and is_tech_major

    if not is_major_event:
        # 非重大事件时降权
        if political_count >= 2:
            score -= 15  # 政治类降权
            matched_keywords.append("[政治-降权]")
        if military_count >= 1:
            score -= 20  # 军事类大幅降权
            matched_keywords.append("[军事-降权]")
        if legal_count >= 2:
            score -= 10  # 一般法律纠纷降权
            matched_keywords.append("[法律-降权]")
        # 但保留重大法律事件（如反垄断大案）
        elif legal_count >= 1 and is_tech_major and ('antitrust' in text_lower or '反垄断' in text):
            score += 5  # 科技巨头反垄断是重大事件
            matched_keywords.append("[反垄断+]")

    return max(score, 0), matched_keywords, matched_categories


def keyword_pre_filter(items, min_priority_score=5, ensure_top_n=40):
    """关键词预筛选 - 确保重要科技动态不被遗漏"""
    if not items:
        return []

    scored_items = []
    for item in items:
        score, keywords, categories = calculate_priority_score(item)
        item_with_score = item.copy()
        item_with_score["_priority_score"] = score
        item_with_score["_matched_keywords"] = keywords
        item_with_score["_matched_categories"] = categories
        scored_items.append(item_with_score)

    scored_items.sort(key=lambda x: x["_priority_score"], reverse=True)

    high_priority = [i for i in scored_items if i["_priority_score"] >= min_priority_score]
    normal_priority = [i for i in scored_items if i["_priority_score"] < min_priority_score]

    category_counts = {}
    for item in high_priority:
        for cat in item["_matched_categories"]:
            category_counts[cat] = category_counts.get(cat, 0) + 1

    logger.info(f"[预筛选] 高优先级新闻: {len(high_priority)} 条")
    logger.info(f"[预筛选] 普通新闻: {len(normal_priority)} 条")
    if category_counts:
        logger.info(f"[预筛选] 类别分布: {category_counts}")

    for i, item in enumerate(high_priority[:10]):
        keywords_str = ", ".join(item["_matched_keywords"][:5])
        logger.info(f"  #{i+1} [{item['_priority_score']}分] {item['title'][:40]}... | 关键词: {keywords_str}")

    result = high_priority[:ensure_top_n]
    if len(result) < ensure_top_n:
        result.extend(normal_priority[:ensure_top_n - len(result)])

    for item in result:
        item["priority_score"] = item.pop("_priority_score", 0)
        item["matched_keywords"] = item.pop("_matched_keywords", [])
        item["matched_categories"] = item.pop("_matched_categories", {})

    return result


# ==================== AI 处理接口 ====================

def get_ai_processing_prompt(items):
    """生成AI处理提示词"""
    items_for_ai = []
    priority_hints = []

    for i, item in enumerate(items[:60]):
        item_data = {
            "index": i,
            "title": item["title"],
            "content": item["content"][:500] if item["content"] else "",
            "source": item["source"],
            "url": item["url"],
        }

        if item.get("matched_keywords"):
            item_data["keywords_matched"] = item["matched_keywords"][:5]
            item_data["priority_score"] = item.get("priority_score", 0)

            # 记录所有预筛选进入的新闻（不设阈值），确保AI了解所有候选
            priority_hints.append(
                f"  新闻#{i}: 匹配关键词 {item['matched_keywords'][:3]} (优先级{item.get('priority_score', 0)}分)"
            )

        items_for_ai.append(item_data)

    keyword_hint_section = ""
    if priority_hints:
        # 显示所有预筛选的新闻，让AI完整了解上下文
        display_hints = priority_hints[:min(30, len(priority_hints))]  # 最多显示30条，避免过长
        keyword_hint_section = f"""【关键词预筛选提示】以下{len(items)}条新闻已通过预筛选进入AI处理阶段（基于科技关键词匹配和优先级评分），请对全部新闻进行批量评估：
{chr(10).join(display_hints)}
(共{len(items)}条新闻，以上显示其中{len(display_hints)}条高优先级示例)

"""

    prompt = f"""你是一位资深科技媒体编辑，负责筛选和加工科技新闻选题。

{keyword_hint_section}请对以下新闻进行批量处理，返回 JSON 格式结果：

输入新闻：
{json.dumps(items_for_ai, ensure_ascii=False, indent=2)}

处理要求：

1. **筛选选题**（S级/A+级/A级/B级）：
   - S级（90-100分）：真正的里程碑事件
     * AI大模型重大发布（GPT-5、Claude 4、Gemini 2等）
     * 马斯克/SpaceX/Neuralink重大动态
     * Nature/Science/Cell顶刊发表
     * 科技巨头重大战略调整或人事变动（CEO级别）
     * AGI相关重大进展或权威预测
     * 顶级AI研究者重大开源项目
     * **独家/首发重大新闻**
     * **多源验证的重大突破**
   - A+级（85-89分）：重要但非里程碑
     * 重要产品更新（GPT-4.5、Claude 3.5重大升级）
     * 重要技术突破（如解决FrontierMath难题）
     * 知名人物重要观点/专访
     * 大额融资（5亿美元以上）
   - A级（75-84分）：
     * 科技巨头常规产品更新
     * 国产大模型重要进展
     * 开源项目爆款/Star数激增
     * 学术突破（arxiv重要论文）
   - B级（65-74分）：
     * 产品评测、体验报告
     * 技术解析、教程
   - 过滤掉C级（<65分）

   **重要降权规则**（除非是重大事件，多源权威报道+科技巨头）：
   - 政治类新闻（特朗普、拜登、政府政策等）：降权15分
   - 军事类新闻（战争、武器、冲突等）：降权20分
   - 一般法律纠纷（普通诉讼、专利纠纷）：降权10分
   - 但科技巨头反垄断大案、重大监管事件除外

2. **生成量子位风格中文标题**：
   - 纯中文，无类型前缀
   - 情绪饱满，优先使用"刚刚"、"突发"、"炸裂"、"重磅"、"首次"等词
   - 15-35字，简洁有力
   - **必须使用数字和对比**
   - 标题公式：时间敏感型、数据冲击型、权威引语型、颠覆型

3. **生成一句话摘要**（AI生成，严禁直接复制原文）：
   - 必须是AI基于理解后生成的概括，50-100字
   - 严禁直接复制或拼接原文内容
   - 严禁包含任何HTML标签、图片链接、视频链接
   - 用简洁的语言概括核心信息，突出关键数据

4. **标注类型**：hot(热点)/ai(AI相关)/tech(科技)/business(商业)

5. **识别核心实体**（2-5个）：公司、产品、人物、技术/概念

6. **添加行业标签**（1-3个）：大模型、AI Agent、多模态、AI编程、AI科研、芯片、机器人等

返回格式（JSON）：
{{
  "results": [
    {{
      "index": 0,
      "score": 95,
      "level": "S",
      "title": "重磅！Andrej Karpathy开源AgentHub：专为AI Agent打造的GitHub",
      "summary": "前特斯拉AI总监Andrej Karpathy发布开源项目AgentHub...",
      "type": "ai",
      "reason": "顶级AI研究者重大开源项目，AI Agent领域里程碑",
      "entities": ["Andrej Karpathy", "AgentHub", "开源", "AI Agent"],
      "tags": ["AI Agent", "开源"]
    }}
  ]
}}

注意：
1. 只返回 JSON，不要其他解释
2. 最多选择20条最有价值的
3. 相似主题的新闻合并为一条
4. **重要：JSON字符串必须使用英文双引号，严禁使用中文引号**
5. **重要：所有属性名必须用双引号包裹**
6. **重要：最后一个属性后不要加逗号**
"""
    return prompt


def process_with_ai(items):
    """处理新闻：筛选 + 生成标题/摘要/类型"""
    logger.info(f"[AI] 开始处理 {len(items)} 条新闻...")

    # 检查是否有本地处理结果
    result_file = "twitter_ai_result.json"
    if os.path.exists(result_file):
        try:
            with open(result_file, "r", encoding="utf-8") as f:
                content = f.read()
            data = safe_json_loads(content, max_retries=3)
            if data and "results" in data:
                ai_results = data["results"]
                backup_file = f"{result_file}.processed"
                os.rename(result_file, backup_file)
                logger.info(f"[AI] 结果文件已备份: {backup_file}")
                logger.info(f"[AI] 成功加载 {len(ai_results)} 条处理结果")
                return ai_results
        except Exception as e:
            logger.warning(f"[AI] 加载结果文件失败: {e}")

    # 没有本地结果，需要生成提示词
    logger.info("[AI] 切换到本地模型模式")
    logger.info("=" * 80)
    logger.info("[操作指引] 本地模型处理步骤：")
    logger.info("  1. 读取 twitter_ai_prompt.txt 文件（已自动生成）")
    logger.info("  2. 将内容发送给本地模型（Claude/ChatGPT等）")
    logger.info("  3. 将模型返回的 JSON 保存为 twitter_ai_result.json")
    logger.info("  4. 再次运行此脚本完成处理")
    logger.info("=" * 80)

    prompt = get_ai_processing_prompt(items)
    with open("twitter_ai_prompt.txt", "w", encoding="utf-8") as f:
        f.write(prompt)

    return None


# ==================== 去重与合并 ====================

def calculate_similarity(s1, s2):
    """计算两个字符串的 Jaccard 相似度"""
    s1_lower, s2_lower = s1.lower(), s2.lower()
    if s1_lower in s2_lower or s2_lower in s1_lower:
        return 0.8

    stop_words = {"the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with", "by", "is", "are"}

    def extract_kw(text):
        words = re.findall(r"\b\w{4,}\b", re.sub(r"[^\w\s]", " ", text.lower()))
        return set(w for w in words if w not in stop_words)

    kw1, kw2 = extract_kw(s1), extract_kw(s2)
    if not kw1 or not kw2:
        return 0
    return len(kw1 & kw2) / len(kw1 | kw2)


def is_same_event(item1, item2, time_threshold_seconds=7200):
    """
    判断两条新闻是否报道同一事件（增强版）

    匹配策略（按优先级）：
    1. Tweet ID 相同（直接同一来源）
    2. URL 相同（同一链接）
    3. 标题高度相似（Jaccard > 0.7 或 包含关系）
    4. 实体高度重叠 + 时间接近
    5. 关键词高度重叠 + 时间接近
    6. 同一主体（公司/人物）+ 主题相似 + 时间接近

    时间阈值说明：
    - 默认2小时（7200秒），因为同一产品发布/重大新闻可能在数小时内被多次报道
    - 实体高度重叠时可放宽到6小时
    """
    # 1. Tweet ID 匹配
    url1 = item1.get("url", "")
    url2 = item2.get("url", "")
    tweet_id1 = re.search(r"status/(\d+)", url1) if url1 else None
    tweet_id2 = re.search(r"status/(\d+)", url2) if url2 else None
    if tweet_id1 and tweet_id2 and tweet_id1.group(1) == tweet_id2.group(1):
        return True

    # 2. URL 直接匹配（可能是同一事件的不同链接）
    if url1 and url2 and url1 == url2:
        return True

    # 3. 标题相似度（提高阈值）
    title1 = item1.get("title", "").strip()
    title2 = item2.get("title", "").strip()
    if title1 and title2:
        if title1.lower() in title2.lower() or title2.lower() in title1.lower():
            return True
        title_sim = calculate_similarity(title1, title2)
        if title_sim > 0.7:
            return True

    # 4. 检查时间差
    time1 = item1.get("timestamp", 0)
    time2 = item2.get("timestamp", 0)
    time_diff = abs(time1 - time2)

    # 5. 实体匹配（高置信度匹配可放宽时间限制）
    entities1 = set(item1.get("entities", []))
    entities2 = set(item2.get("entities", []))
    entity_overlap_high = False

    if entities1 and entities2:
        common_entities = entities1 & entities2
        all_entities = entities1 | entities2
        if all_entities:
            overlap = len(common_entities) / len(all_entities)
            # 实体高度重叠（>=3个共同实体且重叠度>=60%）
            if len(common_entities) >= 3 and overlap >= 0.6:
                entity_overlap_high = True
                # 高置信度实体匹配可放宽到6小时
                if time_diff <= 21600:  # 6小时
                    return True
            # 中等实体重叠（>=2个共同实体且重叠度>=40%）
            elif len(common_entities) >= 2 and overlap >= 0.4:
                if time_diff <= time_threshold_seconds:
                    return True
            # 单个顶级实体（如公司、人物）+ 时间接近
            elif len(common_entities) == 1:
                important_entities = {'OpenAI', 'Anthropic', 'Google', 'Microsoft', 'Apple',
                                      'Meta', 'NVIDIA', 'Tesla', 'SpaceX', 'xAI',
                                      'Elon Musk', 'Sam Altman', 'Andrej Karpathy', 'Demis Hassabis'}
                if common_entities & important_entities and time_diff <= 3600:  # 1小时内
                    return True

    # 6. 关键词匹配（如果items有keywords字段）
    keywords1 = set(item1.get("keywords", []))
    keywords2 = set(item2.get("keywords", []))
    if keywords1 and keywords2:
        common_keywords = keywords1 & keywords2
        if len(common_keywords) >= 3 and time_diff <= time_threshold_seconds:
            return True

    # 7. 检查sourceLinks（来源链接）是否重复
    links1 = item1.get("sourceLinks", [])
    links2 = item2.get("sourceLinks", [])
    urls1 = {link.get("url", "") for link in links1 if link.get("url")}
    urls2 = {link.get("url", "") for link in links2 if link.get("url")}
    if urls1 and urls2 and (urls1 & urls2):
        return True

    # 8. 标题关键词匹配（针对产品发布类新闻的特殊处理）
    # 如果标题包含相同的产品名+版本号+核心功能词，视为同一事件
    if title1 and title2:
        # 提取版本号（如 Opus 4.6, GPT-5, Claude 4等）
        version_pattern = r'(claude|opus|sonnet|gpt|gemini|grok)[\s-]*(\d+\.?\d*)'
        v1_match = re.search(version_pattern, title1.lower())
        v2_match = re.search(version_pattern, title2.lower())

        if v1_match and v2_match:
            # 相同产品+版本
            if v1_match.group(1) == v2_match.group(1) and v1_match.group(2) == v2_match.group(2):
                # 检查是否有共同的核心功能词
                core_keywords = ['上下文', 'context', 'token', '百万', 'million', '发布', 'launch', '开放', 'available']
                common_core = [kw for kw in core_keywords if kw in title1.lower() and kw in title2.lower()]
                if common_core and time_diff <= 21600:  # 6小时内
                    return True

    # 9. 【新增】同一主体 + 主题相似度 + 时间接近
    # 用于合并同一公司/人物的多条相关新闻（如OpenClaw的多个更新、John Carmack的多条发言）
    if entities1 and entities2 and time_diff <= 86400:  # 24小时内
        # 定义关键主体（公司/产品/人物）- 包含中英文实体
        key_subjects = {'OpenClaw', 'Claude', 'OpenAI', 'Anthropic', 'Google', 'Microsoft',
                        'NVIDIA', 'Meta', 'Apple', 'Tesla', 'SpaceX', 'xAI',
                        'Elon Musk', 'Sam Altman', 'John Carmack', 'Andrej Karpathy',
                        'Jensen Huang', 'Demis Hassabis', 'Sundar Pichai',
                        '开源', 'open source', 'AI Agent', 'agent', 'mcp'}

        # 检查是否有共同的关键主体
        common_key_subjects = (entities1 & entities2) & key_subjects

        if common_key_subjects:
            # 提取标题核心词（去除停用词后的关键词）
            def extract_core_keywords(title):
                stop_words = {'刚刚', '重磅', '炸裂', '突发', '首次', '全新', '正式', '已经', '现在', '最新',
                              'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'is', 'are'}
                words = re.findall(r'[\u4e00-\u9fa5]{2,}|\b[a-zA-Z]{3,}\b', title.lower())
                return set(w for w in words if w not in stop_words)

            core_kw1 = extract_core_keywords(title1)
            core_kw2 = extract_core_keywords(title2)

            if core_kw1 and core_kw2:
                # 计算主题相似度
                common_core_kw = core_kw1 & core_kw2
                all_core_kw = core_kw1 | core_kw2

                if all_core_kw:
                    topic_sim = len(common_core_kw) / len(all_core_kw)

                    # 主题相似度 >= 30% 且至少有2个共同核心词
                    if topic_sim >= 0.30 and len(common_core_kw) >= 2:
                        return True

            # 特殊处理：检查实体中的主题词匹配
            # 如果两条新闻都有相同的主题实体（如"开源"、"AI训练"等），视为相关
            topic_entities = {'开源', 'AI训练', 'open source', 'AI Agent', 'agent', 'mcp', 'MCP',
                             '安全', 'security', '浏览器', 'browser', 'chrome'}
            common_topic_entities = (entities1 & entities2) & topic_entities
            # 要求至少2个共同主题实体，或者1个主题实体+时间非常接近（1小时内）
            if len(common_topic_entities) >= 2:
                return True
            if len(common_topic_entities) == 1 and time_diff <= 3600:  # 1小时内
                return True

            # 特殊处理：同一关键主体的多条新闻，如果在短时间内（6小时内）发布
            # 且有至少2个共同实体（非主体本身），视为相关新闻
            if time_diff <= 21600:  # 6小时内
                other_common = (entities1 & entities2) - common_key_subjects
                if len(other_common) >= 2:  # 要求至少2个其他共同实体
                    return True

            # 特殊处理：同一产品/公司的多条更新新闻（如OpenClaw的多个功能更新）
            # 如果在短时间内（12小时内）发布，且标题都包含更新相关词汇
            # 放宽条件：只要是同一产品的更新新闻（无论是否有其他共同实体），都视为相关
            if time_diff <= 43200:  # 12小时内
                update_indicators = {'发布', '更新', '新版', '升级', '推出', '上线', '实现', '开放', '集成', '支持',
                                     'launch', 'release', 'update', 'new', 'available', 'introducing', 'announced'}
                title1_has_update = any(ind in title1 for ind in update_indicators)
                title2_has_update = any(ind in title2 for ind in update_indicators)
                if title1_has_update and title2_has_update:
                    return True

    return False


def find_duplicate(new_item, existing_items):
    """检查新选题是否与已有选题重复（返回最佳匹配或None）"""
    best_match = None
    best_score = 0

    for existing in existing_items:
        # 使用改进后的is_same_event，但需要更细粒度控制
        # 这里我们计算一个匹配分数
        match_score = calculate_event_match_score(new_item, existing)
        if match_score > best_score and match_score >= 0.6:  # 阈值
            best_score = match_score
            best_match = existing

    return best_match


def calculate_event_match_score(item1, item2):
    """
    计算两条新闻的事件匹配分数 (0-1)

    综合考虑：
    - URL/Tweet ID 完全匹配: 1.0
    - 标题相似度: 0.0-1.0
    - 实体重叠度: 0.0-1.0
    - 关键词重叠度: 0.0-1.0
    - 时间接近度: 0-0.2 奖励
    - 产品版本匹配: 额外奖励
    - 同一主体+主题相似: 额外奖励
    """
    score = 0.0

    # 1. 完全匹配（权重最高）
    url1, url2 = item1.get("url", ""), item2.get("url", "")
    if url1 and url2 and url1 == url2:
        return 1.0
    tweet_id1 = re.search(r"status/(\d+)", url1) if url1 else None
    tweet_id2 = re.search(r"status/(\d+)", url2) if url2 else None
    if tweet_id1 and tweet_id2 and tweet_id1.group(1) == tweet_id2.group(1):
        return 1.0

    # 2. 时间窗口检查（放宽到24小时以支持同一主体多新闻合并）
    time1, time2 = item1.get("timestamp", 0), item2.get("timestamp", 0)
    time_diff = abs(time1 - time2)
    if time_diff > 86400:  # 超过24小时，无奖励
        time_bonus = 0
    elif time_diff > 21600:  # 6-24小时，小幅奖励
        time_bonus = 0.03
    elif time_diff > 7200:  # 2-6小时，小幅奖励
        time_bonus = 0.05
    elif time_diff > 3600:  # 1-2小时，中等奖励
        time_bonus = 0.1
    else:  # 1小时内，最高奖励
        time_bonus = 0.2

    # 3. 标题相似度
    title1, title2 = item1.get("title", "").strip(), item2.get("title", "").strip()
    if title1 and title2:
        if title1.lower() in title2.lower() or title2.lower() in title1.lower():
            score += 0.6
        else:
            title_sim = calculate_similarity(title1, title2)
            if title_sim > 0.7:
                score += 0.5
            elif title_sim > 0.5:
                score += 0.3

    # 4. 产品版本匹配（针对Claude/GPT等产品发布新闻）
    if title1 and title2:
        version_pattern = r'(claude|opus|sonnet|gpt|gemini|grok)[\s-]*(\d+\.?\d*)'
        v1_match = re.search(version_pattern, title1.lower())
        v2_match = re.search(version_pattern, title2.lower())
        if v1_match and v2_match:
            if v1_match.group(1) == v2_match.group(1) and v1_match.group(2) == v2_match.group(2):
                score += 0.25  # 相同产品+版本，高置信度
                # 检查核心功能词
                core_keywords = ['上下文', 'context', 'token', '百万', 'million', '发布', 'launch', '开放', 'available']
                common_core = [kw for kw in core_keywords if kw in title1.lower() and kw in title2.lower()]
                if common_core:
                    score += 0.15  # 额外奖励

    # 5. 实体重叠
    entities1, entities2 = set(item1.get("entities", [])), set(item2.get("entities", []))
    if entities1 and entities2:
        common = entities1 & entities2
        all_ents = entities1 | entities2
        if all_ents:
            overlap = len(common) / len(all_ents)
            if overlap >= 0.6 and len(common) >= 3:
                score += 0.35  # 高度重叠
            elif overlap >= 0.5:
                score += 0.3
            elif overlap >= 0.3 and len(common) >= 2:
                score += 0.2
            # 顶级实体奖励
            important_entities = {'OpenAI', 'Anthropic', 'Google', 'Microsoft', 'Apple',
                                  'Meta', 'NVIDIA', 'Tesla', 'SpaceX', 'xAI',
                                  'Elon Musk', 'Sam Altman', 'Andrej Karpathy', 'John Carmack',
                                  'OpenClaw', 'Claude'}
            if common & important_entities:
                score += 0.15

    # 6. 关键词重叠
    keywords1, keywords2 = set(item1.get("keywords", [])), set(item2.get("keywords", []))
    if keywords1 and keywords2:
        common_kw = keywords1 & keywords2
        if len(common_kw) >= 3:
            score += 0.2
        elif len(common_kw) >= 2:
            score += 0.1

    # 7. 【新增】同一主体+主题相似度评分（用于find_duplicate的阈值判断）
    if entities1 and entities2 and time_diff <= 86400:
        key_subjects = {'OpenClaw', 'Claude', 'OpenAI', 'Anthropic', 'Google', 'Microsoft',
                        'NVIDIA', 'Meta', 'Apple', 'Tesla', 'SpaceX', 'xAI',
                        'Elon Musk', 'Sam Altman', 'John Carmack', 'Andrej Karpathy',
                        'Jensen Huang', 'Demis Hassabis', 'Sundar Pichai',
                        '开源', 'open source', 'AI Agent', 'agent', 'mcp'}

        common_key_subjects = (entities1 & entities2) & key_subjects
        if common_key_subjects:
            # 提取标题核心词
            def extract_core_keywords(title):
                stop_words = {'刚刚', '重磅', '炸裂', '突发', '首次', '全新', '正式', '已经', '现在', '最新',
                              'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'is', 'are'}
                words = re.findall(r'[\u4e00-\u9fa5]{2,}|\b[a-zA-Z]{3,}\b', title.lower())
                return set(w for w in words if w not in stop_words)

            core_kw1 = extract_core_keywords(title1)
            core_kw2 = extract_core_keywords(title2)

            if core_kw1 and core_kw2:
                common_core_kw = core_kw1 & core_kw2
                all_core_kw = core_kw1 | core_kw2

                if all_core_kw:
                    topic_sim = len(common_core_kw) / len(all_core_kw)
                    # 主题相似度奖励
                    if topic_sim >= 0.25 and len(common_core_kw) >= 2:
                        score += 0.25  # 主题相似度高
                    elif topic_sim >= 0.15 and len(common_core_kw) >= 1:
                        score += 0.15  # 主题有一定相似

            # 主题实体匹配奖励
            topic_entities = {'开源', 'AI训练', 'open source', 'AI Agent', 'agent', 'mcp', 'MCP',
                             '安全', 'security', '浏览器', 'browser', 'chrome'}
            common_topic_entities = (entities1 & entities2) & topic_entities
            if len(common_topic_entities) >= 1:
                score += 0.2

            # 同一主体多更新奖励（12小时内都包含更新词）
            if time_diff <= 43200:
                update_indicators = {'发布', '更新', '新版', '升级', '推出', '上线', '实现', '开放', '集成', '支持',
                                     'launch', 'release', 'update', 'new', 'available', 'introducing', 'announced'}
                title1_has_update = any(ind in title1 for ind in update_indicators)
                title2_has_update = any(ind in title2 for ind in update_indicators)
                if title1_has_update and title2_has_update:
                    score += 0.25  # 提高权重，确保find_duplicate能正确识别

            # 6小时内 + 其他共同实体
            if time_diff <= 21600:
                other_common = (entities1 & entities2) - common_key_subjects
                if len(other_common) >= 2:
                    score += 0.15
                elif len(other_common) >= 1:
                    score += 0.08

    # 8. 时间奖励
    score += time_bonus

    return min(score, 1.0)


def merge_source_links(existing_links, new_links):
    """合并来源链接，去重"""
    seen_urls = {link["url"] for link in existing_links}
    merged = existing_links.copy()

    for link in new_links:
        if link["url"] not in seen_urls:
            merged.append(link)
            seen_urls.add(link["url"])

    return merged


# ==================== 版本号与数据管理 ====================

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


def save_news(today, news_data, max_file_size_mb=90):
    """保存新闻数据到 JSON 文件

    Args:
        today: 当前日期字符串
        news_data: 当天新闻数据列表
        max_file_size_mb: 最大文件大小限制（MB），默认90MB（GitHub限制100MB，留10MB余量）
    """
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                content = f.read()
            archive = safe_json_loads(content, max_retries=1) or {}
        else:
            archive = {}

        archive[today] = news_data

        # 先按日期数量限制清理（保留最近30天）
        dates = sorted(archive.keys())
        if len(dates) > 30:
            for old_date in dates[:-30]:
                del archive[old_date]
                logger.info(f"[数据清理] 删除超过30天的旧数据: {old_date}")

        # 检查文件大小，如果超过限制则删除最旧的日期数据
        max_bytes = max_file_size_mb * 1024 * 1024
        safe_content = safe_json_dumps(archive, ensure_ascii=False, indent=2)
        content_bytes = safe_content.encode('utf-8')

        while len(content_bytes) > max_bytes and len(archive) > 1:
            # 获取最旧的日期
            oldest_date = sorted(archive.keys())[0]
            # 如果最旧的日期就是今天，则删除第二天最旧的
            if oldest_date == today and len(archive) > 1:
                oldest_date = sorted(archive.keys())[1]
            elif oldest_date == today:
                # 只有今天的数据，无法删除
                break

            deleted_count = len(archive[oldest_date])
            del archive[oldest_date]
            logger.warning(f"[数据清理] 文件大小超标({len(content_bytes)/1024/1024:.1f}MB > {max_file_size_mb}MB)，删除最旧日期 {oldest_date} 的数据({deleted_count}条)")

            # 重新序列化检查大小
            safe_content = safe_json_dumps(archive, ensure_ascii=False, indent=2)
            content_bytes = safe_content.encode('utf-8')

        with open(DATA_FILE, "w", encoding="utf-8") as f:
            f.write(safe_content)

        final_size_mb = len(content_bytes) / 1024 / 1024
        logger.info(f"[数据] 已保存: {today}, {len(news_data)} 条新闻, 文件大小: {final_size_mb:.1f}MB")
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


# ==================== 健康检查 ====================

def check_rss_health():
    """检查RSS源健康状态"""
    health_info = {
        "rss_url": RSS_URL,
        "status": "unknown",
        "response_time": 0,
        "items_count": 0,
        "avg_age_hours": 0,
        "errors": []
    }

    start = time.time()
    try:
        xml_content = fetch_rss()
        health_info["response_time"] = time.time() - start

        if not xml_content:
            health_info["status"] = "error"
            health_info["errors"].append("无法获取RSS内容")
            return health_info

        items = parse_rss(xml_content)
        health_info["items_count"] = len(items)

        if items:
            now = time.time()
            ages = [now - item.get("published", now) for item in items]
            avg_age = sum(ages) / len(ages) / 3600
            health_info["avg_age_hours"] = round(avg_age, 1)

            recent_count = sum(1 for age in ages if age < 3600)
            if recent_count > 0:
                health_info["status"] = "healthy"
            else:
                health_info["status"] = "stale"
                health_info["errors"].append(f"最近1小时无新内容，平均内容年龄{avg_age:.1f}小时")
        else:
            health_info["status"] = "empty"
            health_info["errors"].append("RSS源返回空内容")

    except Exception as e:
        health_info["status"] = "error"
        health_info["errors"].append(str(e))

    return health_info


# ==================== 主流程 ====================

def main():
    check_python_version()

    # 启用结构化JSON日志
    setup_json_logging()

    timing = {
        "start": time.time(),
        "rss_fetch": 0,
        "rss_parse": 0,
        "filter": 0,
        "ai_process": 0,
        "merge": 0,
        "save": 0,
        "github": 0
    }

    logger.info("=" * 60)
    logger.info("开始 Twitter RSS 新闻选题更新...")
    logger.info("=" * 60)

    # 加载已处理的推文ID（新版返回cache dict）
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
        return

    # 2. 解析 RSS
    t0 = time.time()
    items = parse_rss(xml_content)
    timing["rss_parse"] = time.time() - t0
    logger.info(f"[RSS] 解析到 {len(items)} 条内容 (耗时: {timing['rss_parse']:.2f}s)")

    if not items:
        logger.warning("[RSS] 没有内容，退出")
        return

    # 2.5 过滤已处理的推文
    items, processed_ids_set = filter_processed_items(items, cache_data)

    # 3. 筛选最近内容（智能时间窗口）
    t0 = time.time()
    # 启用智能窗口：自动调整时间范围以获取目标数量的新闻
    # 默认目标：20条，因为预筛选后会保留约20-40条进入AI
    smart_target = int(os.getenv("SMART_WINDOW_TARGET", "20"))
    recent_items = filter_recent_items(items, hours=1, smart_mode=True)  # hours仅作为fallback
    timing["filter"] = time.time() - t0

    current_time = time.time()  # 用于缓存时间戳

    if not recent_items:
        logger.info("[筛选] 智能时间窗口内无新内容，退出")
        for item in items:
            tweet_id = extract_tweet_id(item.get("url", ""))
            if tweet_id:
                cache_data[tweet_id] = current_time
        save_processed_ids(cache_data)
        return

    # 4. 关键词预筛选
    logger.info("\n" + "-" * 40)
    logger.info("[预筛选] 执行关键词预筛选...")
    filtered_items = keyword_pre_filter(recent_items, min_priority_score=5, ensure_top_n=40)
    logger.info(f"[预筛选] 保留 {len(filtered_items)} 条新闻进入AI处理")
    logger.info("-" * 40)

    # 5. AI 处理
    t0 = time.time()
    ai_results = process_with_ai(filtered_items)
    timing["ai_process"] = time.time() - t0

    if ai_results is None:
        logger.info("\n" + "=" * 60)
        logger.info("[提示] 需要本地模型处理，请按上述指引操作")
        logger.info("=" * 60)
        return

    logger.info(f"[AI] 返回 {len(ai_results)} 条处理结果")

    if not ai_results:
        logger.warning("[AI] 处理结果为空")
        return

    # 构建最终输出
    ai_results_map = {r["index"]: r for r in ai_results if "index" in r}
    selected_items = [filtered_items[r["index"]] for r in ai_results if "index" in r and r["index"] < len(filtered_items)]

    processed = []
    for item in selected_items:
        ai_result = ai_results_map.get(filtered_items.index(item), {})
        if not ai_result:
            continue

        level = ai_result.get("level", "B")
        score = ai_result.get("score", 60)

        entities = ai_result.get("entities", [])
        if item.get("matched_keywords"):
            for kw in item["matched_keywords"][:3]:
                if kw not in entities:
                    entities.append(kw)

        tags = ai_result.get("tags", [])
        auto_tags = []
        news_type = ai_result.get("type", "tech")
        if news_type == "ai":
            auto_tags.append("AI")
        elif news_type == "business":
            auto_tags.append("商业动态")
        elif news_type == "hot":
            auto_tags.append("热点")

        all_tags = list(dict.fromkeys(auto_tags + tags))

        processed.append({
            "title": ai_result.get("title", item["title"]),
            "title_en": item["title"],
            "summary": ai_result.get("summary", "点击链接查看详情"),
            "type": news_type,
            "typeName": {"hot": "热点", "ai": "AI", "tech": "科技", "business": "商业"}.get(news_type, "科技"),
            "score": score,
            "level": level,
            "reason": f"【{level}级】评分{score}分 | {ai_result.get('reason', '')}",
            "entities": entities[:5],
            "tags": all_tags[:5],
            "url": item["url"],
            "source": item["source"],
            "sources": 1,
            "sourceLinks": [{"name": item["source"], "url": item["url"]}],
            "timestamp": int(time.time()),
            "version": generate_version(),
            "priority_score": item.get("priority_score", 0),
        })

    processed.sort(key=lambda x: x["score"], reverse=True)

    logger.info(f"[AI] 最终产出 {len(processed)} 条新闻 (耗时: {timing['ai_process']:.2f}s)")

    if not processed:
        logger.warning("[AI] 没有高潜力新闻，退出")
        return

    # 6. 加载当日已有新闻并合并（增强去重）
    t0 = time.time()
    today, existing_news = load_existing_news()

    # 合并逻辑 - 使用智能去重
    merged = existing_news.copy()
    added_count = 0
    updated_count = 0
    duplicate_count = 0

    for new_item in processed:
        duplicate = find_duplicate(new_item, merged)

        if duplicate:
            duplicate_count += 1
            existing_links = duplicate.get("sourceLinks", [])
            new_links = new_item.get("sourceLinks", [])
            merged_links = merge_source_links(existing_links, new_links)

            # 只要有新链接添加（去重后），就更新sourceLinks
            if len(merged_links) > len(existing_links):
                duplicate["sourceLinks"] = merged_links
                duplicate["sources"] = len(merged_links)
                logger.info(f"[合并] 添加新来源: {new_item['title'][:30]}... 来源数: {len(existing_links)} -> {len(merged_links)}")

            # 优先保留评分更高的版本
            if new_item.get("score", 0) > duplicate.get("score", 0):
                duplicate["score"] = new_item["score"]
                duplicate["level"] = new_item["level"]
                duplicate["reason"] = new_item["reason"]
                logger.info(f"[合并] 更新评分: {new_item['title'][:30]}... 评分: {duplicate.get('score', 0)} -> {new_item['score']}")

            # 合并实体（去重）
            existing_entities = set(duplicate.get("entities", []))
            new_entities = set(new_item.get("entities", []))
            merged_entities = list(dict.fromkeys(duplicate.get("entities", []) + new_item.get("entities", [])))
            if len(merged_entities) > len(existing_entities):
                duplicate["entities"] = merged_entities[:5]  # 最多保留5个
                logger.info(f"[合并] 更新实体: {new_item['title'][:30]}...")

            # 合并标签（去重）
            existing_tags = set(duplicate.get("tags", []))
            new_tags = set(new_item.get("tags", []))
            merged_tags = list(dict.fromkeys(duplicate.get("tags", []) + new_item.get("tags", [])))
            if len(merged_tags) > len(existing_tags):
                duplicate["tags"] = merged_tags[:5]  # 最多保留5个

            updated_count += 1
        else:
            merged.append(new_item)
            added_count += 1
            logger.info(f"[合并] 新增选题: {new_item['title'][:30]}...")

    logger.info(f"[合并] 新增 {added_count} 条, 更新 {updated_count} 条, 去重 {duplicate_count} 条")
    final_news = merged
    timing["merge"] = time.time() - t0

    # 7. 保存数据
    t0 = time.time()
    save_success = save_news(today, final_news)
    timing["save"] = time.time() - t0

    if save_success:
        logger.info("\n[GitHub] 开始推送...")
        t0 = time.time()
        push_to_github()
        timing["github"] = time.time() - t0

    # 8. 更新已处理的推文ID缓存（带LRU和时间戳）
    current_time = time.time()
    for item in filtered_items:
        tweet_id = extract_tweet_id(item.get("url", ""))
        if tweet_id:
            cache_data[tweet_id] = current_time  # 更新最后使用时间

    # 更新缓存前记录统计
    stats_before = get_cache_stats(cache_data)

    save_processed_ids(cache_data)
    stats_after = get_cache_stats(cache_data)

    logger.info(f"[缓存] 已更新 {len(processed_ids_set)} 条推文ID（总缓存: {stats_after['total']}条, 清理: {stats_before['total'] - stats_after['total']}条）")

    # 9. 统计输出
    generate_report(final_news, timing)


def generate_report(final_news, timing):
    """生成详细的执行报告"""
    if isinstance(timing, dict):
        elapsed = time.time() - timing.get("start", time.time())
        timing_details = timing
    else:
        elapsed = time.time() - timing
        timing_details = {}

    # 分级统计（支持新的A+级）
    s_count = len([t for t in final_news if t["level"] == "S"])
    a_plus_count = len([t for t in final_news if t["level"] == "A+"])
    a_count = len([t for t in final_news if t["level"] == "A"])
    b_count = len([t for t in final_news if t["level"] == "B"])
    c_count = len([t for t in final_news if t["level"] == "C"])
    multi_source = len([t for t in final_news if t.get("sources", 1) > 1])

    type_counts = {}
    for item in final_news:
        t = item.get("type", "tech")
        type_counts[t] = type_counts.get(t, 0) + 1

    tag_counts = {}
    for item in final_news:
        for tag in item.get("tags", []):
            tag_counts[tag] = tag_counts.get(tag, 0) + 1

    all_entities = set()
    for item in final_news:
        all_entities.update(item.get("entities", []))

    high_priority_count = len([t for t in final_news if t.get("priority_score", 0) >= 15])
    today_timestamp = int(time.time()) - 86400
    today_new = len([t for t in final_news if t.get("timestamp", 0) > today_timestamp])

    logger.info("\n" + "=" * 60)
    logger.info("执行完成!")
    logger.info("=" * 60)

    logger.info("\n【选题统计】")
    logger.info(f"  S级(必报): {s_count} 条")
    logger.info(f"  A+级(重要): {a_plus_count} 条")
    logger.info(f"  A级(优先): {a_count} 条")
    logger.info(f"  B级(可选): {b_count} 条")
    logger.info(f"  C级(参考): {c_count} 条")
    logger.info(f"  多源报道: {multi_source} 条")
    logger.info(f"  关键词预筛选命中: {high_priority_count} 条")
    logger.info(f"  今日新增: {today_new} 条")
    logger.info(f"  总计: {len(final_news)} 条")

    if type_counts:
        logger.info("\n【类型分布】")
        for t, count in sorted(type_counts.items(), key=lambda x: -x[1]):
            logger.info(f"  {t}: {count} 条")

    if tag_counts:
        logger.info("\n【热门标签】")
        for tag, count in sorted(tag_counts.items(), key=lambda x: -x[1])[:8]:
            logger.info(f"  {tag}: {count} 条")

    logger.info(f"\n【核心实体】({len(all_entities)}个)")
    entities_str = ", ".join(sorted(all_entities)[:15])
    if len(all_entities) > 15:
        entities_str += f" 等{len(all_entities)}个"
    logger.info(f"  {entities_str}")

    logger.info(f"\n【执行耗时】总计: {elapsed:.2f} 秒")
    if timing_details:
        logger.info("  详细分解:")
        if timing_details.get("rss_fetch"):
            logger.info(f"    RSS获取: {timing_details['rss_fetch']:.2f}s")
        if timing_details.get("rss_parse"):
            logger.info(f"    RSS解析: {timing_details['rss_parse']:.2f}s")
        if timing_details.get("filter"):
            logger.info(f"    筛选过滤: {timing_details['filter']:.2f}s")
        if timing_details.get("ai_process"):
            logger.info(f"    AI处理: {timing_details['ai_process']:.2f}s")
        if timing_details.get("merge"):
            logger.info(f"    合并去重: {timing_details['merge']:.2f}s")
        if timing_details.get("save"):
            logger.info(f"    数据保存: {timing_details['save']:.2f}s")
        if timing_details.get("github"):
            logger.info(f"    GitHub推送: {timing_details['github']:.2f}s")

    logger.info("=" * 60)


if __name__ == "__main__":
    main()
