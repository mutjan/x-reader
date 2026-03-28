#!/usr/bin/env python3
"""
数据获取器基类
定义所有数据源获取器的统一接口
"""
from abc import ABC, abstractmethod
from typing import List
from datetime import datetime

from src.models.news import RawNewsItem
from src.utils.common import setup_logger

class BaseFetcher(ABC):
    """数据获取器抽象基类"""

    def __init__(self, source_name: str):
        self.source_name = source_name
        self.logger = setup_logger(f"fetcher.{source_name}")

    @abstractmethod
    def fetch(self, time_window_hours: int = 24) -> List[RawNewsItem]:
        """
        获取指定时间窗口内的新闻
        :param time_window_hours: 获取最近多少小时内的新闻
        :return: 原始新闻项列表
        """
        pass

    @abstractmethod
    def test_connection(self) -> bool:
        """测试数据源连接是否正常"""
        pass

    def filter_by_time(self, items: List[RawNewsItem], time_window_hours: int) -> List[RawNewsItem]:
        """按时间窗口过滤新闻项"""
        cutoff_time = datetime.now() - datetime.timedelta(hours=time_window_hours)
        filtered = [item for item in items if item.published_at >= cutoff_time]
        self.logger.info(f"时间过滤后保留 {len(filtered)}/{len(items)} 条新闻（最近{time_window_hours}小时）")
        return filtered
