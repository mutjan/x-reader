#!/usr/bin/env python3
"""
Twitter RSS 新闻选题更新脚本
- 从 Twitter List RSS 获取内容
- 选题筛选由本地模型完成（无需API配置）
- 与当日已有选题去重合并
- 推送到 GitHub Pages

使用方式：
1. 直接运行：python3 update_twitter_news.py
2. 脚本会自动生成 twitter_ai_prompt.txt
3. 将内容发送给本地AI模型（如Claude Desktop）处理
4. 将模型返回的JSON保存为 twitter_ai_result.json
5. 再次运行脚本完成合并

或者使用自动化模式（推荐）：
- 通过外部调度器自动完成步骤3-4
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
    1. 中文引号 " " 替换为转义的英文引号 \\"
    2. 控制字符过滤
    3. 换行符统一处理
    4. 修复AI可能生成的错误JSON格式
    5. 修复字符串内未转义的引号

    关键：字符串内部的中文双引号必须转义为 \\" 才能保留在JSON中
    """
    if not isinstance(text, str):
        return text

    # 步骤1: 保护已转义的引号 \\" (反斜杠+双引号)
    PLACEHOLDER = "<<<ESCAPED_QUOTE>>>"
    text = text.replace('\\"', PLACEHOLDER)

    # 步骤2: 替换中文双引号为转义的英文双引号 \\"
    # 使用Unicode码点来区分中英文引号
    # U+201C = "  U+201D = "
    text = text.replace('\u201C', '\\"').replace('\u201D', '\\"')
    # 替换全角双引号 U+FF02
    text = text.replace('＂', '\\"')

    # 步骤3: 替换中文单引号为普通英文单引号
    # U+2018 = '  U+2019 = '
    text = text.replace('\u2018', "'").replace('\u2019', "'")
    text = text.replace("＇", "'")

    # 步骤4: 替换其他可能的中文引号变体
    text = text.replace('「', '[').replace('」', ']')
    text = text.replace('『', '[').replace('』', ']')
    text = text.replace('【', '[').replace('】', ']')

    # 步骤5: 恢复已转义的引号
    text = text.replace(PLACEHOLDER, '\\"')

    # 步骤6: 修复常见的AI生成JSON错误：属性名未加引号
    # 例如：{title: "xxx"} -> {"title": "xxx"}
    text = re.sub(r'([{,]\s*)([a-zA-Z_][a-zA-Z0-9_]*)(\s*:)', r'\1"\2"\3', text)

    # 步骤7: 修复尾部逗号（在}或]前的多余逗号）
    text = re.sub(r',(\s*[}\]])', r'\1', text)

    return text


def sanitize_json_content_for_ai(text):
    """
    为AI生成的JSON内容做预处理，防止中文引号问题
    在保存AI结果前调用此函数处理

    关键：中文双引号必须转义为 \" 才能在JSON字符串内部保留
    """
    if not isinstance(text, str):
        return text

    # 替换中文双引号为转义的英文双引号 \"
    # 这样在JSON字符串内部就是合法的
    # 左双引号 U+201C -> \"
    text = text.replace('\u201c', '\\"')
    # 右双引号 U+201D -> \"
    text = text.replace('\u201d', '\\"')
    # 全角双引号
    text = text.replace('＂', '\\"')

    # 中文单引号替换为普通英文单引号（单引号在JSON字符串内是合法字符）
    # 左单引号 U+2018 -> '
    text = text.replace('\u2018', "'")
    # 右单引号 U+2019 -> '
    text = text.replace('\u2019', "'")

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

    # 解析错误位置
    match = re.search(r'line (\d+) column (\d+)', str(error))
    if match:
        error_info["line"] = int(match.group(1))
        error_info["column"] = int(match.group(2))

        # 提取错误行内容
        lines = json_str.split('\n')
        if 0 <= error_info["line"] - 1 < len(lines):
            error_line = lines[error_info["line"] - 1]
            error_info["error_line_content"] = error_line

            # 诊断常见问题
            if '"' in error_line or '"' in error_line:
                error_info["suggestions"].append("检测到中文引号，请替换为英文引号")
            if "'" in error_line and '"' not in error_line[:error_info["column"]]:
                error_info["suggestions"].append("检测到单引号，JSON标准使用双引号")
            if re.search(r'\w+\s*:', error_line) and not re.search(r'"\w+"\s*:', error_line):
                error_info["suggestions"].append("属性名可能缺少引号，如 {key: value} 应改为 {\"key\": value}")
            if re.search(r',\s*[}\]]', error_line):
                error_info["suggestions"].append("检测到尾部逗号，JSON不允许最后一个属性后跟逗号")

    # 全局检查
    if '\\n' in json_str and '"\\n"' not in json_str:
        error_info["suggestions"].append("检测到未转义的换行符")
    if json_str.count('{') != json_str.count('}'):
        error_info["suggestions"].append("大括号不匹配")
    if json_str.count('[') != json_str.count(']'):
        error_info["suggestions"].append("方括号不匹配")

    return error_info


def safe_json_loads(json_str, max_retries=3):
    """安全加载JSON字符串，带重试和清理机制

    Args:
        json_str: JSON字符串
        max_retries: 最大重试次数

    Returns:
        解析后的Python对象，失败返回None
    """
    original_str = json_str  # 保存原始字符串用于诊断

    for attempt in range(max_retries):
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.warning(f"JSON解析失败 (尝试 {attempt + 1}/{max_retries}): {e}")

            # 诊断错误
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

    # 修复字符串内部的未转义双引号
    json_str = fix_unescaped_quotes_in_json_strings(json_str)

    return json_str


