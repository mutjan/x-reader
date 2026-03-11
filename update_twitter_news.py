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
import sys
from datetime import datetime, timedelta
import time
from urllib.parse import urlparse
import requests
import xml.etree.ElementTree as ET
import logging

# ==================== Python 版本检测 ====================

def check_python_version():
    """检查 Python 版本，确保使用 Python 3"""
    if sys.version_info.major < 3:
        print("错误: 需要使用 Python 3 运行此脚本")
        sys.exit(1)
    return True

# ==================== 日志配置 ====================

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


# ==================== JSON 安全处理 ====================

def sanitize_json_string(text):
    """清理JSON字符串中的特殊字符，特别是中文引号

    处理以下问题：
    1. 中文引号 " " 替换为转义的英文引号 \" \"
    2. 控制字符过滤
    3. 换行符统一处理
    4. 修复AI可能生成的错误JSON格式
    """
    if not isinstance(text, str):
        return text

    # 替换中文引号为英文引号（左双引号、右双引号）
    text = text.replace('"', '"').replace('"', '"')
    # 替换中文单引号（左单引号、右单引号）
    text = text.replace(''', "'").replace(''', "'")
    # 替换全角引号
    text = text.replace('＂', '"').replace("＇", "'")

    # 修复常见的AI生成JSON错误：属性名未加引号
    # 例如：{title: "xxx"} -> {"title": "xxx"}
    text = re.sub(r'([{,]\s*)([a-zA-Z_][a-zA-Z0-9_]*)(\s*:)', r'\1"\2"\3', text)

    # 修复尾部逗号（在}或]前的多余逗号）
    text = re.sub(r',(\s*[}\]])', r'\1', text)

    # 替换其他可能导致JSON解析失败的字符
    text = text.replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')

    # 移除其他控制字符 (0x00-0x1F，除了\n\r\t)
    text = ''.join(char for char in text if ord(char) >= 32 or char in '\n\r\t')

    return text


def safe_json_loads(json_str, max_retries=3):
    """安全加载JSON字符串，带重试和清理机制

    Args:
        json_str: JSON字符串
        max_retries: 最大重试次数

    Returns:
        解析后的Python对象，失败返回None
    """
    for attempt in range(max_retries):
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.warning(f"JSON解析失败 (尝试 {attempt + 1}/{max_retries}): {e}")

            if attempt == 0:
                # 第一次尝试：清理中文引号
                json_str = sanitize_json_string(json_str)
            elif attempt == 1:
                # 第二次尝试：尝试提取JSON部分（如果包含在代码块中）
                json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', json_str, re.DOTALL)
                if json_match:
                    json_str = json_match.group(1)
                    json_str = sanitize_json_string(json_str)
            else:
                # 最后一次尝试：尝试修复常见的JSON错误
                json_str = try_fix_json(json_str)

    logger.error(f"JSON解析失败，已达到最大重试次数")
    return None


def try_fix_json(json_str):
    """尝试修复常见的JSON格式错误"""
    # 移除BOM
    if json_str.startswith('\ufeff'):
        json_str = json_str[1:]

    # 修复尾部逗号
    json_str = re.sub(r',(\s*[}\]])', r'\1', json_str)

    # 修复缺失的引号（简单情况）
    json_str = re.sub(r'([{,]\s*)(\w+)(\s*:)', r'\1"\2"\3', json_str)

    return json_str


def safe_json_dumps(obj, ensure_ascii=False, indent=2):
    """安全地将Python对象转为JSON字符串

    自动处理字符串中的特殊字符
    """
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


def validate_json_before_save(obj, context=""):
    """在保存前验证JSON对象是否可以正确序列化

    Args:
        obj: 要验证的Python对象
        context: 上下文信息，用于日志

    Returns:
        (is_valid, error_message): 验证结果和错误信息
    """
    try:
        # 尝试序列化
        json_str = json.dumps(obj, ensure_ascii=False)
        # 尝试反序列化验证
        parsed = json.loads(json_str)
        return True, ""
    except (TypeError, ValueError, json.JSONDecodeError) as e:
        error_msg = f"JSON验证失败{' (' + context + ')' if context else ''}: {e}"
        return False, error_msg


def safe_save_json_file(filepath, obj, ensure_ascii=False, indent=2):
    """安全地保存JSON文件，带前置验证

    Args:
        filepath: 文件路径
        obj: 要保存的Python对象
        ensure_ascii: 是否转义非ASCII字符
        indent: 缩进空格数

    Returns:
        bool: 是否保存成功
    """
    # 前置验证
    is_valid, error_msg = validate_json_before_save(obj, filepath)
    if not is_valid:
        logger.error(f"[保存] {error_msg}")
        return False

    try:
        # 使用安全导出
        safe_content = safe_json_dumps(obj, ensure_ascii=ensure_ascii, indent=indent)

        # 再次验证生成的内容
        try:
            json.loads(safe_content)
        except json.JSONDecodeError as e:
            logger.error(f"[保存] 生成的JSON内容无效: {e}")
            return False

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(safe_content)

        logger.info(f"[保存] 文件已保存: {filepath}")
        return True
    except Exception as e:
        logger.error(f"[保存] 保存文件失败 {filepath}: {e}")
        return False

# ==================== 配置 ====================

RSS_URL = "http://localhost:1200/twitter/list/2026563584311108010?filter_time=86400"
PROXY = "socks5h://127.0.0.1:7890"
DATA_FILE = "news_data.json"

