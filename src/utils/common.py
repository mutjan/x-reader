#!/usr/bin/env python3
"""
通用工具函数
"""
import json
import os
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
import logging
from difflib import SequenceMatcher
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import requests

from src.config.settings import LOGGING_CONFIG

# 网络请求重试装饰器：重试3次，指数退避
def request_retry(max_retries=3):
    return retry(
        stop=stop_after_attempt(max_retries),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((requests.exceptions.RequestException, ConnectionError, TimeoutError)),
        reraise=True
    )

def setup_logger(name: str) -> logging.Logger:
    """设置日志记录器"""
    logging.basicConfig(**LOGGING_CONFIG)
    return logging.getLogger(name)

def load_json(file_path: str, default: Any = None) -> Any:
    """加载JSON文件"""
    if not os.path.exists(file_path):
        return default if default is not None else {}

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger = setup_logger("utils")
        logger.warning(f"加载JSON文件失败 {file_path}: {e}")
        return default if default is not None else {}

def sanitize_content(text: str) -> str:
    """清理内容中的特殊字符，避免破坏JSON格式"""
    if not text:
        return ""

    # 转义所有半角双引号
    text = text.replace('"', '\\"')
    # 统一中文全角引号为半角
    text = text.replace('“', '"').replace('”', '"')
    # 清理其他可能破坏JSON格式的控制字符
    text = text.replace('\n', ' ').replace('\r', '').replace('\t', ' ')
    # 清理多余空白
    text = re.sub(r'\s+', ' ', text).strip()

    return text

def save_json(data: Any, file_path: str, indent: int = 2, ensure_ascii: bool = False) -> bool:
    """保存JSON文件，带格式校验"""
    try:
        # 先序列化再反序列化验证格式正确性
        json_str = json.dumps(data, indent=indent, ensure_ascii=ensure_ascii)
        try:
            json.loads(json_str)  # 验证格式合法性
        except json.JSONDecodeError as e:
            logger = setup_logger("utils")
            logger.error(f"JSON格式校验失败 {file_path}: {e}")
            return False

        # 确保目录存在
        os.makedirs(os.path.dirname(file_path), exist_ok=True)

        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(json_str)
        return True
    except IOError as e:
        logger = setup_logger("utils")
        logger.error(f"保存JSON文件失败 {file_path}: {e}")
        return False

def clean_html(html: str) -> str:
    """清理HTML标签，提取纯文本"""
    if not html:
        return ""

    # 移除script和style标签
    html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)

    # 移除所有HTML标签
    text = re.sub(r'<[^>]+>', ' ', html)

    # 清理多余空白
    text = re.sub(r'\s+', ' ', text).strip()

    return text

def normalize_url(url: str) -> str:
    """标准化URL，用于去重比较"""
    if not url:
        return ""

    # 移除URL参数
    url = url.split('?')[0].split('#')[0]

    # 移除协议头
    url = re.sub(r'^https?://', '', url)

    # 移除末尾斜杠
    url = url.rstrip('/')

    # 转换为小写
    return url.lower()

def is_similar_text(a: str, b: str, threshold: float = 0.7) -> bool:
    """判断两个文本是否相似"""
    if not a or not b:
        return False

    # 计算相似度
    similarity = SequenceMatcher(None, a.lower(), b.lower()).ratio()
    return similarity >= threshold

def parse_date(date_str: str, formats: List[str] = None) -> Optional[datetime]:
    """解析日期字符串，尝试多种格式"""
    if not date_str:
        return None

    if formats is None:
        formats = [
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%a, %d %b %Y %H:%M:%S %z",
            "%a, %d %b %Y %H:%M:%S GMT",
            "%Y-%m-%d",
            "%b %d, %Y"
        ]

    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue

    # 尝试使用dateutil解析（如果可用）
    try:
        from dateutil import parser
        return parser.parse(date_str)
    except (ImportError, ValueError):
        pass

    logger = setup_logger("utils")
    logger.debug(f"无法解析日期: {date_str}")
    return None

def get_time_window(hours: int = 24) -> datetime:
    """获取指定小时数前的时间点"""
    return datetime.now() - timedelta(hours=hours)

def truncate_text(text: str, max_length: int = 200, suffix: str = "...") -> str:
    """截断文本到指定长度"""
    if not text or len(text) <= max_length:
        return text

    return text[:max_length - len(suffix)] + suffix

def extract_domain(url: str) -> str:
    """从URL中提取域名"""
    if not url:
        return ""

    from urllib.parse import urlparse
    parsed = urlparse(url)
    domain = parsed.netloc.lower()

    # 移除www前缀
    if domain.startswith('www.'):
        domain = domain[4:]

    return domain

def slugify(text: str) -> str:
    """将文本转换为URL友好的slug格式"""
    if not text:
        return ""

    # 转换为小写
    text = text.lower()

    # 替换非字母数字字符为连字符
    text = re.sub(r'[^a-z0-9\u4e00-\u9fff]+', '-', text)

    # 移除首尾连字符
    text = text.strip('-')

    return text