def fix_unescaped_quotes_in_json_strings(text):
    """
    修复JSON字符串内部的未转义双引号

    这是AI生成JSON时的常见问题：
    错误: "summary": "He said "Hello" to me"
    正确: "summary": "He said \"Hello\" to me"

    算法：逐行处理，识别JSON字符串值模式并修复
    """
    if not isinstance(text, str):
        return text

    lines = text.split('\n')
    fixed_lines = []

    for line in lines:
        # 检测类似 "key": "value" 的模式
        # 使用更宽松的正则来匹配
        match = re.match(r'^(\s*"[^"]+"\s*:\s*")(.*)("\s*,?\s*)$', line)
        if match:
            prefix = match.group(1)  # "key": "
            content = match.group(2)  # 字符串内容（可能包含未转义的引号）
            suffix = match.group(3)  # ", 或 "

            # 转义内容中的未转义双引号
            fixed_content = escape_quotes_in_string_content(content)
            fixed_lines.append(prefix + fixed_content + suffix)
        else:
            fixed_lines.append(line)

    return '\n'.join(fixed_lines)


def escape_quotes_in_string_content(content):
    """
    转义字符串内容中的未转义双引号

    将内容中所有未转义的 " 替换为 \"
    """
    result = []
    i = 0
    while i < len(content):
        if content[i] == '"':
            # 检查前面是否有反斜杠（考虑连续的转义）
            backslash_count = 0
            j = i - 1
            while j >= 0 and content[j] == '\\':
                backslash_count += 1
                j -= 1

            if backslash_count % 2 == 0:
                # 偶数个反斜杠（包括0个），说明这个引号是未转义的
                result.append('\\"')
            else:
                # 奇数个反斜杠，说明这个引号已经被转义
                result.append('"')
        else:
            result.append(content[i])
        i += 1

    return ''.join(result)


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
           # MCP、Function Calling、Tool Use
           "mcp", "model context protocol", "function calling", "tool use", "tool calling",
           # NVIDIA模型
           "nemotron", "nemotron 3", "nemotron 4", "nemotron 3 super", "nvidia nemotron"],
    # 科技巨头动态
    "bigtech": ["apple intelligence", "apple ai", "google ai", "microsoft ai", "meta ai",
                "amazon ai", "nvidia", "tesla fsd", "spacex", "neuralink", "starlink",
                "waymo", "alphabet", "meta", "字节", "bytedance", "腾讯", "tencent",
                "阿里", "alibaba", "百度", "baidu", "华为", "huawei", "xiaomi", "小米",
                "meituan", "美团", "pinduoduo", "拼多多", "jd", "京东", "kuaishou", "快手",
                # 智谱、月之暗面等国产AI公司
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
               # 更多AI领域重要人物
               "alexandr wang", "scale ai", "emmett shear", "jensen huang", "黄仁勋"],
    # 科研突破
    "research": ["nature", "science", "cell", "arxiv", "breakthrough", "milestone",
                 "首次", "第一次", "创造历史", "里程碑", "新发现", "重大突破", "颠覆性",
                 "state-of-the-art", "sota", "novel", "innovative", "pioneering",
                 "ai for science", "ai4science", "protein folding", "drug discovery",
                 "mathematics", "theorem proving", "frontiermath",
                 # 更多科研相关
                 "benchmark", "evaluation", "dataset", "开源数据集",
                 # AI for Science 专项
                 "alphaevolve", "alpha evolve", "deepmind", "alphafold",
                 "ramsey", "组合数学", "extremal combinatorics",
                 "materials discovery", "材料发现", "weather forecasting",
                 "climate modeling", "分子模拟", "quantum chemistry",
                 "drug design", "蛋白质设计", "基因编辑", "crispr"],
    # 商业/融资
    "business": ["ipo", "上市", "收购", "并购", "融资", "估值", "独角兽", "merger",
                 "acquisition", "funding", "valuation", "unicorn", "series a", "series b",
                 "series c", "investment", "investor", "share price", "market cap",
                 "revenue", "profit", "earnings", "quarterly", "财报"],
    # 多模态/视频生成
    "multimodal": ["sora", "video generation", "text-to-video", "image generation",
                   "text-to-image", "multimodal", "vision model", "vlm", "diffusion",
                   "stable diffusion", "dalle", "dall-e", "midjourney", "flux",
                   # 更多图像/视频生成工具
                   "runway", "pika", "heygen", "elevenlabs", "voice clone"],
    # AI编程/工具 - 大幅扩展
    "coding": ["cursor", "windsurf", "github copilot", "code generation", "ai coding",
               "devin", "coding agent", "programming assistant", "ide", "vscode",
               "ai engineer", "software engineer", "swe", "swe-bench",
               # 更多AI编程相关
               "code review", "code completion", "autocomplete", "refactor",
               "unit test", "test generation", "documentation", "api design",
               "vibe coding", "vibecoding", "trae", "cline", "aider", "continue.dev"],
    # 具身智能/机器人 - 大幅扩展
    "robotics": ["robotics", "robot", "embodied ai", "humanoid", "boston dynamics",
                 "figure ai", "tesla bot", "optimus", "autonomous", "self-driving",
                 # 更多机器人公司和概念
                 "agility robotics", "digit", "apptronik", "apollo", "1x technologies",
                 "covariant", "physical intelligence", "pi", "general purpose robot",
                 "manipulation", "grasping", "locomotion", "teleoperation",
                 # 更多具身智能相关
                 "embodied intelligence", "具身智能", "人形机器人",
                 "mobile manipulation", "dexterous manipulation", "灵巧操作",
                 "sim2real", "sim to real", "domain randomization",
                 "reinforcement learning robotics", "rl for robotics",
                 "foundation model robotics", "rt-2", "rt-x", "open x-embodiment",
                 "unitree", "宇树", "智元机器人", "远征", "傅利叶", "frank emika"],
    # 新增：裁员/就业市场影响
    "layoff": ["layoff", "layoffs", "裁员", "失业", "job cut", "workforce reduction",
               "headcount reduction", "headcount", "fired", "terminated", "hiring freeze",
               "招聘冻结", "job loss", "restructure", "restructuring", "组织调整",
               "人员优化", "人力成本", "downsizing", "redundancy",
               # AI替代相关
               "ai replace", "ai replacement", "自动化", "automation", "取代工作",
               "job displacement", "career transition", "技能转型", "ai agent替代",
               "agent替代", "ai裁员", "ai裁员潮"],
    # 新增：医疗/生物科技AI
    "healthcare": ["cancer", "癌症", "cancer screening", "cancer detection",
                   "medical ai", "health ai", "clinical ai", "diagnosis", "诊断",
                   "drug discovery", "药物发现", "clinical trial", "临床试验",
                   "fda approval", "fda批准", "medical device", "医疗器械",
                   "radiology", "病理", "pathology", "imaging", "医学影像",
                   "biotech", "biotechnology", "基因", "gene", "genomics", "基因组",
                   "nature cancer", "nature medicine", "cell", "science", "nejm",
                   "nhs", "imperial college", "jeff dean"],
}