# 关键词预筛选配置 - 确保重要科技动态不被遗漏
# 改进：添加更多AI编程/Agent相关关键词，增强具身智能覆盖
PRIORITY_KEYWORDS = {
    # AI大模型相关
    "ai": ["gpt-5", "gpt-4.5", "gpt5.4", "gpt-5.4", "gpt4.5", "claude 4", "claude4", "gemini 2", "gemini2",
           "o3", "o4", "o1", "o1-pro", "reasoning", "agent", "agents", "agi", "llama 4", "llama4", "deepseek-v4", "deepseek v4",
           "openai", "anthropic", "deepmind", "xai", "grok", "perplexity", "cursor", "manus", "sora",
           "chatgpt", "claude", "gemini", "deepseek", "grok-3", "grok 3", "llama3", "llama 3",
           "llm", "foundation model", "reasoning model", "inference", "training", "fine-tuning",
           "rlhf", "rl", "reinforcement learning", "moe", "mixture of experts",
           "context window", "long context", "multimodal", "embedding", "vector",
           # 新增：MCP、Function Calling、Tool Use
           "mcp", "model context protocol", "function calling", "tool use", "tool calling"],
    # 科技巨头动态
    "bigtech": ["apple intelligence", "apple ai", "google ai", "microsoft ai", "meta ai",
                "amazon ai", "nvidia", "tesla fsd", "spacex", "neuralink", "starlink",
                "waymo", "alphabet", "meta", "字节", "bytedance", "腾讯", "tencent",
                "阿里", "alibaba", "百度", "baidu", "华为", "huawei", "xiaomi", "小米",
                "meituan", "美团", "pinduoduo", "拼多多", "jd", "京东", "kuaishou", "快手",
                # 新增：智谱、月之暗面等国产AI公司
                "智谱", "zhipu", "月之暗面", "moonshot", "kimi", "minimax", "零一万物", "01.ai"],
    # 芯片/硬件
    "chip": ["blackwell", "hopper", "h100", "h200", "h300", "b100", "b200", "b300", "mi300", "mi400",
             "tensor", "cuda", "quantum chip", "quantum processor", "ai chip", "ai accelerator",
             "tsmc", "samsung foundry", "intel", "amd", "ryzen", "epyc", "gpu shortage",
             "compute", "compute cluster", "data center", "ai infrastructure"],
    # 产品发布
    "product": ["正式发布", "刚刚发布", "新品发布", "launch", "released", "announced",
                "unveiled", "debut", "shipped", "available now", "coming soon", "预告",
                "开源", "open source", "github", "paper", "论文", "demo", "炸裂", "重磅", "突发"],
    # 人物动态
    "people": ["elon musk", "musk", "sam altman", "altman", "sundar pichai", "pichai",
               "satya nadella", "nadella", "tim cook", "mark zuckerberg", "zuckerberg",
               "jeff bezos", "bezos", "demis hassabis", "hassabis", "ilya sutskever", "ilya",
               "andrej karpathy", "karpathy", "dario amodei", "amodei", "fei-fei li",
               "李飞飞", "李彦宏", "robin li", "马云", "jack ma", "马化腾", "pony ma",
               "greg brockman", "brockman", "sebastien bubeck", "bubeck", "noam shazeer", "shazeer",
               # 新增：更多AI领域重要人物
               "alexandr wang", "scale ai", "emmett shear", "jensen huang", "黄仁勋"],
    # 科研突破
    "research": ["nature", "science", "cell", "arxiv", "breakthrough", "milestone",
                 "首次", "第一次", "创造历史", "里程碑", "新发现", "重大突破", "颠覆性",
                 "state-of-the-art", "sota", "novel", "innovative", "pioneering",
                 "ai for science", "ai4science", "protein folding", "drug discovery",
                 "mathematics", "theorem proving", "frontiermath",
                 # 新增：更多科研相关
                 "benchmark", "evaluation", "dataset", "开源数据集"],
    # 商业/融资
    "business": ["ipo", "上市", "收购", "并购", "融资", "估值", "独角兽", "merger",
                 "acquisition", "funding", "valuation", "unicorn", "series a", "series b",
                 "series c", "investment", "investor", "share price", "market cap",
                 "revenue", "profit", "earnings", "quarterly", "财报"],
    # 多模态/视频生成
    "multimodal": ["sora", "video generation", "text-to-video", "image generation",
                   "text-to-image", "multimodal", "vision model", "vlm", "diffusion",
                   "stable diffusion", "dalle", "dall-e", "midjourney", "flux",
                   # 新增：更多图像/视频生成工具
                   "runway", "pika", "heygen", "elevenlabs", "voice clone"],
    # AI编程/工具 - 大幅扩展
    "coding": ["cursor", "windsurf", "github copilot", "code generation", "ai coding",
               "devin", "coding agent", "programming assistant", "ide", "vscode",
               "ai engineer", "software engineer", "swe", "swe-bench",
               # 新增：更多AI编程相关
               "code review", "code completion", "autocomplete", "refactor",
               "unit test", "test generation", "documentation", "api design",
               "vibe coding", "vibecoding", "trae", "cline", "aider", "continue.dev"],
    # 具身智能/机器人 - 大幅扩展
    "robotics": ["robotics", "robot", "embodied ai", "humanoid", "boston dynamics",
                 "figure ai", "tesla bot", "optimus", "autonomous", "self-driving",
                 # 新增：更多机器人公司和概念
                 "agility robotics", "digit", "apptronik", "apollo", "1x technologies",
                 "covariant", "physical intelligence", "pi", "general purpose robot",
                 "manipulation", "grasping", "locomotion", "teleoperation"],
}

# 所有关键词合并为一个列表用于快速匹配
ALL_PRIORITY_KEYWORDS = []
for category, keywords in PRIORITY_KEYWORDS.items():
    ALL_PRIORITY_KEYWORDS.extend(keywords)

