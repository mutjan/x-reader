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
        "url": "http://localhost:1200/twitter/list/2026563584311108010?filter_time=86400&includeReplies=1",
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

# AI 处理文件配置（按数据源区分）
def get_ai_files(source="default"):
    """获取 AI 处理相关文件路径（按数据源区分）"""
    source_prefix = source if source else "default"
    return {
        "prompt": f"{source_prefix}_ai_prompt.txt",
        "result": f"{source_prefix}_ai_result.json",
        "lock": f"{source_prefix}_ai_processing.lock",
        "backup": f"{source_prefix}_ai_result.json.processed",
        "cache": f"{source_prefix}_ai_cache.json",
    }

# 默认批量大小
DEFAULT_BATCH_SIZE = 30

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


# ==================== 文件锁定机制 ====================

import fcntl

def acquire_lock(lock_file, timeout=5):
    """获取文件锁，防止并发处理"""
    try:
        fd = open(lock_file, "w")
        fcntl.flock(fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        fd.write(str(os.getpid()))
        fd.flush()
        return fd
    except (IOError, OSError):
        logger.warning(f"[锁定] 无法获取锁，可能已有进程在处理: {lock_file}")
        return None

def release_lock(fd):
    """释放文件锁"""
    if fd:
        try:
            fcntl.flock(fd.fileno(), fcntl.LOCK_UN)
            fd.close()
        except Exception as e:
            logger.warning(f"[锁定] 释放锁失败: {e}")


def check_processing_state(source="default"):
    """检查是否有正在进行的处理任务"""
    files = get_ai_files(source)
    lock_file = files["lock"]
    result_file = files["result"]
    prompt_file = files["prompt"]

    # 检查是否有锁文件
    if os.path.exists(lock_file):
        try:
            with open(lock_file, "r") as f:
                pid = f.read().strip()
            # 检查进程是否还在运行
            if pid and os.path.exists(f"/proc/{pid}"):
                logger.warning(f"[恢复] 检测到正在进行的处理 (PID: {pid})")
                return "running", files
            else:
                logger.info(f"[恢复] 发现残留锁文件，进程已结束")
                os.remove(lock_file)
        except Exception:
            pass

    # 检查是否有未处理的结果文件
    if os.path.exists(result_file):
        logger.info(f"[恢复] 发现未处理的结果文件: {result_file}")
        return "result_pending", files

    # 检查是否有 prompt 文件但没有结果
    if os.path.exists(prompt_file):
        logger.info(f"[恢复] 发现未处理的 prompt 文件: {prompt_file}")
        return "prompt_pending", files

    return "idle", files


def cleanup_processing_files(source="default"):
    """清理处理相关的临时文件"""
    files = get_ai_files(source)
    for key in ["lock", "prompt"]:
        filepath = files[key]
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
                logger.info(f"[清理] 已删除: {filepath}")
            except Exception as e:
                logger.warning(f"[清理] 删除失败 {filepath}: {e}")


# ==================== AI 结果缓存 ====================

def get_cache_key(item):
    """生成新闻条目的缓存键"""
    content = f"{item.get('title', '')}_{item.get('url', '')}"
    import hashlib
    return hashlib.md5(content.encode()).hexdigest()[:16]


def load_ai_cache(source="default"):
    """加载 AI 处理结果缓存"""
    files = get_ai_files(source)
    cache_file = files["cache"]

    if not os.path.exists(cache_file):
        return {}

    try:
        with open(cache_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"[缓存] 加载缓存失败: {e}")
        return {}


def save_ai_cache(cache, source="default"):
    """保存 AI 处理结果缓存"""
    files = get_ai_files(source)
    cache_file = files["cache"]

    try:
        # 只保留最近100条缓存
        if len(cache) > 100:
            # 按时间戳排序，保留最新的
            sorted_items = sorted(cache.items(), key=lambda x: x[1].get("_cached_at", 0), reverse=True)
            cache = dict(sorted_items[:100])

        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"[缓存] 保存缓存失败: {e}")


def get_cached_result(item, cache):
    """从缓存获取处理结果"""
    key = get_cache_key(item)
    if key in cache:
        cached = cache[key]
        # 检查缓存是否过期（7天）
        if time.time() - cached.get("_cached_at", 0) < 7 * 24 * 3600:
            logger.debug(f"[缓存] 命中: {item.get('title', '')[:30]}...")
            return cached.get("result")
    return None


def cache_result(item, result, cache):
    """缓存处理结果"""
    key = get_cache_key(item)
    cache[key] = {
        "_cached_at": int(time.time()),
        "result": result
    }