# 所有关键词合并为一个列表用于快速匹配
ALL_PRIORITY_KEYWORDS = []
for category, keywords in PRIORITY_KEYWORDS.items():
    ALL_PRIORITY_KEYWORDS.extend(keywords)

# GitHub 配置
GITHUB_REPO = "x-reader"  # 根据实际情况修改
GITHUB_BRANCH = "main"

# ==================== 批处理累积配置 ====================
# 改进：当新内容不足时暂存，累积到一定数量再统一处理
BATCH_QUEUE_FILE = ".batch_queue.json"
BATCH_MIN_THRESHOLD = 5  # 最少需要5条才进行AI处理（从10条降低到5条）
BATCH_MAX_AGE_HOURS = 12  # 队列中内容最大保留时间（小时，从24改为12）


def load_batch_queue():
    """加载批处理队列中的待处理内容"""
    if not os.path.exists(BATCH_QUEUE_FILE):
        return {"items": [], "queued_at": None, "last_reported": None}
    try:
        with open(BATCH_QUEUE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"[批处理] 加载队列失败: {e}")
        return {"items": [], "queued_at": None, "last_reported": None}


def save_batch_queue(queue_data):
    """保存批处理队列"""
    try:
        with open(BATCH_QUEUE_FILE, "w", encoding="utf-8") as f:
            json.dump(queue_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"[批处理] 保存队列失败: {e}")


def add_to_batch_queue(new_items):
    """将新内容加入批处理队列"""
    queue = load_batch_queue()

    # 初始化队列时间
    if not queue["queued_at"]:
        queue["queued_at"] = datetime.now().isoformat()

    # 去重：检查是否已存在相同URL的内容
    existing_urls = {item.get("url", "") for item in queue["items"]}
    added_count = 0

    for item in new_items:
        if item.get("url", "") not in existing_urls:
            queue["items"].append(item)
            existing_urls.add(item["url"])
            added_count += 1

    save_batch_queue(queue)
    return added_count, len(queue["items"])


def get_batch_queue_for_processing():
    """获取队列中的内容用于处理，并清空队列"""
    queue = load_batch_queue()
    items = queue.get("items", [])

    # 清空队列
    save_batch_queue({"items": [], "queued_at": None, "last_reported": None})

    return items


def should_force_process(queue_data):
    """判断是否应该强制处理队列（超过最大保留时间）"""
    if not queue_data.get("queued_at"):
        return False

    try:
        queued_time = datetime.fromisoformat(queue_data["queued_at"])
        age_hours = (datetime.now() - queued_time).total_seconds() / 3600
        return age_hours >= BATCH_MAX_AGE_HOURS
    except:
        return False


