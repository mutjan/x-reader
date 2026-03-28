#!/usr/bin/env python3
"""
Twitter RSS 数据源获取器
"""
from typing import List
import xml.etree.ElementTree as ET
import requests
from datetime import datetime

from src.fetchers.base import BaseFetcher
from src.models.news import RawNewsItem
from src.config.settings import RSS_CONFIG
from src.utils.common import clean_html, parse_date

class TwitterFetcher(BaseFetcher):
    """Twitter RSS数据源获取器"""

    def __init__(self):
        super().__init__("twitter")
        self.rss_url = RSS_CONFIG["twitter"]["url"]

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
