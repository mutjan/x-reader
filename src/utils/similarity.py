#!/usr/bin/env python3
"""
相似度计算工具类
用于新闻事件分组的相似度计算
"""
from typing import List, Set, Dict, Any, Optional
import re
from collections import Counter

try:
    import jieba
    JIEBA_AVAILABLE = True
except ImportError:
    JIEBA_AVAILABLE = False

# 模块级配置缓存，避免每次调用都读取配置
_threshold_config_cache: Optional[Dict[str, Any]] = None


def _get_threshold_config() -> Dict[str, Any]:
    """加载阈值配置（模块级缓存）。可通过 _reset_config_cache() 重置。"""
    global _threshold_config_cache
    if _threshold_config_cache is None:
        from src.config.settings import EVENT_GROUPER_CONFIG
        _threshold_config_cache = EVENT_GROUPER_CONFIG
    return _threshold_config_cache


def _reset_config_cache():
    """重置配置缓存。仅供测试使用。"""
    global _threshold_config_cache
    _threshold_config_cache = None


def jaccard_similarity(set_a: Set, set_b: Set) -> float:
    """计算Jaccard相似度：交集/并集"""
    if not set_a or not set_b:
        return 0.0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union > 0 else 0.0

def cosine_similarity(text1: str, text2: str) -> float:
    """计算余弦相似度（基于词频）"""
    if JIEBA_AVAILABLE:
        # 使用jieba进行中文分词
        words1 = [w for w in jieba.lcut(text1) if len(w) >= 2]
        words2 = [w for w in jieba.lcut(text2) if len(w) >= 2]
    else:
        # 备用：简单按非字母数字字符分割
        def get_words(text: str) -> List[str]:
            text = text.lower()
            words = re.findall(r'[\w\u4e00-\u9fff]+', text)
            return [w for w in words if len(w) >= 2]
        words1 = get_words(text1)
        words2 = get_words(text2)

    if not words1 or not words2:
        return 0.0

    # 计算词频
    counter1 = Counter(words1)
    counter2 = Counter(words2)

    # 计算点积
    dot_product = 0
    for word in set(counter1.keys()) & set(counter2.keys()):
        dot_product += counter1[word] * counter2[word]

    # 计算模长
    magnitude1 = sum(count ** 2 for count in counter1.values()) ** 0.5
    magnitude2 = sum(count ** 2 for count in counter2.values()) ** 0.5

    if magnitude1 == 0 or magnitude2 == 0:
        return 0.0

    return dot_product / (magnitude1 * magnitude2)

def calculate_news_similarity(news1, news2, entity_threshold: int = 3, similarity_threshold: float = 0.85) -> float:
    """
    计算两条新闻的综合相似度（分层匹配策略）

    核心逻辑：实体是最稳定的事件标识，文本相似度作为辅助验证。
    根据共享的特定实体数量调节文本相似度门槛：
    - ≥2 个特定实体共享 → 文本门槛 0.15（实体已充分表明同一事件）
    - 1 个特定实体共享 → 文本门槛 0.20（需要少量文本佐证）
    - 0 个特定实体共享 → 使用 similarity_threshold（纯靠文本匹配，几乎不聚合）

    :param news1: ProcessedNewsItem 对象1
    :param news2: ProcessedNewsItem 对象2
    :param entity_threshold: 保留兼容，不再作为硬门槛
    :param similarity_threshold: 保留兼容，无特定实体共享时使用此值
    :return: 0-1的相似度值
    """
    # 1. 计算特定实体重叠（排除通用实体）
    generic_entities = {"AI", "人工智能", "机器人", "科技", "技术", "公司", "企业", "产品", "服务", "大模型", "大型语言模型"}
    common_entities = set(news1.entities) & set(news2.entities)
    specific_common = common_entities - generic_entities
    specific_count = len(specific_common)

    # 2. 无特定实体共享 → 使用高文本门槛（几乎不聚合）
    if specific_count == 0:
        text_sim = _text_similarity(news1, news2)
        return text_sim if text_sim >= similarity_threshold else 0.0

    # 3. 根据特定实体数量确定文本门槛和权重（配置驱动阶梯方案）
    config = _get_threshold_config()
    steps = config.get("entity_threshold_steps", [])
    threshold_floor = config.get("threshold_floor", 0.01)

    if steps:
        # 阶梯查找：找到 min_entities <= specific_count 的最高档
        matched_step = None
        for step in sorted(steps, key=lambda s: s["min_entities"]):
            if specific_count >= step["min_entities"]:
                matched_step = step
            else:
                break

        if matched_step:
            text_threshold = max(matched_step["text_threshold"], threshold_floor)
            entity_weight = matched_step["entity_weight"]
            text_weight = matched_step["text_weight"]
        else:
            # specific_count 不匹配任何阶梯（理论上不应发生）
            text_threshold = similarity_threshold
            entity_weight = 0.5
            text_weight = 0.5
    else:
        # 向后兼容：无阶梯配置时使用旧的硬编码行为
        if specific_count >= 2:
            text_threshold = 0.15
        else:
            text_threshold = 0.20
        entity_weight = 0.5
        text_weight = 0.5

    text_sim = _text_similarity(news1, news2)

    if text_sim >= text_threshold:
        # 综合得分：实体匹配 + 文本匹配（动态权重）
        entity_score = min(specific_count / 3.0, 1.0)
        combined = entity_score * entity_weight + text_sim * text_weight
        # Return combined score — callers compare against similarity_threshold
        return combined

    return 0.0


def _text_similarity(news1, news2) -> float:
    """计算标题+摘要的文本相似度"""
    title_sim = cosine_similarity(news1.chinese_title, news2.chinese_title)
    summary_sim = cosine_similarity(news1.summary, news2.summary)
    return title_sim * 0.7 + summary_sim * 0.3
