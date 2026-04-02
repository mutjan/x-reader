#!/usr/bin/env python3
"""
相似度计算工具类
用于新闻事件分组的相似度计算
"""
from typing import List, Set
import re
from collections import Counter

def jaccard_similarity(set_a: Set, set_b: Set) -> float:
    """计算Jaccard相似度：交集/并集"""
    if not set_a or not set_b:
        return 0.0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union > 0 else 0.0

def cosine_similarity(text1: str, text2: str) -> float:
    """计算余弦相似度（基于词频）"""
    # 分词：简单按非字母数字字符分割
    def get_words(text: str) -> List[str]:
        text = text.lower()
        words = re.findall(r'[\w\u4e00-\u9fff]+', text)
        # 过滤掉太短的词
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
    计算两条新闻的综合相似度
    :param news1: ProcessedNewsItem 对象1
    :param news2: ProcessedNewsItem 对象2
    :param entity_threshold: 共同实体阈值，低于此值直接返回0
    :param similarity_threshold: 相似度阈值，默认0.85
    :return: 0-1的相似度值
    """
    # 1. 先检查共同实体数量
    common_entities = set(news1.entities) & set(news2.entities)
    if len(common_entities) < entity_threshold:
        return 0.0

    # 2. 计算标题相似度（权重0.6）
    title_sim = cosine_similarity(news1.chinese_title, news2.chinese_title)

    # 3. 计算摘要相似度（权重0.4）
    summary_sim = cosine_similarity(news1.summary, news2.summary)

    # 4. 综合相似度
    combined_sim = title_sim * 0.6 + summary_sim * 0.4

    return combined_sim if combined_sim >= similarity_threshold else 0.0
