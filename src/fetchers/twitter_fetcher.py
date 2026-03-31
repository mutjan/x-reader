#!/usr/bin/env python3
"""
Twitter RSS 数据源获取器
"""
from typing import List
import xml.etree.ElementTree as ET
import requests
from datetime import datetime
import re

from src.fetchers.base import BaseFetcher
from src.models.news import RawNewsItem
from src.config.settings import RSS_CONFIG
from src.utils.common import clean_html, parse_date

class TwitterFetcher(BaseFetcher):
    """Twitter RSS数据源获取器"""

    def __init__(self):
        super().__init__("twitter")
        self.rss_url = RSS_CONFIG["twitter"]["url"]
        # 转发内容匹配模式
        self.retweet_patterns = [
            # 标准RT格式
            re.compile(r'^RT @[\w_]+: (.*)$', re.DOTALL),
            # 中文转发格式
            re.compile(r'^转发 @[\w_]+: (.*)$', re.DOTALL),
            # 引用转推格式（有换行分隔）
            re.compile(r'^(.*?)\s*Quoted from @[\w_]+:\s*(.*)$', re.DOTALL | re.IGNORECASE),
            # Reposted格式
            re.compile(r'^(.*?)\s*Reposted from @[\w_]+:\s*(.*)$', re.DOTALL | re.IGNORECASE),
            # 另一种引用格式（冒号后直接跟内容）
            re.compile(r'^(.*?)"@[\w_]+: (.*?)"', re.DOTALL),
        ]

    def _parse_twitter_content(self, content: str) -> str:
        """
        解析Twitter内容，对于转发贴，优先使用被转发的原贴内容，转发者的评论作为补充
        :param content: 原始Twitter内容
        :return: 处理后的内容，原贴内容在前，转发评论在后
        """
        if not content:
            return content

        # 尝试匹配各种转发格式
        for pattern in self.retweet_patterns:
            match = pattern.match(content)
            if match:
                groups = match.groups()
                if len(groups) == 1:
                    # 纯转发，无评论，直接使用原贴内容
                    return groups[0].strip()
                elif len(groups) == 2:
                    # 有评论的转发，原贴内容在前，评论在后
                    quote_content = groups[0].strip()
                    original_content = groups[1].strip()
                    if original_content:
                        # 原贴内容作为主要内容，转发评论作为补充
                        if quote_content:
                            return f"{original_content}\n\n转发评论: {quote_content}"
                        return original_content

        # 不是转发贴，返回原内容
        return content

    def fetch(self, time_window_hours: int = 24) -> List[RawNewsItem]:
        """获取Twitter RSS内容"""
        self.logger.info(f"开始获取Twitter RSS内容（最近{time_window_hours}小时）")

        try:
            response = requests.get(self.rss_url, timeout=30)
            response.raise_for_status()

            root = ET.fromstring(response.content)
            items = []

            # RSS 2.0 格式
            for item in root.findall("./channel/item"):
                title_elem = item.find("title")
                description_elem = item.find("description")
                link_elem = item.find("link")
                pub_date_elem = item.find("pubDate")
                creator_elem = item.find("{http://purl.org/dc/elements/1.1/}creator")

                title = title_elem.text.strip() if title_elem is not None and title_elem.text else ""
                description = description_elem.text if description_elem is not None and description_elem.text else ""
                link = link_elem.text.strip() if link_elem is not None and link_elem.text else ""
                pub_date_str = pub_date_elem.text if pub_date_elem is not None else ""
                creator = creator_elem.text if creator_elem is not None else "Twitter"

                # 清理HTML内容
                content = clean_html(description)

                # 解析转发内容，优先使用原贴内容
                content = self._parse_twitter_content(content)

                # 解析发布时间
                published_at = parse_date(pub_date_str) or datetime.now()

                if not title and not content:
                    continue

                raw_item = RawNewsItem(
                    title=title,
                    content=content,
                    source=f"Twitter @{creator}" if creator != "Twitter" else "Twitter",
                    url=link,
                    published_at=published_at,
                    raw_data={
                        "creator": creator,
                        "pub_date_str": pub_date_str
                    }
                )
                items.append(raw_item)

            self.logger.info(f"获取到 {len(items)} 条Twitter新闻")

            # 按时间过滤
            if time_window_hours > 0:
                items = self.filter_by_time(items, time_window_hours)

            return items

        except Exception as e:
            self.logger.error(f"获取Twitter RSS失败: {e}")
            return []

    def test_connection(self) -> bool:
        """测试Twitter RSS连接"""
        try:
            response = requests.head(self.rss_url, timeout=10)
            return response.status_code == 200
        except Exception as e:
            self.logger.error(f"Twitter连接测试失败: {e}")
            return False