# GitHub 配置
GITHUB_REPO = "x-reader"  # 根据实际情况修改
GITHUB_BRANCH = "main"

# ==================== 已处理推文ID缓存配置 ====================
# 改进：添加已处理推文ID缓存机制，避免重复处理
PROCESSED_IDS_FILE = ".processed_tweet_ids.json"
MAX_CACHED_IDS = 5000  # 最多缓存5000条推文ID


def load_processed_ids():
    """加载已处理的推文ID缓存"""
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
    """保存已处理的推文ID缓存"""
    try:
        # 限制缓存数量，保留最新的
        ids_list = list(ids)
        if len(ids_list) > MAX_CACHED_IDS:
            ids_list = ids_list[-MAX_CACHED_IDS:]

        with open(PROCESSED_IDS_FILE, "w", encoding="utf-8") as f:
            json.dump({"ids": ids_list, "updated_at": datetime.now().isoformat()}, f)
    except Exception as e:
        logger.warning(f"[缓存] 保存已处理ID失败: {e}")


def extract_tweet_id(url):
    """从Twitter URL中提取推文ID"""
    if not url:
        return None
    match = re.search(r"status/(\d+)", url)
    if match:
        return match.group(1)
    return None


def filter_processed_items(items, processed_ids):
    """过滤掉已处理的推文"""
    new_items = []
    skipped_count = 0

    for item in items:
        tweet_id = extract_tweet_id(item.get("url", ""))
        if tweet_id and tweet_id in processed_ids:
            skipped_count += 1
            continue
        new_items.append(item)

    if skipped_count > 0:
        logger.info(f"[去重] 跳过 {skipped_count} 条已处理的推文")

    return new_items

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
        logger.error(f"[RSS] 解析出错: {e}")

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
    logger.info(f"[筛选] 最近 {hours} 小时: {len(recent)}/{len(items)} 条")
    return recent


def extract_priority_keywords(text):
    """从文本中提取匹配的高优先级关键词

    返回匹配到的关键词列表及其所属类别
    改进：支持整词匹配，避免部分匹配（如 "rl" 匹配到 "already"）
    """
    if not text:
        return [], {}

    text_lower = text.lower()
    matched_keywords = []
    matched_categories = {}

    # 需要整词匹配的关键词（避免部分匹配）
    # 注意：这些短关键词如果简单包含匹配会误伤很多词，如"ide"匹配到"idea"、"identifier"
    whole_word_keywords = {
        # 严格整词匹配（前后必须是边界字符）
        'rl', 'pi', 'agi', 'mcp', 'o1', 'o3', 'o4', 'gpt', 'vlm',
        'tpu', 'sdk', 'ux', 'os', 'db',
        # 特殊处理的关键词（见下方精确匹配列表）
    }

    # 需要更精确匹配的关键词（避免常见误匹配）
    # 格式: 关键词: (避免匹配的模式列表)
    precise_match_keywords = {
        'ide': ['idea', 'identifier', 'identify', 'identical', 'side', 'aside', 'inside', 'outside', 'beside', 'decide', 'president', 'resident', 'evident', 'provide', 'divide'],
        'ai': ['fail', 'mail', 'sail', 'tail', 'rail', 'nail', 'pain', 'paint', 'pair', 'airport', 'airline', 'waiting', 'training', 'draining', 'explaining'],
        'llm': ['all', 'will', 'ball', 'call', 'fall', 'hall', 'mall', 'tall', 'wall', 'well', 'tell', 'sell', 'cell', 'dell', 'shell'],
        'cpu': ['occupy', 'occurrence', 'sculpture'],
        'gpu': [],  # gpu相对安全
        'api': ['april', 'apiece', 'happiness'],
        'ui': ['build', 'built', 'fruit', 'suit', 'juice', 'ruin', 'guide', 'guilty', 'quick', 'quiet', 'quite', 'require', 'inquiry', 'equity'],
    }

    for category, keywords in PRIORITY_KEYWORDS.items():
        category_matches = []
        for keyword in keywords:
            keyword_lower = keyword.lower()

            # 检查是否需要精确匹配（避免误匹配）
            if keyword_lower in precise_match_keywords:
                # 精确匹配模式：检查是否包含避免列表中的词
                avoid_patterns = precise_match_keywords[keyword_lower]
                is_valid_match = False

                # 先检查是否包含关键词本身
                if keyword_lower in text_lower:
                    is_valid_match = True
                    # 检查是否命中了需要避免的模式
                    for avoid in avoid_patterns:
                        if avoid in text_lower:
                            # 如果包含避免词，需要进一步验证是独立词还是子串
                            # 例如 "ide" vs "idea"：检查 "ide" 后面是否跟着字母
                            # 使用正则确保关键词是独立单词
                            pattern = r'(?:^|[^a-z])' + re.escape(keyword_lower) + r'(?:[^a-z]|$)'
                            if not re.search(pattern, text_lower):
                                is_valid_match = False
                                break

                if is_valid_match:
                    matched_keywords.append(keyword)
                    category_matches.append(keyword)

            # 检查是否需要整词匹配
            elif keyword_lower in whole_word_keywords:
                # 使用单词边界进行整词匹配
                # 支持：空格、标点、开头、结尾作为边界
                # 构建正则：匹配作为独立单词的关键词
                pattern = r'(?:^|[\s\W])' + re.escape(keyword_lower) + r'(?:$|[\s\W])'
                if re.search(pattern, text_lower):
                    matched_keywords.append(keyword)
                    category_matches.append(keyword)
            else:
                # 普通包含匹配（用于短语、复合词等）
                if keyword_lower in text_lower:
                    matched_keywords.append(keyword)
                    category_matches.append(keyword)

        if category_matches:
            matched_categories[category] = category_matches

    return matched_keywords, matched_categories


