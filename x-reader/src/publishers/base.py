#!/usr/bin/env python3
"""
发布器基类
定义所有发布器的统一接口
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any

from src.models.news import ProcessedNewsItem
from src.utils.common import setup_logger

class BasePublisher(ABC):
    """发布器抽象基类"""

    def __init__(self, publisher_name: str):
        self.publisher_name = publisher_name
        self.logger = setup_logger(f"publisher.{publisher_name}")

    @abstractmethod
    def publish(self, items: List[ProcessedNewsItem], **kwargs) -> bool:
        """
        发布新闻项
        :param items: 处理后的新闻项列表
        :param kwargs: 额外参数
        :return: 是否发布成功
        """
        pass

    @abstractmethod
    def test_connection(self) -> bool:
        """测试发布目标连接是否正常"""
        pass
