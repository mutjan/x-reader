#!/usr/bin/env python3
"""
Publisher工厂类
根据发布类型创建对应的Publisher实例
"""
from typing import Dict, Type, List, Optional

from src.publishers.base import BasePublisher
from src.publishers.github_pages import GitHubPagesPublisher

class PublisherFactory:
    """Publisher工厂类"""

    _publishers: Dict[str, Type[BasePublisher]] = {
        "github_pages": GitHubPagesPublisher
    }

    @classmethod
    def get_publisher(cls, publisher_type: str) -> Optional[BasePublisher]:
        """
        获取指定类型的Publisher实例
        :param publisher_type: 发布类型（github_pages）
        :return: Publisher实例，如果类型不支持返回None
        """
        publisher_class = cls._publishers.get(publisher_type.lower())
        if publisher_class:
            return publisher_class()
        return None

    @classmethod
    def get_all_publishers(cls) -> List[BasePublisher]:
        """获取所有可用的Publisher实例"""
        return [publisher_class() for publisher_class in cls._publishers.values()]

    @classmethod
    def get_supported_publishers(cls) -> List[str]:
        """获取支持的发布类型列表"""
        return list(cls._publishers.keys())

    @classmethod
    def register_publisher(cls, publisher_type: str, publisher_class: Type[BasePublisher]) -> None:
        """注册新的Publisher类型"""
        cls._publishers[publisher_type.lower()] = publisher_class
