#!/usr/bin/env python3
"""
Fetcher工厂类
根据数据源类型创建对应的Fetcher实例
"""
from typing import Dict, Type, List, Optional

from src.fetchers.base import BaseFetcher
from src.fetchers.twitter_fetcher import TwitterFetcher
from src.fetchers.inoreader_fetcher import InoreaderFetcher

class FetcherFactory:
    """Fetcher工厂类"""

    _fetchers: Dict[str, Type[BaseFetcher]] = {
        "twitter": TwitterFetcher,
        "inoreader": InoreaderFetcher
    }

    @classmethod
    def get_fetcher(cls, source_type: str) -> Optional[BaseFetcher]:
        """
        获取指定类型的Fetcher实例
        :param source_type: 数据源类型（twitter/inoreader）
        :return: Fetcher实例，如果类型不支持返回None
        """
        fetcher_class = cls._fetchers.get(source_type.lower())
        if fetcher_class:
            return fetcher_class()
        return None

    @classmethod
    def get_all_fetchers(cls) -> List[BaseFetcher]:
        """获取所有可用的Fetcher实例"""
        return [fetcher_class() for fetcher_class in cls._fetchers.values()]

    @classmethod
    def get_supported_sources(cls) -> List[str]:
        """获取支持的数据源类型列表"""
        return list(cls._fetchers.keys())

    @classmethod
    def register_fetcher(cls, source_type: str, fetcher_class: Type[BaseFetcher]) -> None:
        """注册新的Fetcher类型"""
        cls._fetchers[source_type.lower()] = fetcher_class