# ==================== 实体标准化 ====================

def normalize_entities(entities):
    """标准化实体列表：统一大小写、去重、过滤"""
    if not entities:
        return []

    # 标准化映射表（常见实体）
    entity_mapping = {
        # 公司
        "openai": "OpenAI",
        "OPENAI": "OpenAI",
        "anthropic": "Anthropic",
        "deepmind": "DeepMind",
        "google": "Google",
        "meta": "Meta",
        "microsoft": "Microsoft",
        "nvidia": "NVIDIA",
        "tesla": "Tesla",
        "spacex": "SpaceX",
        "xai": "xAI",
        "grok": "Grok",
        "chatgpt": "ChatGPT",
        "claude": "Claude",
        "gemini": "Gemini",
        "deepseek": "DeepSeek",
        "cursor": "Cursor",
        "github": "GitHub",
        "vercel": "Vercel",

        # 人物
        "elon musk": "Elon Musk",
        "musk": "Elon Musk",
        "sam altman": "Sam Altman",
        "altman": "Sam Altman",
        "sundar pichai": "Sundar Pichai",
        "satya nadella": "Satya Nadella",
        "tim cook": "Tim Cook",
        "mark zuckerberg": "Mark Zuckerberg",
        "zuckerberg": "Mark Zuckerberg",
        "demis hassabis": "Demis Hassabis",
        "hassabis": "Demis Hassabis",
        "ilya sutskever": "Ilya Sutskever",
        "andrej karpathy": "Andrej Karpathy",
        "karpathy": "Andrej Karpathy",
        "dario amodei": "Dario Amodei",
        "fei-fei li": "李飞飞",
        "jensen huang": "Jensen Huang",
        "黄仁勋": "Jensen Huang",

        # 技术/产品
        "gpt-4": "GPT-4",
        "gpt-5": "GPT-5",
        "gpt4": "GPT-4",
        "gpt5": "GPT-5",
        "llm": "LLM",
        "ai": "AI",
        "agi": "AGI",
        "mcp": "MCP",
    }

    normalized = []
    seen = set()

    for entity in entities:
        if not entity or not isinstance(entity, str):
            continue

        # 去除空白
        entity = entity.strip()
        if not entity:
            continue

        # 小写用于查表和去重
        lower = entity.lower()

        # 标准化
        if lower in entity_mapping:
            entity = entity_mapping[lower]

        # 去重（不区分大小写）
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


