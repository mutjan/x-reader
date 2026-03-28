#!/usr/bin/env python3
"""
新闻数据模型
定义标准化的新闻数据结构和实体处理逻辑
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any
from urllib.parse import urlparse
import re
import hashlib

@dataclass
class RawNewsItem:
    """原始新闻项，从数据源获取的原始数据"""
    title: str
    content: str
    source: str
    url: str
    published_at: datetime = field(default_factory=datetime.now)
    raw_data: Dict[str, Any] = field(default_factory=dict)

    def get_unique_id(self) -> str:
        """生成唯一ID，用于去重"""
        # 使用URL作为主要标识
        if self.url:
            # 标准化URL
            parsed = urlparse(self.url)
            normalized_url = f"{parsed.netloc}{parsed.path}".lower()
            return hashlib.md5(normalized_url.encode()).hexdigest()

        # 如果没有URL，使用标题+内容哈希
        content_hash = hashlib.md5(f"{self.title}{self.content[:200]}".encode()).hexdigest()
        return content_hash

@dataclass
class ProcessedNewsItem:
    """处理后的新闻项，包含AI处理结果"""
    id: str
    original_title: str
    original_content: str
    source: str
    url: str
    published_at: datetime

    # AI处理结果
    chinese_title: str = ""
    summary: str = ""
    grade: str = ""  # S/A+/A/B/C
    score: int = 0
    news_type: str = ""
    extension: str = ""
    entities: List[str] = field(default_factory=list)

    # 元数据
    processed_at: datetime = field(default_factory=datetime.now)
    raw_item: Optional[RawNewsItem] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式，用于存储"""
        return {
            "id": self.id,
            "original_title": self.original_title,
            "original_content": self.original_content,
            "chinese_title": self.chinese_title,
            "summary": self.summary,
            "grade": self.grade,
            "score": self.score,
            "type": self.news_type,
            "extension": self.extension,
            "entities": self.entities,
            "source": self.source,
            "url": self.url,
            "published_at": self.published_at.isoformat(),
            "processed_at": self.processed_at.isoformat()
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ProcessedNewsItem':
        """从字典加载"""
        published_at = datetime.fromisoformat(data["published_at"]) if data.get("published_at") else datetime.now()
        processed_at = datetime.fromisoformat(data["processed_at"]) if data.get("processed_at") else datetime.now()

        return cls(
            id=data["id"],
            original_title=data["original_title"],
            original_content=data["original_content"],
            chinese_title=data.get("chinese_title", ""),
            summary=data.get("summary", ""),
            grade=data.get("grade", ""),
            score=data.get("score", 0),
            news_type=data.get("type", ""),
            extension=data.get("extension", ""),
            entities=data.get("entities", []),
            source=data.get("source", ""),
            url=data.get("url", ""),
            published_at=published_at,
            processed_at=processed_at
        )

class EntityNormalizer:
    """实体标准化器，统一实体表述"""

    # 实体映射规则
    ENTITY_MAPPINGS = {
        # 公司/组织
        "openai": "OpenAI",
        "anthropic": "Anthropic",
        "deepmind": "DeepMind",
        "google deepmind": "DeepMind",
        "xai": "xAI",
        "perplexity": "Perplexity",
        "bytedance": "字节跳动",
        "tiktok": "字节跳动",
        "tencent": "腾讯",
        "alibaba": "阿里巴巴",
        "baidu": "百度",
        "apple": "苹果",
        "google": "谷歌",
        "microsoft": "微软",
        "meta": "Meta",
        "facebook": "Meta",
        "amazon": "亚马逊",
        "nvidia": "英伟达",
        "tesla": "特斯拉",
        "spacex": "SpaceX",
        "neuralink": "Neuralink",
        "starlink": "Starlink",
        "tsmc": "台积电",
        "smic": "中芯国际",
        "qualcomm": "高通",

        # 产品/技术
        "gpt": "GPT",
        "chatgpt": "GPT",
        "gpt-4": "GPT",
        "gpt-5": "GPT",
        "gpt4": "GPT",
        "gpt5": "GPT",
        "claude": "Claude",
        "claude 3": "Claude",
        "claude 4": "Claude",
        "gemini": "Gemini",
        "gemini 2": "Gemini",
        "deepseek": "DeepSeek",
        "grok": "Grok",
        "sora": "Sora",
        "llm": "大模型",
        "large language model": "大模型",
        "foundation model": "基础模型",
        "agi": "AGI",
        "mcp": "MCP",
        "model context protocol": "MCP",
        "cuda": "CUDA",
        "h100": "H100",
        "h200": "H200",
        "b200": "B200",
        "gb200": "GB200",
        "gh200": "GH200",
        "a100": "A100",

        # 人物
        "elon musk": "马斯克",
        "musk": "马斯克",
        "sam altman": "萨姆·奥尔特曼",
        "altman": "萨姆·奥尔特曼",
        "demis hassabis": "戴密斯·哈萨比斯",
        "hassabis": "戴密斯·哈萨比斯",
        "andrej karpathy": "安德烈·卡帕西",
        "karpathy": "安德烈·卡帕西",
        "sundar pichai": "桑达尔·皮查伊",
        "satya nadella": "萨提亚·纳德拉",
        "mark zuckerberg": "马克·扎克伯格",
        "zuckerberg": "马克·扎克伯格",
        "李开复": "李开复",
        "李彦宏": "李彦宏",
        "马化腾": "马化腾",
        "马云": "马云",
        "张一鸣": "张一鸣",
        "雷军": "雷军"
    }

    @classmethod
    def normalize(cls, entity: str) -> str:
        """标准化实体名称"""
        if not entity:
            return entity

        # 转换为小写查找映射
        entity_lower = entity.strip().lower()

        # 移除版本号等后缀
        entity_lower = re.sub(r'[\d\.]+$', '', entity_lower).strip()

        # 查找映射
        if entity_lower in cls.ENTITY_MAPPINGS:
            return cls.ENTITY_MAPPINGS[entity_lower]

        # 如果没有映射，返回原词（首字母大写）
        return entity.strip().title()

    @classmethod
    def normalize_list(cls, entities: List[str]) -> List[str]:
        """标准化实体列表，去重并排序"""
        if not entities:
            return []

        normalized = set()
        for entity in entities:
            norm = cls.normalize(entity)
            if norm:
                normalized.add(norm)

        return sorted(list(normalized))