def report_pending_items(queue_data, force=False):
    """报告待处理的新内容

    Args:
        queue_data: 队列数据
        force: 是否强制报告（即使之前报告过）
    """
    items = queue_data.get("items", [])
    if not items:
        return

    last_reported = queue_data.get("last_reported")
    current_count = len(items)

    # 如果数量没有变化且不是强制报告，则跳过
    if not force and last_reported == current_count:
        return

    # 更新最后报告数量
    queue_data["last_reported"] = current_count
    save_batch_queue(queue_data)

    # 生成报告
    logger.info("\n" + "=" * 60)
    logger.info("【待处理新内容报告】")
    logger.info("=" * 60)
    logger.info(f"当前队列中有 {current_count} 条待处理内容（达到 {BATCH_MIN_THRESHOLD} 条将自动处理）")
    logger.info(f"队列开始时间: {queue_data.get('queued_at', 'N/A')}")

    # 按优先级排序显示
    scored_items = []
    for item in items:
        score, keywords, _ = calculate_priority_score(item)
        scored_items.append((score, keywords, item))

    scored_items.sort(key=lambda x: x[0], reverse=True)

    logger.info("\n待处理内容预览（按优先级排序）:")
    for i, (score, keywords, item) in enumerate(scored_items[:15], 1):
        keyword_str = ", ".join(keywords[:3]) if keywords else "无"
        title = item.get("title", "")[:50]
        logger.info(f"  {i}. [{score}分] {title}... (关键词: {keyword_str})")

    if len(scored_items) > 15:
        logger.info(f"  ... 还有 {len(scored_items) - 15} 条内容")

    logger.info("\n提示: 可以手动运行脚本并设置环境变量 FORCE_PROCESS=1 来立即处理队列")
    logger.info("=" * 60)

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
        # 新增：intel 与 intelligence 的误匹配处理
        'intel': ['intelligence', 'intelligent', 'intellectual', 'intellect', 'intelligently', 'intelligible', 'unintelligible'],
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
    改进：增加"独家/首发"和"多源验证"加分项
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

    # 独家/首发加分：权威媒体的独家报道
    exclusive_keywords = ['exclusive', '独家', 'breaking', '突发', 'first look', 'first look at',
                          'just announced', '刚刚发布', '首次', 'first time', 'preview',
                          # 新增：战略合作/合资企业相关
                          'joint venture', '合资企业', 'consulting venture', 'strategic partnership',
                          '战略合作', '独家报道', '独家披露', '独家消息', 'first reported',
                          '独家首发', '全网首发', '全球首发', 'industry first']
    text_lower = text.lower()
    for kw in exclusive_keywords:
        if kw.lower() in text_lower:
            score += 8  # 独家报道额外加8分
            matched_keywords.append(f"[独家]{kw}")
            break  # 只加一次

    # 多源验证加分：检测是否有多个来源引用（在content中检测链接或@提及）
    # 这个在预筛选阶段较难判断，留给AI处理阶段，但可以先标记
    source_indicators = ['the information', 'bloomberg', 'reuters', 'techcrunch', 'the verge',
                         'wired', 'mit technology review', 'nature', 'science', 'arxiv',
                         # 新增：更多权威科技媒体
                         'financial times', 'ft', 'wall street journal', 'wsj',
                         'new york times', 'nyt', 'washington post', 'the guardian',
                         'cnbc', 'cnn', 'forbes', 'fortune', 'business insider',
                         'axios', 'protocol', 'the block', 'decrypt',
                         'venturebeat', 'zdnet', 'arstechnica', 'engadget']
    authoritative_sources = sum(1 for src in source_indicators if src.lower() in text_lower)
    if authoritative_sources >= 2:
        score += 5  # 多个权威源提及加5分
        matched_keywords.append(f"[多源验证]{authoritative_sources}源")
    elif authoritative_sources == 1:
        score += 2  # 单个权威源提及加2分
        matched_keywords.append("[权威信源]")

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


# ==================== AI 处理（本地模型模式） ====================

def ai_process_items_direct(items, enable_keyword_hint=True):
    """直接在当前AI环境中处理新闻选题（无需API配置）

    此函数生成处理指令和输入数据，由调用方（Claude Desktop等）直接处理
    并返回处理结果，完全绕过API调用和文件IO。

    Args:
        items: 新闻列表
        enable_keyword_hint: 是否启用关键词预筛选提示

    Returns:
        (prompt, items_for_ai): 提示词和处理后的数据，供直接处理
    """
    if not items:
        return None, []

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

