"""
数据获取模块
支持多种数据源（Twitter RSS、Inoreader API等）
"""
from .base import BaseFetcher
from .twitter_fetcher import TwitterFetcher
from .inoreader_fetcher import InoreaderFetcher
from .factory import FetcherFactory

__all__ = [
    "BaseFetcher",
    "TwitterFetcher",
    "InoreaderFetcher",
    "FetcherFactory"
]
