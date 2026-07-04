"""
新闻处理模块
包括筛选、去重、AI处理等功能
"""
from .filter import NewsFilter
from .duplicate import DuplicateRemover
from .ai_processor import BaseAIProcessor, LocalAgentProcessor, ManualProcessor

__all__ = [
    "NewsFilter",
    "DuplicateRemover",
    "BaseAIProcessor",
    "LocalAgentProcessor",
    "ManualProcessor"
]