1. **筛选选题**（S级/A+级/A级/B级）：
   - S级（90-100分）：真正的里程碑事件
     * AI大模型重大发布（GPT-5、Claude 4、Gemini 2等）
     * 马斯克/SpaceX/Neuralink重大动态
     * Nature/Science/Cell顶刊发表
     * 科技巨头重大战略调整或人事变动（CEO级别）
     * AGI相关重大进展或权威预测
     * 顶级AI研究者（如Karpathy、Hassabis）的重大开源项目
     * **独家/首发重大新闻**（The Information、Bloomberg等权威媒体独家报道的突破性消息）
     * **多源验证的重大突破**（被多个权威科技媒体同时报道的重要进展）
   - A+级（85-89分）：重要但非里程碑（原S-级）
     * 重要产品更新（如GPT-4.5、Claude 3.5重大升级）
     * 重要技术突破（如解决FrontierMath难题）
     * 知名人物重要观点/专访
     * 大额融资（5亿美元以上）
     * **独家报道的重要战略调整**（如The Information独家披露的产品路线图）
   - A级（75-84分）：
     * 科技巨头常规产品更新（OpenAI、Google、Microsoft、Meta等）
     * 国产大模型重要进展（DeepSeek、文心一言、通义千问等）
     * 开源项目爆款/Star数激增
     * 学术突破（arxiv重要论文）
     * 资本市场重大动态（IPO、中等规模融资）
     * **多源报道的技术进展**（2个以上权威源报道的同一技术突破）
     * **知名AI研究者转发或参与的项目**（Jeff Dean、Fei-Fei Li、Andrej Karpathy、Yann LeCun、Yoshua Bengio、Geoffrey Hinton、Ilya Sutskever等转发或参与的项目，尤其是种子轮/A轮融资、技术突破、开源项目）
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

   **评分加分项**：
   - 独家/首发报道（标题含"Exclusive"、"独家"、"breaking"、"突发"、"首次"、"first look"、"just announced"、"刚刚发布"等）：+8分
   - 战略合作/合资企业（"joint venture"、"合资企业"、"consulting venture"、"strategic partnership"、"战略合作"）：+8分
   - 多源验证（同一新闻被2个以上权威源报道）：+5分
   - 权威信源（The Information、Bloomberg、Reuters、TechCrunch、Wired、Nature、Science等）：+3分（单个）/+5分（多个）

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
   - **技术类新闻标题优化**（新增）：
     * 突出核心技术突破点：参数规模（1T参数）、上下文长度（100万token）、推理速度（毫秒级延迟）、准确率提升（超越SOTA X%）
     * 强调技术架构创新：MoE架构、Diffusion模型、Transformer改进、多模态融合等
     * 量化技术成果：训练成本降低X%、推理效率提升X倍、能耗减少X%
     * 示例："1T参数+100万上下文！OpenRouter隐身模型炸裂登场，专为Agent设计" → "1T参数+100万token！OpenRouter隐身模型刷新大模型纪录"
     * 示例："Mercury扩散模型速度碾压Groq" → "Mercury扩散模型推理速度超Groq 2倍，延迟仅50ms"
   - 标题示例：
     * "刚刚！Andrej Karpathy开源AgentHub：专为AI Agent打造的GitHub"
     * "GPT-5.4 Pro数学推理炸裂！35分钟破解复杂迷宫"
     * "DeepMind CEO Hassabis：AlphaZero级AI可能在AGI之后出现"
     * "暴涨300%！Sora日活突破300万，OpenAI视频战略逆转"
     * "仅3%渗透率！Microsoft Copilot企业采用率远低于预期"
     * "1T参数+100万token！OpenRouter隐身模型刷新大模型纪录"

3. **生成一句话摘要**：
   - 50-100字
   - 概括核心信息，突出关键数据
   - 说明"为什么重要"

4. **标注类型**：hot(热点)/ai(AI相关)/tech(科技)/business(商业)

