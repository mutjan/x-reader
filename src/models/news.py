#!/usr/bin/env python3
"""
新闻数据模型
定义标准化的新闻数据结构和实体处理逻辑
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any
import re
import hashlib
from src.utils.url import normalize_url

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
            normalized_url = normalize_url(self.url)
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
    sourceLinks: List[Dict[str, str]] = field(default_factory=list)
    sources: int = 1
    event_id: Optional[str] = None  # 所属事件ID，同事件的新闻共享一个ID

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
            "processed_at": self.processed_at.isoformat(),
            "event_id": self.event_id
        }

    def to_frontend_dict(self) -> Dict[str, Any]:
        """转换为前端期望的字典格式"""
        type_map = {
            "product": "产品发布",
            "funding": "融资上市",
            "personnel": "人事变动",
            "opinion": "观点访谈",
            "industry": "行业动态",
            "safety": "安全伦理",
            "research": "研究成果",
            "financial": "商业数据",
            "breaking": "突发事件",
            "tool": "工具技巧",
            "society": "社会影响",
            "hardware": "硬件基建"
        }

        return {
            "id": self.id,
            "title": self.chinese_title,
            "chinese_title": self.chinese_title,
            "original_title": self.original_title,
            "summary": self.summary,
            "rating": self.grade or "C",
            "score": self.score,
            "type": self.news_type,
            "typeName": type_map.get(self.news_type, self.news_type),
            "expansion": self.extension,
            "entities": self.entities,
            "sourceLinks": [{"name": self.source or "Source", "url": self.url}],
            "sources": 1,
            "timestamp": int(self.processed_at.timestamp()),
            "published_at": self.processed_at.isoformat(),
            "source": self.source,
            "url": self.url,
            "event_id": self.event_id
        }

    @classmethod
    def from_frontend_dict(cls, data: Dict[str, Any]) -> 'ProcessedNewsItem':
        """从前端格式(to_frontend_dict的输出)反向加载，自动处理字段映射"""
        published_at = datetime.fromisoformat(data["published_at"]) if data.get("published_at") else datetime.now()
        processed_at = datetime.fromisoformat(data.get("processed_at", "")) if data.get("processed_at") else datetime.now()

        return cls(
            id=data["id"],
            original_title=data.get("original_title", data.get("title", "")),
            original_content=data.get("original_content", ""),
            chinese_title=data.get("chinese_title", data.get("title", "")),
            summary=data.get("summary", ""),
            grade=data.get("grade", data.get("rating", "")),
            score=data.get("score", 0),
            news_type=data.get("type", ""),
            extension=data.get("extension", data.get("expansion", "")),
            entities=data.get("entities", []),
            source=data.get("source", ""),
            url=data.get("url", ""),
            published_at=published_at,
            processed_at=processed_at,
            event_id=data.get("event_id")
        )

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
            processed_at=processed_at,
            event_id=data.get("event_id")
        )

class EntityNormalizer:
    """实体标准化器，统一实体表述"""

    # 实体映射规则（统一英文实体）
    ENTITY_MAPPINGS = {
        # 公司/组织
        "openai": "OpenAI",
        "anthropic": "Anthropic",
        "deepmind": "DeepMind",
        "google deepmind": "DeepMind",
        "xai": "xAI",
        "perplexity": "Perplexity",
        "bytedance": "ByteDance",
        "tiktok": "ByteDance",
        "tencent": "Tencent",
        "alibaba": "Alibaba",
        "baidu": "Baidu",
        "apple": "Apple",
        "google": "Google",
        "microsoft": "Microsoft",
        "meta": "Meta",
        "facebook": "Meta",
        "amazon": "Amazon",
        "nvidia": "NVIDIA",
        "tesla": "Tesla",
        "spacex": "SpaceX",
        "neuralink": "Neuralink",
        "starlink": "Starlink",
        "tsmc": "TSMC",
        "smic": "SMIC",
        "qualcomm": "Qualcomm",

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
        "gemini 3": "Gemini",
        "deepseek": "DeepSeek",
        "grok": "Grok",
        "sora": "Sora",
        "llm": "LLM",
        "large language model": "LLM",
        "foundation model": "Foundation Model",
        "agi": "AGI",
        "mcp": "MCP",
        "model context protocol": "MCP",
        "cuda": "CUDA",
        "h100": "NVIDIA",
        "h200": "NVIDIA",
        "b200": "NVIDIA",
        "gb200": "NVIDIA",
        "gh200": "NVIDIA",
        "a100": "NVIDIA",

        # 人物
        "elon musk": "Elon Musk",
        "musk": "Elon Musk",
        "sam altman": "Sam Altman",
        "altman": "Sam Altman",
        "demis hassabis": "Demis Hassabis",
        "hassabis": "Demis Hassabis",
        "andrej karpathy": "Andrej Karpathy",
        "karpathy": "Andrej Karpathy",
        "sundar pichai": "Sundar Pichai",
        "satya nadella": "Satya Nadella",
        "mark zuckerberg": "Mark Zuckerberg",
        "zuckerberg": "Mark Zuckerberg",
        "李开复": "Kai-Fu Lee",
        "李彦宏": "Robin Li",
        "马化腾": "Pony Ma",
        "马云": "Jack Ma",
        "张一鸣": "Zhang Yiming",
        "雷军": "Lei Jun",

        # 中文名→英文映射（LLM 可能输出中文名）
        "字节跳动": "ByteDance",
        "腾讯": "Tencent",
        "阿里巴巴": "Alibaba",
        "百度": "Baidu",
        "苹果": "Apple",
        "谷歌": "Google",
        "微软": "Microsoft",
        "英伟达": "NVIDIA",
        "特斯拉": "Tesla",
        "台积电": "TSMC",
        "中芯国际": "SMIC",
        "高通": "Qualcomm",
        "亚马逊": "Amazon",
        "大模型": "LLM",
        "基础模型": "Foundation Model",
        "马斯克": "Elon Musk",
        "萨姆·奥尔特曼": "Sam Altman",
        "奥尔特曼": "Sam Altman",
        "戴密斯·哈萨比斯": "Demis Hassabis",
        "哈萨比斯": "Demis Hassabis",
        "安德烈·卡帕西": "Andrej Karpathy",
        "卡帕西": "Andrej Karpathy",
        "桑达尔·皮查伊": "Sundar Pichai",
        "皮查伊": "Sundar Pichai",
        "萨提亚·纳德拉": "Satya Nadella",
        "纳德拉": "Satya Nadella",
        "马克·扎克伯格": "Mark Zuckerberg",
        "扎克伯格": "Mark Zuckerberg"
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