def calculate_priority_score(item):
    """计算新闻的优先级得分

    基于关键词匹配情况给新闻打分，用于预筛选排序
    """
    text = f"{item.get('title', '')} {item.get('content', '')}"
    matched_keywords, matched_categories = extract_priority_keywords(text)

    score = 0
    # 基础分：每个匹配关键词+5分
    score += len(matched_keywords) * 5

    # 类别加分：匹配到不同类别额外加分
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

    return score, matched_keywords, matched_categories


def keyword_pre_filter(items, min_priority_score=5, ensure_top_n=30):
    """关键词预筛选 - 确保重要科技动态不被遗漏

    Args:
        items: 原始新闻列表
        min_priority_score: 最低优先级分数阈值，低于此值可能被过滤
        ensure_top_n: 确保至少保留前N条（按优先级排序）

    Returns:
        预筛选后的新闻列表，重要新闻排在前面
    """
    if not items:
        return []

    # 为每条新闻计算优先级分数
    scored_items = []
    for item in items:
        score, keywords, categories = calculate_priority_score(item)
        item_with_score = item.copy()
        item_with_score["_priority_score"] = score
        item_with_score["_matched_keywords"] = keywords
        item_with_score["_matched_categories"] = categories
        scored_items.append(item_with_score)

    # 按优先级分数排序（高到低）
    scored_items.sort(key=lambda x: x["_priority_score"], reverse=True)

    # 分离高优先级和普通新闻
    high_priority = [i for i in scored_items if i["_priority_score"] >= min_priority_score]
    normal_priority = [i for i in scored_items if i["_priority_score"] < min_priority_score]

    # 统计信息
    category_counts = {}
    for item in high_priority:
        for cat in item["_matched_categories"]:
            category_counts[cat] = category_counts.get(cat, 0) + 1

    logger.info(f"[预筛选] 高优先级新闻: {len(high_priority)} 条")
    logger.info(f"[预筛选] 普通新闻: {len(normal_priority)} 条")
    if category_counts:
        logger.info(f"[预筛选] 类别分布: {category_counts}")

    # 输出前10条高优先级新闻的关键词匹配情况
    for i, item in enumerate(high_priority[:10]):
        keywords_str = ", ".join(item["_matched_keywords"][:5])
        logger.info(f"  #{i+1} [{item['_priority_score']}分] {item['title'][:40]}... | 关键词: {keywords_str}")

    # 组合结果：高优先级优先，然后补充普通新闻到ensure_top_n
    result = high_priority[:ensure_top_n]
    if len(result) < ensure_top_n:
        result.extend(normal_priority[:ensure_top_n - len(result)])

    # 清理临时字段（保留_score用于后续处理参考）
    for item in result:
        item["priority_score"] = item.pop("_priority_score", 0)
        item["matched_keywords"] = item.pop("_matched_keywords", [])
        item["matched_categories"] = item.pop("_matched_categories", {})

    return result


# ==================== AI 处理（支持多种模式） ====================

def get_claude_api_key():
    """从环境变量或配置文件获取 Claude API Key"""
    # 首先检查环境变量
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        return api_key

    # 检查配置文件
    config_file = os.path.expanduser("~/.config/anthropic/api_key")
    if os.path.exists(config_file):
        try:
            with open(config_file, "r") as f:
                return f.read().strip()
        except:
            pass

    return None


def check_api_key_config():
    """检查API Key配置状态，返回配置提示信息"""
    api_key = get_claude_api_key()

    if api_key:
        # 显示部分key用于确认
        masked_key = api_key[:8] + "..." + api_key[-4:] if len(api_key) > 12 else "已配置"
        return True, f"[配置] Claude API Key 已配置 ({masked_key})"

    # 未配置，返回详细配置指南
    config_guide = """
[配置] Claude API Key 未配置，将使用本地模型模式

配置方法（选择其一）：
1. 环境变量：export ANTHROPIC_API_KEY="your-api-key"
2. 配置文件：mkdir -p ~/.config/anthropic && echo "your-api-key" > ~/.config/anthropic/api_key

获取API Key: https://console.anthropic.com/settings/keys
"""
    return False, config_guide


def call_claude_api(prompt, max_retries=2):
    """调用 Claude API 处理新闻选题

    Args:
        prompt: 提示词
        max_retries: 最大重试次数

    Returns:
        API 返回的 JSON 字符串，失败返回 None
    """
    # 检查API Key配置并输出提示
    is_configured, config_msg = check_api_key_config()
    if not is_configured:
        logger.info(config_msg)
        return None
    else:
        logger.info(config_msg)

    api_key = get_claude_api_key()

    api_url = "https://api.anthropic.com/v1/messages"

    headers = {
        "x-api-key": api_key,
        "Content-Type": "application/json",
        "anthropic-version": "2023-06-01"
    }

    payload = {
        "model": "claude-3-5-sonnet-20241022",
        "max_tokens": 4000,
        "temperature": 0.3,
        "system": "你是一位资深科技媒体编辑，负责筛选和加工科技新闻选题。请严格按照用户要求的JSON格式返回结果，不要添加任何解释性文字。",
        "messages": [
            {"role": "user", "content": prompt}
        ]
    }

    for attempt in range(max_retries):
        try:
            logger.info(f"[AI] 调用 Claude API (尝试 {attempt + 1}/{max_retries})...")
            response = requests.post(
                api_url,
                headers=headers,
                json=payload,
                timeout=120
            )

            if response.status_code == 200:
                data = response.json()
                content = data.get("content", [])
                if content:
                    return content[0].get("text", "")
                logger.warning("[AI] API 返回内容为空")
            else:
                logger.warning(f"[AI] API 请求失败: {response.status_code} - {response.text}")

        except requests.exceptions.Timeout:
            logger.warning(f"[AI] API 请求超时 (尝试 {attempt + 1}/{max_retries})")
        except Exception as e:
            logger.warning(f"[AI] API 请求出错: {e}")

        if attempt < max_retries - 1:
            time.sleep(2 ** attempt)  # 指数退避

    return None