def clean_retweet_content(title, content):
    """
    清理 Twitter 转发（RT）格式，提取原始内容。

    Twitter RSS 中转发格式：
    - title: "RT @original_author: original tweet content..."
    - content: 可能包含原始推文或转发者的评论

    返回清理后的 (title, content, is_retweet, original_author)
    """
    if not title:
        return title, content, False, None

    # 匹配 RT @username: content 或 RT username: content 格式
    # 支持带空格的名称，如 "RT Greg Brockman: ..."
    rt_pattern = r'^RT\s+@?([^:]+):\s*(.+)$'
    match = re.match(rt_pattern, title, re.DOTALL)

    if match:
        original_author = match.group(1)
        original_content = match.group(2).strip()

        # 如果 content 为空或与 title 相似，使用提取的原始内容
        if not content or content.strip() == title.strip():
            content = original_content

        # 清理后的 title 应该是原始内容（截断版）
        # 返回原始内容作为 title，以便 AI 正确理解
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

                # 清理转发格式
                title, content, is_rt, rt_author = clean_retweet_content(title, content)

                items.append({
                    "title": title,
                    "content": content,
                    "url": url,
                    "source": source,
                    "published": parse_pub_date(pub_date),
                    "_is_retweet": is_rt,
                    "_rt_author": rt_author,
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

            # 清理转发格式
            title, content, is_rt, rt_author = clean_retweet_content(title, content)

            items.append({
                "title": title,
                "content": content,
                "url": url,
                "source": source,
                "published": parse_pub_date(pub_date),
                "_is_retweet": is_rt,
                "_rt_author": rt_author,
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

    # CEO/核心人物观点加分（公司高管发表的重要观点）
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


# ==================== AI 处理 ====================

def get_ai_prompt(items, batch_size=None):
    """生成 AI 处理提示词"""
    if batch_size is None:
        batch_size = DEFAULT_BATCH_SIZE

    items_for_ai = []
    for i, item in enumerate(items[:batch_size]):
        # 使用 _original_index（filtered 列表的绝对位置），而非局部 i
        # 这样 AI 返回的 result["index"] 可以直接映射回 filtered 列表，避免缓存分离后的索引错位
        items_for_ai.append({
            "index": item.get("_original_index", i),
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


def process_with_ai(items, auto_ai=False, source="default", batch_size=None, cache=None):
    """使用 AI 处理新闻"""
    if batch_size is None:
        batch_size = DEFAULT_BATCH_SIZE

    files = get_ai_files(source)
    logger.info(f"[AI] 开始处理 {len(items)} 条新闻 (来源: {source}, 批量: {batch_size})...")

    # 为每个 item 添加原始索引，用于后续匹配
    for i, item in enumerate(items):
        item["_original_index"] = i

    # 尝试从缓存获取结果
    cached_results = []  # 始终初始化，确保后续 return 时可以合并
    if cache is not None:
        uncached_items = []
        for item in items:
            cached = get_cached_result(item, cache)
            if cached:
                # 将缓存结果与原始索引关联
                cached["_original_index"] = item.get("_original_index", 0)
                cached_results.append(cached)
            else:
                uncached_items.append(item)

        if cached_results:
            logger.info(f"[AI] 从缓存获取 {len(cached_results)} 条结果")

        if not uncached_items:
            logger.info("[AI] 全部结果来自缓存")
            return cached_results

        items = uncached_items

    # 获取锁
    lock_fd = acquire_lock(files["lock"])
    if lock_fd is None:
        logger.error("[AI] 无法获取处理锁，可能有其他进程正在运行")
        return None

    try:
        prompt = get_ai_prompt(items, batch_size=batch_size)

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
                            results = data.get("results", [])
                            logger.info(f"[AI] API 处理成功，返回 {len(results)} 条结果")
                            # Bug 3 修复：构建 _original_index → item 映射，避免依赖 enumerate 顺序
                            # AI 可能合并条目，results 顺序和数量都可能与 items 不一致
                            index_to_item = {item.get("_original_index", i): item for i, item in enumerate(items)}
                            for result in results:
                                ai_index = result.get("index", -1)
                                if ai_index in index_to_item:
                                    result["_original_index"] = ai_index
                                else:
                                    logger.warning(f"[AI] 结果 index={ai_index} 无法映射到原始 item")
                            # 缓存结果
                            if cache is not None:
                                for item, result in zip(items, results):
                                    cache_result(item, result, cache)
                                save_ai_cache(cache, source)
                            # Bug 2 修复：合并之前命中缓存的结果，避免部分缓存命中时丢弃已缓存条目
                            return cached_results + results
                        else:
                            logger.warning(f"[AI] 结果验证失败: {msg}")

            logger.warning("[AI] API 调用失败或结果无效，切换到本地模型模式")

        # 本地模型模式：生成提示词文件
        prompt_file = files["prompt"]
        with open(prompt_file, "w", encoding="utf-8") as f:
            f.write(prompt)

        logger.info("=" * 60)
        logger.info("[本地模式] 请按以下步骤操作：")
        logger.info(f"  1. 读取 {prompt_file} 文件")
        logger.info("  2. 将内容发送给本地模型（Claude/ChatGPT等）")
        logger.info(f"  3. 将模型返回的 JSON 保存为 {files['result']}")
        logger.info("  4. 再次运行此脚本")
        logger.info("=" * 60)

        return None

    finally:
        release_lock(lock_fd)


def load_local_ai_result(source="default"):
    """加载本地 AI 处理结果"""
    files = get_ai_files(source)
    result_file = files["result"]

    if not os.path.exists(result_file):
        return None

    try:
        with open(result_file, "r", encoding="utf-8") as f:
            content = f.read()

        data = safe_json_loads(content, max_retries=3, context="本地AI结果")
        if data:
            # 备份并删除结果文件
            backup_file = files["backup"]
            if os.path.exists(backup_file):
                os.remove(backup_file)
            os.rename(result_file, backup_file)
            logger.info(f"[AI] 结果文件已备份: {backup_file}")

            # 清理锁文件和 prompt 文件
            cleanup_processing_files(source)

            is_valid, msg = validate_ai_result(data)
            if is_valid:
                results = data.get("results", [])
                # 兼容旧格式：如果没有 _original_index，使用 index
                for r in results:
                    if "_original_index" not in r and "index" in r:
                        r["_original_index"] = r["index"]
                return results
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
    parser.add_argument("--batch-size", type=int, default=None,
                        help=f"批量处理大小 (默认: {DEFAULT_BATCH_SIZE})")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="显示详细日志")
    parser.add_argument("--resume", action="store_true",
                        help="恢复之前中断的处理")
    args = parser.parse_args()

    # 设置日志级别
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    logger.info("=" * 60)
    logger.info(f"开始新闻选题更新 [源: {args.source}]")
    logger.info("=" * 60)

    # 检查处理状态（恢复机制）
    source_key = args.source if args.source != "all" else "combined"
    state, files = check_processing_state(source_key)

    if state == "running" and not args.resume:
        logger.error("[错误] 检测到正在进行的处理任务。请等待完成或使用 --resume 强制新任务")
        return

    if state == "prompt_pending" and not args.resume:
        logger.info("[提示] 发现未处理的 prompt 文件。请处理后再运行，或使用 --resume 强制重新生成")
        return

    # 加载缓存
    ai_cache = load_ai_cache(source_key)
    if ai_cache:
        logger.info(f"[缓存] 已加载 {len(ai_cache)} 条 AI 处理缓存")

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

    # ========== 预告事件检查 ==========
    upcoming_news_items = []
    if UPCOMING_EVENTS_AVAILABLE:
        summary = get_pending_events_summary()
        if summary["pending"] > 0:
            logger.info(f"[预告事件] 发现 {summary['pending']} 个待处理预告")
            
            # 检查新内容是否匹配预告事件
            check_result = check_items_against_events(new_items)
            
            if check_result["matched"]:
                logger.info(f"[预告事件] 🎯 匹配到 {len(check_result['matched'])} 个预告事件！")
                
                for event, item, match_details in check_result["matched"]:
                    # 转换为新闻格式
                    news_item = convert_matched_to_news(event, item, match_details)
                    upcoming_news_items.append(news_item)
                    
                    # 更新事件状态为 found
                    update_event_status(event["id"], "found", news_item)
                    
                    logger.info(f"[预告事件] ✅ 已转换: {event['title'][:50]}...")
                
                # 更新 new_items 为未匹配的内容
                new_items = check_result["unmatched"]
                logger.info(f"[预告事件] 剩余未匹配新内容: {len(new_items)} 条")
            else:
                logger.info("[预告事件] 本次无匹配")
        else:
            logger.debug("[预告事件] 无待处理预告")
    
    # 如果有预告事件落地，先保存
    if upcoming_news_items:
        today, existing = load_existing_news()
        final_news, added, updated = merge_news(existing, upcoming_news_items)
        logger.info(f"[预告事件] 已加入 {len(upcoming_news_items)} 条落地新闻")
        
        if save_news(today, final_news):
            push_to_github()
            logger.info("[预告事件] ✅ 已保存到新闻列表")
    
    # ========== 预告事件检查结束 ==========

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
    # 先尝试加载本地结果（恢复机制）
    ai_results = load_local_ai_result(source_key)

    if ai_results is None:
        # 没有本地结果，进行 AI 处理
        ai_results = process_with_ai(
            filtered,
            auto_ai=args.auto_ai,
            source=source_key,
            batch_size=args.batch_size,
            cache=ai_cache
        )

        if ai_results is None:
            logger.info("\n需要本地模型处理，请按上述指引操作")
            return

    logger.info(f"[AI] 处理完成，获得 {len(ai_results)} 条结果")

    # 5. 构建最终数据
    # 使用 _original_index 映射回原始 filtered 列表
    ai_map = {r.get("_original_index", r.get("index", 0)): r for r in ai_results}
    processed = []

    for idx, item in enumerate(filtered):
        ai_result = ai_map.get(idx, {})

        if not ai_result:
            logger.warning(f"[AI] 索引 {idx} 无对应结果: {item.get('title', '')[:40]}...")
            continue

        # 标准化实体
        entities = normalize_entities(ai_result.get("entities", []))

        level = ai_result.get("level", "B")
        score = ai_result.get("score", 60)
        processed.append({
            "title": ai_result.get("title", item["title"]),
            "title_en": item["title"],
            "summary": ai_result.get("summary", ""),
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
    
    # 预告事件统计
    if UPCOMING_EVENTS_AVAILABLE:
        summary = get_pending_events_summary()
        if summary["pending"] > 0:
            logger.info(f"\n【预告事件】")
            logger.info(f"  待处理: {summary['pending']} 个")
            for e in summary["pending_list"][:3]:  # 最多显示3个
                logger.info(f"    - {e['title'][:40]}...")
        
        # 清理过期事件
        cleanup_expired_events()
    
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