5. **识别核心实体**（2-5个）：
   - 公司/组织：如OpenAI、Google、DeepMind、NVIDIA
   - 产品/模型：如ChatGPT、Claude、Sora、Gemini
   - 人物：如Elon Musk、Sam Altman、Demis Hassabis、Andrej Karpathy
     * **重要：人物必须使用完整名称**，如"Jack Dorsey"而非"Jack"，"Amjad Masad"而非"Amjad"
     * 常见人物全称映射：Jack→Jack Dorsey, Amjad→Amjad Masad, Elon→Elon Musk, Sam→Sam Altman
   - 技术/概念：如AGI、Agent、RAG、量子计算
   - **技术/架构类**（新增）：
     * 模型架构：Transformer、MoE、Attention、Encoder-Decoder、Autoregressive
     * 训练技术：RLHF、DPO、Fine-tuning、Pre-training、Distillation、Quantization
     * 推理优化：Speculative Decoding、KV Cache、Flash Attention
     * 学习方法：Chain-of-Thought、Few-shot、In-context Learning
     * 模型类型：VLM、Diffusion Model、Flow Matching、GAN、VAE
   - **新增实体识别**（2025-2026热点）：
     * AI内核生成公司：Standard Kernel、Kernel Generation
     * 空间智能/世界模型：World Labs（李飞飞公司）、Marble、Gaussian Splatting
     * 新兴AI产品：WonderingApp（NotebookLM创始人新项目）、Lovart、Nano Banana
     * AI Agent框架：MCP、Function Calling、Tool Use、Agent Protocol
     * 具身智能公司：Figure AI、1X Technologies、Apptronik、Agility Robotics、Covariant、Physical Intelligence
     * 国产AI：智谱AI、月之暗面/Moonshot、Kimi、MiniMax、零一万物/01.AI、百川智能
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

    # 返回提示词和数据，由调用方直接处理
    return prompt, items_for_ai


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
            # 尝试使用中文引号修复工具
            try:
                import subprocess
                result = subprocess.run(
                    ["python3", "fix_chinese_quotes.py"],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                if result.returncode == 0:
                    # 修复成功，重新加载
                    with open(result_file, "r", encoding="utf-8") as f:
                        content = f.read()
                    data = safe_json_loads(content, max_retries=1)
                    if data is not None:
                        logger.info("[AI] 通过修复工具成功解析结果文件")
                else:
                    logger.warning(f"[AI] 修复工具执行失败: {result.stderr}")
            except Exception as fix_e:
                logger.warning(f"[AI] 尝试修复失败: {fix_e}")

            if data is None:
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
    """提取文本中的核心实体（公司、产品、技术/架构、人名等）

    改进：增加技术/架构类实体识别，新增裁员/医疗AI相关实体，新增人物全称映射
    """
    if not text:
        return set()

    # 人物全称映射表（避免只识别部分名字）
    PERSON_FULL_NAMES = {
        # Jack Dorsey 相关
        'jack': 'Jack Dorsey',
        'jack dorsey': 'Jack Dorsey',
        '@jack': 'Jack Dorsey',
        # Elon Musk 相关
        'elon': 'Elon Musk',
        'musk': 'Elon Musk',
        'elon musk': 'Elon Musk',
        '@elonmusk': 'Elon Musk',
        # Sam Altman 相关
        'sam': 'Sam Altman',
        'altman': 'Sam Altman',
        'sam altman': 'Sam Altman',
        '@sama': 'Sam Altman',
        # Amjad Masad 相关
        'amjad': 'Amjad Masad',
        'amasad': 'Amjad Masad',
        'amjad masad': 'Amjad Masad',
        '@amasad': 'Amjad Masad',
        # Jeff Dean 相关
        'jeff dean': 'Jeff Dean',
        # Demis Hassabis 相关
        'hassabis': 'Demis Hassabis',
        'demis hassabis': 'Demis Hassabis',
        # Andrej Karpathy 相关
        'karpathy': 'Andrej Karpathy',
        'andrej karpathy': 'Andrej Karpathy',
        # Yann LeCun 相关
        'lecun': 'Yann LeCun',
        'yann lecun': 'Yann LeCun',
        '@ylecun': 'Yann LeCun',
        # Fei-Fei Li 相关
        'fei-fei li': 'Fei-Fei Li',
        'fei fei li': 'Fei-Fei Li',
        '李飞飞': 'Fei-Fei Li',
        # Ilya Sutskever 相关
        'ilya': 'Ilya Sutskever',
        'sutskever': 'Ilya Sutskever',
        'ilya sutskever': 'Ilya Sutskever',
        # Scott Wu 相关
        'scott wu': 'Scott Wu',
        # Paul Graham 相关
        'paul graham': 'Paul Graham',
        'pg': 'Paul Graham',
        '@paulg': 'Paul Graham',
        # Jensen Huang 相关
        'jensen huang': 'Jensen Huang',
        '黄仁勋': 'Jensen Huang',
        'huang': 'Jensen Huang',
        # Sundar Pichai 相关
        'sundar pichai': 'Sundar Pichai',
        'pichai': 'Sundar Pichai',
        # Satya Nadella 相关
        'satya nadella': 'Satya Nadella',
        'nadella': 'Satya Nadella',
        # Mark Zuckerberg 相关
        'mark zuckerberg': 'Mark Zuckerberg',
        'zuckerberg': 'Mark Zuckerberg',
        # Tim Cook 相关
        'tim cook': 'Tim Cook',
        # Dario Amodei 相关
        'dario amodei': 'Dario Amodei',
        'amodei': 'Dario Amodei',
        # Geoffrey Hinton 相关
        'geoffrey hinton': 'Geoffrey Hinton',
        'hinton': 'Geoffrey Hinton',
        # Yoshua Bengio 相关
        'yoshua bengio': 'Yoshua Bengio',
        'bengio': 'Yoshua Bengio',
    }

    # 常见科技实体关键词库
    tech_entities = {
        # 公司
        "openai", "anthropic", "google", "microsoft", "meta", "amazon", "nvidia", "apple",
        "tesla", "spacex", "xai", "deepmind", "anthropic", "stability", "midjourney",
        "alibaba", "tencent", "baidu", "bytedance", "huawei", "xiaomi",
        # 产品/模型
        "chatgpt", "gpt", "gpt-4", "gpt-4o", "gpt-5", "claude", "gemini", "llama",
        "dalle", "sora", "midjourney", "stable", "diffusion", "copilot", "cursor",
        # 基础技术/架构
        "llm", "ai", "agi", "agent", "rag", "mcp", "transformer", "diffusion",
        "quantum", "chip", "gpu", "cuda", "neural", "training", "inference",
        # 技术/架构类实体
        "moe", "mixture of experts", "attention", "self-attention", "multi-head attention",
        "encoder", "decoder", "encoder-decoder", "autoregressive", "bidirectional",
        "embedding", "token", "tokenization", "vector", "latent", "latent space",
        "fine-tuning", "pre-training", "post-training", "rlhf", "dpo", "ppo",
        "distillation", "quantization", "pruning", "compression",
        "context window", "long context", "infinite context", "kv cache",
        "prompt", "prompt engineering", "chain of thought", "cot", "few-shot", "zero-shot",
        "hallucination", "alignment", "safety", "guardrails",
        "function calling", "tool use", "tool calling", "api calling",
        "multimodal", "vision", "vlm", "speech", "tts", "asr", "stt",
        "diffusion model", "flow matching", "consistency model", "gflow",
        "vae", "gan", "normalizing flow", "energy-based model",
        "slm", "small language model", "olmoe", "switch transformer",
        "speculative decoding", "lookahead decoding", "flash attention",
        "lora", "qlora", "adapter", "peft", "parameter efficient",
        "synthetic data", "data augmentation", "curriculum learning",
        "test-time compute", "inference-time compute", "scaling law",
        # AI内核生成/空间智能/具身智能实体（2025-2026热点）
        "standard kernel", "kernel generation", "neural kernel",
        "world labs", "marble", "gaussian splatting", "3d gaussian",
        "spatial intelligence", "world model",
        "wonderingapp", "lovart", "nano banana", "notebooklm",
        "mcp", "model context protocol", "agent protocol",
        "figure ai", "1x technologies", "apptronik", "agility robotics",
        "covariant", "physical intelligence", "pi robotics",
        "digit", "apollo", "optimus", "tesla bot",
        "智谱", "zhipu", "月之暗面", "moonshot", "kimi", "minimax",
        "零一万物", "01.ai", "百川智能", "baichuan",
        # 新增：裁员/就业相关公司/实体
        "block", "square", "cash app", "jack dorsey",
        "oracle", "database", "oci", "aws", "azure", "gcp",
        "workforce", "layoff", "裁员", "restructuring",
        # 新增：医疗/生物科技AI实体
        "google health", "deepmind health", "alphafold", "isomorphic labs",
        "recursion", "insitro", "exscientia", "atomwise",
        "cancer research", "cancer detection", "cancer screening",
        "fda", "clinical trial", "drug discovery",
        "medical imaging", "radiology", "pathology",
        "genomics", "proteomics", "crispr", "gene therapy",
        "nhs", "imperial college", "nature cancer", "nature medicine",
        "cell", "science", "nejm", "thelancet",
        # 新增：更多机器人/具身智能公司
        "unitree", "宇树科技", "go2", "b2", "h1",
        "智元机器人", "agibot", "远征", "远征a1", "远征a2",
        "傅利叶智能", "fourier", "gr-1", "gr-2",
        "达闼", "cloudminds", "优必选", "ubtech", "walker",
        "星动纪元", "limx dynamics", "逐际动力", "limx",
        "银河通用", "galaxea", "星尘智能", "stardust",
        "众擎", "engineai", "pm01", "sa01",
        # 新增：AI编程/Agent框架实体
        "replit", "amjad masad", "ghostwriter",
        "sourcegraph", "cody", "tabnine", "codeium",
        "poolside", "magic", "cognition", "cognition labs", "devin",
        "sweep", "mentat", "aider", "continue", "supermaven",
        "v0", "vercel", "bolt", "lovable", "tempo",
        "dimensional", "openclaw", "stash", "physical agent",
        # 新增：更多AI模型/产品
        "nemotron", "nvidia nemotron", "nemotron 3", "nemotron 4", "nemotron 3 super",
        "phi", "phi-4", "phi-3", "microsoft phi",
        "mistral", "mixtral", "pixtral", "codestral",
        "command r", "command r+", "cohere",
        "jamba", "ai21", "jurassic",
        "pangu", "盘古", "文心", "ernie", "通义", "qwen", "kimi k1.5",
        "step", "阶跃", "abab", "spark", "讯飞", "iflytek",
        # 新增：AI基础设施/云服务
        "together ai", "fireworks", "replicate", "baseten", "modal",
        "anyscale", "ray", "vllm", "tensorrt", "triton",
        "huggingface", "hf", "transformers", "datasets",
        "weights & biases", "wandb", "mlflow", "langsmith",
        # 新增：更多重要人物（包含简称和全称，简称用于匹配，全称通过映射表转换）
        # 简称（用于匹配）
        "jack", "amjad", "sam", "elon", "musk", "altman", "hassabis", "amodei", "ilya", "karpathy",
        "pg", "sutskever", "bengio", "hinton", "lecun", "huang", "pichai", "nadella",
        "zuckerberg", "cook", "bezos", "bezos",
        # 全称（也用于匹配）
        "jack dorsey", "block ceo", "amjad masad", "replit ceo",
        "sam altman", "elon musk",
        "jeff dean", "fei-fei li", "李飞飞", "yann lecun", "yoshua bengio",
        "geoffrey hinton", "ilya sutskever",
        "jensen huang", "黄仁勋", "sundar pichai", "satya nadella",
        "mark zuckerberg", "tim cook", "jeff bezos",
        "scott wu", "cognition ceo", "founder",
        "paul graham", "y combinator", "yc",
        " Naval Ravikant", "balaji srinivasan", "patrick collision", "stripe",
    }

    text_lower = text.lower()
    found = set()

    # 第一步：匹配所有科技实体
    for entity in tech_entities:
        if entity in text_lower:
            found.add(entity)

    # 第二步：应用人物全称映射（确保识别完整人名而非简称）
    normalized_found = set()
    for entity in found:
        entity_lower = entity.lower()
        # 检查是否是人物简称，如果是则替换为全称
        if entity_lower in PERSON_FULL_NAMES:
            normalized_found.add(PERSON_FULL_NAMES[entity_lower])
        else:
            normalized_found.add(entity)

    return normalized_found


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

def process_with_ai(items, direct_mode=True):
    """处理新闻：筛选 + 生成标题/摘要/类型

    Args:
        items: 新闻列表
        direct_mode: 是否启用直接调用模式（默认True，直接使用本地模型）
    """
    # 第一步：AI 批量处理
    logger.info(f"[AI] 开始处理 {len(items)} 条新闻...")

    # 检查是否有本地处理结果（用于兼容旧模式）
    ai_results = load_ai_results()
    if ai_results is not None:
        logger.info(f"[AI] 加载到已存在的本地处理结果: {len(ai_results)} 条")
    elif direct_mode:
        # 直接模式：生成提示词和数据，由调用方处理
        logger.info("[AI] 使用直接处理模式（本地模型）")
        prompt, items_for_ai = ai_process_items_direct(items)

        # 保存提示词到文件（方便调试和手动处理）
        with open("twitter_ai_prompt.txt", "w", encoding="utf-8") as f:
            f.write(prompt + "\n\n输入新闻：\n" + json.dumps(items_for_ai, ensure_ascii=False, indent=2))
        logger.info("[AI] 提示词已保存到 twitter_ai_prompt.txt")

        # 返回特殊标记，表示需要外部处理
        return "NEEDS_LOCAL_PROCESSING"
    else:
        # 兼容旧模式：尝试API调用
        logger.info("[AI] 使用API模式（已废弃，建议改用直接模式）")
        return "NEEDS_LOCAL_PROCESSING"

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


def check_and_process_ai_result():
    """
    检查是否存在AI结果文件，如果存在则直接进入合并流程

    Returns:
        (processed, message): 是否处理了AI结果，以及处理消息
    """
    result_file = "twitter_ai_result.json"
    if not os.path.exists(result_file):
        return False, "无AI结果文件"

    logger.info("=" * 60)
    logger.info("【自动合并模式】检测到AI结果文件，直接进入合并流程")
    logger.info("=" * 60)

    try:
        # 加载AI结果
        ai_results = load_ai_results()
        if ai_results is None:
            return False, "AI结果文件加载失败"

        # 构建processed_items（简化版，使用AI结果中的信息）
        processed = []
        for result in ai_results:
            level = result.get("level", "B")
            score = result.get("score", 60)

            processed.append({
                "title": result.get("title", ""),
                "title_en": "",  # 自动合并模式下可能没有原始标题
                "summary": result.get("summary", "点击链接查看详情"),
                "type": result.get("type", "tech"),
                "typeName": ai_detect_type_name(result.get("type", "tech")),
                "score": score,
                "level": level,
                "reason": f"【{level}级】评分{score}分 | {result.get('reason', '')}",
                "entities": result.get("entities", [])[:5],
                "tags": result.get("tags", [])[:5],
                "url": "",  # 自动合并模式下可能没有URL
                "source": "AI",
                "sources": 1,
                "sourceLinks": [],
                "timestamp": int(time.time()),
                "version": generate_version(),
                "priority_score": 0,
            })

        # 按分数排序
        processed.sort(key=lambda x: x["score"], reverse=True)

        logger.info(f"[自动合并] 加载 {len(processed)} 条AI处理结果")

        # 加载当日已有新闻并合并
        today, existing_news = load_existing_news()
        final_news = merge_with_existing(processed, existing_news)

        # 保存数据
        save_success = save_news(today, final_news)

        if save_success:
            # 推送到 GitHub
            logger.info("\n[GitHub] 开始推送...")
            push_to_github()

            # 生成报告
            timing = {"start": time.time()}
            generate_report(final_news, timing)

            return True, f"成功合并 {len(processed)} 条AI处理结果"

        return False, "保存数据失败"

    except Exception as e:
        logger.error(f"[自动合并] 处理失败: {e}")
        return False, f"处理失败: {e}"


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

    # 【新增】检查是否存在AI结果文件，如果存在则直接进入合并流程
    auto_processed, auto_message = check_and_process_ai_result()
    if auto_processed:
        logger.info(f"[启动] 自动合并完成: {auto_message}")
        return
    else:
        logger.info(f"[启动] {auto_message}，继续正常流程")

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

    # 5. 批处理累积逻辑
    # 检查是否强制处理（环境变量或队列超时）
    force_process = os.environ.get("FORCE_PROCESS", "false").lower() == "true"
    queue = load_batch_queue()

    if not force_process and len(filtered_items) < BATCH_MIN_THRESHOLD:
        # 新内容不足阈值，加入队列并报告
        added, total = add_to_batch_queue(filtered_items)
        logger.info(f"[批处理] 新内容 {added} 条（共 {total} 条）已加入队列，等待累积到 {BATCH_MIN_THRESHOLD} 条")

        # 报告待处理内容
        report_pending_items(load_batch_queue())

        # 更新已处理的推文ID缓存
        for item in filtered_items:
            tweet_id = extract_tweet_id(item.get("url", ""))
            if tweet_id:
                processed_ids.add(tweet_id)
        save_processed_ids(processed_ids)

        logger.info("[批处理] 本次执行结束，等待累积更多内容")
        return

    # 检查队列是否需要强制处理（超过最大保留时间）
    if should_force_process(queue):
        logger.info(f"[批处理] 队列内容已超过 {BATCH_MAX_AGE_HOURS} 小时，强制处理")
        force_process = True

    # 合并队列中的内容和当前新内容
    if force_process or len(filtered_items) >= BATCH_MIN_THRESHOLD:
        queued_items = get_batch_queue_for_processing()
        if queued_items:
            logger.info(f"[批处理] 合并队列中的 {len(queued_items)} 条内容与当前 {len(filtered_items)} 条")
            # 去重合并
            existing_urls = {item.get("url", "") for item in filtered_items}
            for item in queued_items:
                if item.get("url", "") not in existing_urls:
                    filtered_items.append(item)
                    existing_urls.add(item["url"])
            logger.info(f"[批处理] 合并后共 {len(filtered_items)} 条内容待处理")

    # 6. AI 处理（本地模型，默认直接模式）
    t0 = time.time()
    # 默认使用直接处理模式，无需API配置
    # 如需强制使用旧模式，可设置环境变量 AI_DIRECT_MODE=false
    direct_mode = os.environ.get("AI_DIRECT_MODE", "true").lower() == "true"
    processed = process_with_ai(filtered_items, direct_mode=direct_mode)
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

    # 分级统计（支持新的A+级）
    s_count = len([t for t in final_news if t["level"] == "S"])
    a_plus_count = len([t for t in final_news if t["level"] == "A+"])
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