def ai_process_items(items, enable_keyword_hint=True, auto_call_api=True):
    """使用 AI 处理新闻选题

    支持两种模式：
    1. 自动 API 调用（如果配置了 API Key）
    2. 本地模型模式（生成提示词供人工处理）

    Args:
        items: 新闻列表
        enable_keyword_hint: 是否启用关键词预筛选提示
        auto_call_api: 是否尝试自动调用 API
    """
    if not items:
        return []

    # 准备输入数据
    items_for_ai = []
    priority_hints = []

    for i, item in enumerate(items[:60]):  # 最多处理60条
        item_data = {
            "index": i,
            "title": item["title"],
            "content": item["content"][:500] if item["content"] else "",
            "source": item["source"],
            "url": item["url"],
        }

        # 添加关键词匹配信息作为提示
        if enable_keyword_hint and item.get("matched_keywords"):
            item_data["keywords_matched"] = item["matched_keywords"][:5]
            item_data["priority_score"] = item.get("priority_score", 0)

            # 为高优先级新闻生成提示
            if item.get("priority_score", 0) >= 15:
                priority_hints.append(
                    f"  新闻#{i}: 匹配关键词 {item['matched_keywords'][:3]} (优先级{item['priority_score']}分)"
                )

        items_for_ai.append(item_data)

    # 构建关键词提示部分
    keyword_hint_section = ""
    if priority_hints:
        keyword_hint_section = f"""
【关键词预筛选提示】以下新闻经关键词匹配被标记为高优先级，请重点关注：
{chr(10).join(priority_hints[:15])}

"""

    prompt = f"""你是一位资深科技媒体编辑，负责筛选和加工科技新闻选题。

{keyword_hint_section}请对以下新闻进行批量处理，返回 JSON 格式结果：

输入新闻：
{json.dumps(items_for_ai, ensure_ascii=False, indent=2)}

处理要求：

1. **筛选选题**（S级/S-级/A级/B级）：
   - S级（90-100分）：真正的里程碑事件
     * AI大模型重大发布（GPT-5、Claude 4、Gemini 2等）
     * 马斯克/SpaceX/Neuralink重大动态
     * Nature/Science/Cell顶刊发表
     * 科技巨头重大战略调整或人事变动（CEO级别）
     * AGI相关重大进展或权威预测
     * 顶级AI研究者（如Karpathy、Hassabis）的重大开源项目
   - S-级（85-89分）：重要但非里程碑
     * 重要产品更新（如GPT-4.5、Claude 3.5重大升级）
     * 重要技术突破（如解决FrontierMath难题）
     * 知名人物重要观点/专访
     * 大额融资（5亿美元以上）
   - A级（75-84分）：
     * 科技巨头常规产品更新（OpenAI、Google、Microsoft、Meta等）
     * 国产大模型重要进展（DeepSeek、文心一言、通义千问等）
     * 开源项目爆款/Star数激增
     * 学术突破（arxiv重要论文）
     * 资本市场重大动态（IPO、中等规模融资）
   - B级（65-74分）：
     * 产品评测、体验报告
     * 技术解析、教程
     * 航天/芯片领域常规进展
     * 行业数据报告
   - 过滤掉C级（<65分）：
     * 一般商业新闻
     * 消费电子日常更新
     * 营销软文
     * 个人观点/评论（非权威来源）

2. **生成量子位风格中文标题**：
   - 纯中文，无类型前缀
   - 情绪饱满，优先使用"刚刚"、"突发"、"炸裂"、"重磅"、"颠覆"、"首次"等词开头
   - 15-35字，简洁有力，突出核心信息
   - **必须使用数字和对比**，如"暴涨300%"、"跌破5%"、"仅3%"、"超10亿"
   - 避免冗长描述，直击要点
   - **标题公式**（按优先级选择）：
     * 时间敏感型："刚刚！+ 主体 + 动作 + 数据"
     * 数据冲击型："数字 + 对比词 + 主体 + 结果"
     * 权威引语型："人物/公司 + ：+ 核心观点"
     * 颠覆型："颠覆/重新定义 + 领域 + 主体"
   - 标题示例：
     * "刚刚！Andrej Karpathy开源AgentHub：专为AI Agent打造的GitHub"
     * "GPT-5.4 Pro数学推理炸裂！35分钟破解复杂迷宫"
     * "DeepMind CEO Hassabis：AlphaZero级AI可能在AGI之后出现"
     * "暴涨300%！Sora日活突破300万，OpenAI视频战略逆转"
     * "仅3%渗透率！Microsoft Copilot企业采用率远低于预期"

3. **生成一句话摘要**：
   - 50-100字
   - 概括核心信息，突出关键数据
   - 说明"为什么重要"

4. **标注类型**：hot(热点)/ai(AI相关)/tech(科技)/business(商业)

5. **识别核心实体**（2-5个）：
   - 公司/组织：如OpenAI、Google、DeepMind、NVIDIA
   - 产品/模型：如ChatGPT、Claude、Sora、Gemini
   - 人物：如马斯克、Sam Altman、Demis Hassabis、Andrej Karpathy
   - 技术/概念：如AGI、Agent、RAG、量子计算
   - 事件：如IPO、收购、发布、开源

6. **添加行业标签**（1-3个）：
   - 大模型、AI Agent、多模态、AI编程、AI科研、芯片、机器人、自动驾驶、商业动态、开源、监管政策

返回格式（JSON）：
{{
  "results": [
    {{
      "index": 0,
      "score": 95,
      "level": "S",
      "title": "重磅！Andrej Karpathy开源AgentHub：专为AI Agent打造的GitHub",
      "summary": "前特斯拉AI总监Andrej Karpathy发布开源项目AgentHub，这是一个专为AI Agent设计的代码协作平台，被视为AI时代的GitHub。",
      "type": "ai",
      "reason": "顶级AI研究者重大开源项目，AI Agent领域里程碑",
      "entities": ["Andrej Karpathy", "AgentHub", "开源", "AI Agent"],
      "tags": ["AI Agent", "开源"]
    }}
  ]
}}

注意：
1. 只返回 JSON，不要其他解释
2. 最多选择20条最有价值的（S级+A级+B级）
3. 相似主题的新闻合并为一条，标注多来源
4. 特别关注带有"keywords_matched"标记的新闻
5. **重要：JSON字符串必须使用英文双引号，严禁使用中文引号
6. **重要：所有属性名必须用双引号包裹，如"index": 0, "title": "xxx"
7. **重要：字符串内容中如果包含引号，必须正确转义
8. **重要：最后一个属性后不要加逗号

"""

    logger.info(f"[AI] 准备处理 {len(items_for_ai)} 条新闻...")

    # 尝试自动调用 API
    if auto_call_api:
        api_result = call_claude_api(prompt)
        if api_result:
            logger.info("[AI] API 调用成功，正在解析结果...")
            # 保存 API 结果到文件
            with open("twitter_ai_result.json", "w", encoding="utf-8") as f:
                f.write(api_result)
            logger.info("[AI] 结果已保存到 twitter_ai_result.json")
            return "API_SUCCESS"

    # 如果 API 调用失败或未启用，切换到本地模型模式
    logger.info("[AI] 切换到本地模型模式")
    logger.info("=" * 80)
    logger.info("[操作指引] 本地模型处理步骤：")
    logger.info("  1. 读取 twitter_ai_prompt.txt 文件（已自动生成）")
    logger.info("  2. 将内容发送给本地模型（Claude/ChatGPT等）")
    logger.info("  3. 将模型返回的 JSON 保存为 twitter_ai_result.json")
    logger.info("  4. 再次运行此脚本完成处理")
    logger.info("=" * 80)
    logger.debug("[AI] 提示词内容已保存到 twitter_ai_prompt.txt")

    # 保存提示词到文件，方便处理
    with open("twitter_ai_prompt.txt", "w", encoding="utf-8") as f:
        f.write(prompt)

    return "NEEDS_LOCAL_PROCESSING"


