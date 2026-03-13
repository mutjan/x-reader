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


# ==================== 工具函数 ====================

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


def filter_recent_items(items, hours=1):
    """筛选最近 N 小时的内容"""
    cutoff = int(time.time()) - (hours * 3600)
    recent = [item for item in items if item["published"] >= cutoff]
    logger.info(f"[筛选] 最近 {hours} 小时: {len(recent)}/{len(items)} 条")
    return recent


# ==================== 关键词预筛选（优化版） ====================

def extract_priority_keywords(text):
    """从文本中提取匹配的高优先级关键词"""
    if not text:
        return [], {}

    text_lower = text.lower()
    matched_keywords = []
    matched_categories = {}

    whole_word_keywords = {'rl', 'pi', 'agi', 'mcp', 'o1', 'o3', 'o4', 'gpt', 'vlm'}

    precise_match_keywords = {
        'ide': ['idea', 'identifier', 'identify', 'side', 'aside', 'inside'],
        'ai': ['fail', 'mail', 'sail', 'tail', 'pain', 'paint', 'waiting'],
        'llm': ['all', 'will', 'ball', 'call', 'fall', 'hall', 'tell', 'sell'],
    }

    for category, keywords in PRIORITY_KEYWORDS.items():
        category_matches = []
        for keyword in keywords:
            keyword_lower = keyword.lower()

            if keyword_lower in precise_match_keywords:
                avoid_patterns = precise_match_keywords[keyword_lower]
                is_valid_match = False

                if keyword_lower in text_lower:
                    is_valid_match = True
                    for avoid in avoid_patterns:
                        if avoid in text_lower:
                            pattern = r'(?:^|[^a-z])' + re.escape(keyword_lower) + r'(?:[^a-z]|$)'
                            if not re.search(pattern, text_lower):
                                is_valid_match = False
                                break

                if is_valid_match:
                    matched_keywords.append(keyword)
                    category_matches.append(keyword)

            elif keyword_lower in whole_word_keywords:
                pattern = r'(?:^|[\s\W])' + re.escape(keyword_lower) + r'(?:$|[\s\W])'
                if re.search(pattern, text_lower):
                    matched_keywords.append(keyword)
                    category_matches.append(keyword)
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

    return score, matched_keywords, matched_categories


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

            if item.get("priority_score", 0) >= 15:
                priority_hints.append(
                    f"  新闻#{i}: 匹配关键词 {item['matched_keywords'][:3]} (优先级{item['priority_score']}分)"
                )

        items_for_ai.append(item_data)

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

2. **生成量子位风格中文标题**：
   - 纯中文，无类型前缀
   - 情绪饱满，优先使用"刚刚"、"突发"、"炸裂"、"重磅"、"首次"等词
   - 15-35字，简洁有力
   - **必须使用数字和对比**
   - 标题公式：时间敏感型、数据冲击型、权威引语型、颠覆型

3. **生成一句话摘要**：50-100字，概括核心信息

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


def is_same_event(item1, item2):
    """判断两条新闻是否报道同一事件"""
    title_sim = calculate_similarity(item1.get("title", ""), item2.get("title", ""))
    if title_sim > 0.6:
        return True

    en_title_sim = calculate_similarity(
        item1.get("title_en", ""), item2.get("title_en", "")
    )
    if en_title_sim > 0.6:
        return True

    entities1 = set(item1.get("entities", []))
    entities2 = set(item2.get("entities", []))

    if entities1 and entities2:
        common_entities = entities1 & entities2
        all_entities = entities1 | entities2

        if len(common_entities) >= 2 and len(common_entities) / len(all_entities) > 0.5:
            time1 = item1.get("timestamp", 0)
            time2 = item2.get("timestamp", 0)
            if abs(time1 - time2) < 1800:
                return True

    url1 = item1.get("url", "")
    url2 = item2.get("url", "")
    if url1 and url2:
        tweet_id1 = re.search(r"status/(\d+)", url1)
        tweet_id2 = re.search(r"status/(\d+)", url2)
        if tweet_id1 and tweet_id2:
            if tweet_id1.group(1) == tweet_id2.group(1):
                return True

    return False


def find_duplicate(new_item, existing_items):
    """检查新选题是否与已有选题重复"""
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
        for item in items:
            tweet_id = extract_tweet_id(item.get("url", ""))
            if tweet_id:
                processed_ids.add(tweet_id)
        save_processed_ids(processed_ids)
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

    # 6. 加载当日已有新闻并合并
    t0 = time.time()
    today, existing_news = load_existing_news()

    # 合并逻辑
    merged = existing_news.copy()
    added_count = 0
    updated_count = 0

    for new_item in processed:
        duplicate = find_duplicate(new_item, merged)

        if duplicate:
            existing_links = duplicate.get("sourceLinks", [])
            new_links = new_item.get("sourceLinks", [])
            merged_links = merge_source_links(existing_links, new_links)

            if len(merged_links) > len(existing_links):
                duplicate["sourceLinks"] = merged_links
                duplicate["sources"] = len(merged_links)
                updated_count += 1
                logger.info(f"[合并] 更新来源: {new_item['title'][:30]}...")
        else:
            merged.append(new_item)
            added_count += 1
            logger.info(f"[合并] 新增选题: {new_item['title'][:30]}...")

    logger.info(f"[合并] 新增 {added_count} 条, 更新 {updated_count} 条")
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

    # 8. 更新已处理的推文ID缓存
    for item in filtered_items:
        tweet_id = extract_tweet_id(item.get("url", ""))
        if tweet_id:
            processed_ids.add(tweet_id)
    save_processed_ids(processed_ids)
    logger.info(f"[缓存] 已更新 {len(processed_ids)} 条推文ID")

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