def load_ai_results():
    """加载本地模型处理的结果（增强版，带JSON验证和重试）"""
    result_file = "twitter_ai_result.json"
    if not os.path.exists(result_file):
        logger.info("[AI] 结果文件不存在，等待处理")
        return None

    try:
        with open(result_file, "r", encoding="utf-8") as f:
            content = f.read()

        # 使用安全JSON加载（带重试和清理）
        data = safe_json_loads(content, max_retries=3)

        if data is None:
            logger.error("[AI] 无法解析结果文件，格式错误")
            # 备份错误文件以便调试
            error_file = f"{result_file}.error"
            os.rename(result_file, error_file)
            logger.info(f"[AI] 错误文件已备份: {error_file}")
            return None

        # 验证数据结构
        if not isinstance(data, dict):
            logger.error(f"[AI] 结果格式错误：期望dict，得到{type(data)}")
            return None

        results = data.get("results", [])
        if not isinstance(results, list):
            logger.error(f"[AI] results字段格式错误：期望list，得到{type(results)}")
            return None

        # 备份并清理结果文件
        backup_file = f"{result_file}.processed"
        os.rename(result_file, backup_file)
        logger.info(f"[AI] 结果文件已备份: {backup_file}")
        logger.info(f"[AI] 成功加载 {len(results)} 条处理结果")

        return results

    except Exception as e:
        logger.error(f"[AI] 加载结果失败: {e}")
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


def extract_core_entities(text):
    """提取文本中的核心实体（公司、产品、技术、人名等）"""
    if not text:
        return set()

    # 常见科技实体关键词库
    tech_entities = {
        # 公司
        "openai", "anthropic", "google", "microsoft", "meta", "amazon", "nvidia", "apple",
        "tesla", "spacex", "xai", "deepmind", "anthropic", "stability", "midjourney",
        "alibaba", "tencent", "baidu", "bytedance", "huawei", "xiaomi",
        # 产品/模型
        "chatgpt", "gpt", "gpt-4", "gpt-4o", "gpt-5", "claude", "gemini", "llama",
        "dalle", "sora", "midjourney", "stable", "diffusion", "copilot", "cursor",
        # 技术
        "llm", "ai", "agi", "agent", "rag", "mcp", "transformer", "diffusion",
        "quantum", "chip", "gpu", "cuda", "neural", "training", "inference",
        # 人物
        "altman", "musk", "elon", "hassabis", "amodei", "ilya", "karpathy",
    }

    text_lower = text.lower()
    found = set()

    for entity in tech_entities:
        if entity in text_lower:
            found.add(entity)

    return found


def is_same_event(item1, item2):
    """判断两条新闻是否报道同一事件"""
    # 1. 标题高相似度
    title_sim = calculate_similarity(item1.get("title", ""), item2.get("title", ""))
    if title_sim > 0.6:
        return True

    # 2. 英文标题高相似度
    en_title_sim = calculate_similarity(
        item1.get("title_en", ""), item2.get("title_en", "")
    )
    if en_title_sim > 0.6:
        return True

    # 3. 核心实体高度重叠 + 时间接近
    entities1 = set(item1.get("entities", []))
    entities2 = set(item2.get("entities", []))

    if entities1 and entities2:
        # 实体交集
        common_entities = entities1 & entities2
        all_entities = entities1 | entities2

        # 如果核心实体高度重叠（>70%）且至少2个共同实体
        if len(common_entities) >= 2 and len(common_entities) / len(all_entities) > 0.5:
            # 检查时间是否接近（30分钟内）
            time1 = item1.get("timestamp", 0)
            time2 = item2.get("timestamp", 0)
            if abs(time1 - time2) < 1800:  # 30分钟
                return True

    # 4. URL 指向同一推文（Twitter 特有）
    url1 = item1.get("url", "")
    url2 = item2.get("url", "")
    if url1 and url2:
        # 提取推文ID
        tweet_id1 = re.search(r"status/(\d+)", url1)
        tweet_id2 = re.search(r"status/(\d+)", url2)
        if tweet_id1 and tweet_id2:
            if tweet_id1.group(1) == tweet_id2.group(1):
                return True

    return False


def find_duplicate(new_item, existing_items):
    """检查新选题是否与已有选题重复（增强版）"""
    for existing in existing_items:
        if is_same_event(new_item, existing):
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
        logger.error(f"[数据] 加载失败: {e}")
        return today, []


def save_news(today, news_data):
    """保存新闻数据到 JSON 文件（使用安全JSON导出）"""
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

        # 使用安全JSON导出
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


# ==================== 主流程 ====================

def process_with_ai(items):
    """处理新闻：筛选 + 生成标题/摘要/类型"""
    # 第一步：AI 批量处理
    logger.info(f"[AI] 开始处理 {len(items)} 条新闻...")

    # 检查是否有本地处理结果
    ai_results = load_ai_results()
    if ai_results is None:
        # 需要 AI 处理
        result = ai_process_items(items, auto_call_api=True)
        if result == "API_SUCCESS":
            # API 调用成功，重新加载结果
            ai_results = load_ai_results()
            if ai_results is None:
                logger.error("[AI] API 调用成功但无法加载结果")
                return []
        elif result == "NEEDS_LOCAL_PROCESSING":
            return "NEEDS_LOCAL_PROCESSING"
        else:
            return []

    logger.info(f"[AI] 返回 {len(ai_results)} 条处理结果")

    if not ai_results:
        logger.warning("[AI] 处理结果为空")
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

        # C级新闻处理：保留但标记为参考级别
        is_c_level = score < 65 or level == "C"
        if is_c_level:
            level = "C"
            # C级新闻降低权重，但仍然保留供参考

        # 合并AI识别的实体和关键词预筛选的实体
        entities = ai_result.get("entities", [])
        if item.get("matched_keywords"):
            # 将关键词匹配信息作为补充实体
            for kw in item["matched_keywords"][:3]:
                if kw not in entities:
                    entities.append(kw)

        # 获取行业标签
        tags = ai_result.get("tags", [])

        # 根据类型自动添加标签
        auto_tags = []
        news_type = ai_result.get("type", "tech")
        if news_type == "ai":
            auto_tags.append("AI")
        elif news_type == "business":
            auto_tags.append("商业动态")
        elif news_type == "hot":
            auto_tags.append("热点")

        # 合并自动标签和AI识别的标签
        all_tags = list(dict.fromkeys(auto_tags + tags))  # 去重保持顺序

        processed.append({
            "title": ai_result.get("title", item["title"]),
            "title_en": item["title"],
            "summary": ai_result.get("summary", "点击链接查看详情"),
            "type": news_type,
            "typeName": ai_detect_type_name(news_type),
            "score": score,
            "level": level,
            "reason": f"【{level}级】评分{score}分 | {ai_result.get('reason', '')}",
            "entities": entities[:5],  # 最多保留5个实体
            "tags": all_tags[:5],  # 最多保留5个标签
            "url": item["url"],
            "source": item["source"],
            "sources": 1,
            "sourceLinks": [{"name": item["source"], "url": item["url"]}],
            "timestamp": int(time.time()),
            "version": generate_version(),
            "priority_score": item.get("priority_score", 0),  # 保留优先级分数用于调试
        })

    # 按分数排序
    processed.sort(key=lambda x: x["score"], reverse=True)
    return processed


def merge_item_fields(existing, new):
    """智能合并两条新闻的字段，保留最优信息"""
    # 保留更高评分
    if new.get("score", 0) > existing.get("score", 0):
        existing["score"] = new["score"]
        existing["level"] = new["level"]

    # 合并实体列表（去重）
    existing_entities = set(existing.get("entities", []))
    new_entities = set(new.get("entities", []))
    merged_entities = list(existing_entities | new_entities)[:5]  # 最多保留5个
    existing["entities"] = merged_entities

    # 合并reason字段
    existing_reason = existing.get("reason", "")
    new_reason = new.get("reason", "")
    if new_reason and new_reason not in existing_reason:
        existing["reason"] = f"{existing_reason} | 补充: {new_reason}"

    return existing


def merge_with_existing(new_items, existing_items):
    """将新选题与已有选题合并，处理重复（增强版）"""
    merged = existing_items.copy()
    added_count = 0
    updated_count = 0
    merged_count = 0

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

                # 智能合并其他字段
                duplicate = merge_item_fields(duplicate, new_item)

                updated_count += 1
                logger.info(f"[合并] 更新来源: {new_item['title'][:30]}...")
            else:
                # 来源相同但可能是补充信息
                duplicate = merge_item_fields(duplicate, new_item)
                merged_count += 1
        else:
            # 添加新选题
            merged.append(new_item)
            added_count += 1
            logger.info(f"[合并] 新增选题: {new_item['title'][:30]}...")

    logger.info(f"[合并] 新增 {added_count} 条, 更新 {updated_count} 条, 合并信息 {merged_count} 条")
    return merged


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
            # 计算平均内容年龄
            now = time.time()
            ages = [now - item.get("published", now) for item in items]
            avg_age = sum(ages) / len(ages) / 3600  # 转为小时
            health_info["avg_age_hours"] = round(avg_age, 1)

            # 检查是否有最近的内容
            recent_count = sum(1 for age in ages if age < 3600)  # 1小时内
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


def main():
    # 检查 Python 版本
    check_python_version()

    # 初始化计时器
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

    # 加载已处理的推文ID
    processed_ids = load_processed_ids()
    logger.info(f"[缓存] 已加载 {len(processed_ids)} 条历史推文ID")

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
    items = filter_processed_items(items, processed_ids)

    # 3. 筛选最近 12 小时内容
    t0 = time.time()
    recent_items = filter_recent_items(items, hours=12)
    timing["filter"] = time.time() - t0

    if not recent_items:
        logger.info("[筛选] 最近 12 小时无新内容，退出")
        # 保存已处理的ID（即使没有新内容也更新缓存）
        for item in items:
            tweet_id = extract_tweet_id(item.get("url", ""))
            if tweet_id:
                processed_ids.add(tweet_id)
        save_processed_ids(processed_ids)
        return

    # 4. 关键词预筛选 - 确保重要科技动态不被遗漏
    logger.info("\n" + "-" * 40)
    logger.info("[预筛选] 执行关键词预筛选...")
    filtered_items = keyword_pre_filter(recent_items, min_priority_score=5, ensure_top_n=40)
    logger.info(f"[预筛选] 保留 {len(filtered_items)} 条新闻进入AI处理")
    logger.info("-" * 40)

    # 5. AI 处理（本地模型）
    t0 = time.time()
    processed = process_with_ai(filtered_items)
    timing["ai_process"] = time.time() - t0

    if processed == "NEEDS_LOCAL_PROCESSING":
        logger.info("\n" + "=" * 60)
        logger.info("[提示] 需要本地模型处理，请：")
        logger.info("1. 读取 twitter_ai_prompt.txt 文件内容")
        logger.info("2. 将内容发送给本地模型处理")
        logger.info("3. 将模型返回的 JSON 保存为 twitter_ai_result.json")
        logger.info("4. 再次运行此脚本")
        logger.info("=" * 60)
        return

    logger.info(f"[AI] 最终产出 {len(processed)} 条新闻 (耗时: {timing['ai_process']:.2f}s)")

    if not processed:
        logger.warning("[AI] 没有高潜力新闻，退出")
        return

    # 6. 加载当日已有新闻并合并
    t0 = time.time()
    today, existing_news = load_existing_news()
    final_news = merge_with_existing(processed, existing_news)
    timing["merge"] = time.time() - t0

    # 7. 保存数据
    t0 = time.time()
    save_success = save_news(today, final_news)
    timing["save"] = time.time() - t0

    if save_success:
        # 8. 推送到 GitHub
        logger.info("\n[GitHub] 开始推送...")
        t0 = time.time()
        push_to_github()
        timing["github"] = time.time() - t0

    # 9. 更新已处理的推文ID缓存
    for item in filtered_items:
        tweet_id = extract_tweet_id(item.get("url", ""))
        if tweet_id:
            processed_ids.add(tweet_id)
    save_processed_ids(processed_ids)
    logger.info(f"[缓存] 已更新 {len(processed_ids)} 条推文ID")

    # 10. 统计输出
    generate_report(final_news, timing)


def generate_report(final_news, timing):
    """生成详细的执行报告"""
    if isinstance(timing, dict):
        elapsed = time.time() - timing.get("start", time.time())
        timing_details = timing
    else:
        # 兼容旧版本，timing可能是start_time
        elapsed = time.time() - timing
        timing_details = {}

    # 分级统计
    s_count = len([t for t in final_news if t["level"] == "S"])
    a_count = len([t for t in final_news if t["level"] == "A"])
    b_count = len([t for t in final_news if t["level"] == "B"])
    c_count = len([t for t in final_news if t["level"] == "C"])
    multi_source = len([t for t in final_news if t.get("sources", 1) > 1])

    # 类型统计
    type_counts = {}
    for item in final_news:
        t = item.get("type", "tech")
        type_counts[t] = type_counts.get(t, 0) + 1

    # 标签统计
    tag_counts = {}
    for item in final_news:
        for tag in item.get("tags", []):
            tag_counts[tag] = tag_counts.get(tag, 0) + 1

    # 核心实体统计
    all_entities = set()
    for item in final_news:
        all_entities.update(item.get("entities", []))

    # 关键词预筛选命中情况
    high_priority_count = len([t for t in final_news if t.get("priority_score", 0) >= 15])

    # 今日新增统计
    today_timestamp = int(time.time()) - 86400  # 24小时内
    today_new = len([t for t in final_news if t.get("timestamp", 0) > today_timestamp])

    logger.info("\n" + "=" * 60)
    logger.info("执行完成!")
    logger.info("=" * 60)

    logger.info("\n【选题统计】")
    logger.info(f"  S级(必报): {s_count} 条")
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

    # 详细耗时统计
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
