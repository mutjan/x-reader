#!/usr/bin/env python3
"""
Inoreader API 数据源获取器
"""
from typing import List, Dict, Any
import requests
from datetime import datetime, timedelta
import time

from src.fetchers.base import BaseFetcher
from src.models.news import RawNewsItem
from src.config.settings import RSS_CONFIG
from src.utils.common import clean_html, parse_date
from src.utils.auth import get_inoreader_auth

class InoreaderFetcher(BaseFetcher):
    """Inoreader API数据源获取器"""

    def __init__(self):
        super().__init__("inoreader")
        self.api_base = RSS_CONFIG["inoreader"]["api"]
        self.auth = get_inoreader_auth()

    def fetch(self, time_window_hours: int = 24) -> List[RawNewsItem]:
        """获取Inoreader内容"""
        if not self.auth.is_authenticated():
            self.logger.error("Inoreader未认证，请先运行授权流程")
            return []

        self.logger.info(f"开始获取Inoreader内容（最近{time_window_hours}小时）")

        try:
            access_token = self.auth.get_access_token()
            if not access_token:
                return []

            headers = {
                "Authorization": f"Bearer {access_token}"
            }

            # 计算时间窗口（Unix时间戳，秒）
            cutoff_time = time.time() - time_window_hours * 3600

            # 获取订阅流
            params = {
                "n": 200,  # 最多获取200条
                "ot": int(cutoff_time),  # 只获取指定时间之后的内容
                "output": "json"
            }

            response = requests.get(
                f"{self.api_base}/stream/contents/user/-/state/com.google/reading-list",
                headers=headers,
                params=params,
                timeout=30
            )
            response.raise_for_status()

            data = response.json()
            items = []

            for item in data.get("items", []):
                # 提取标题
                title = item.get("title", "").strip()

                # 提取内容
                content = ""
                if "summary" in item:
                    content = item["summary"].get("content", "")
                elif "content" in item:
                    content = item["content"].get("content", "")

                # 清理HTML
                content = clean_html(content)

                # 提取URL
                url = ""
                if "canonical" in item and len(item["canonical"]) > 0:
                    url = item["canonical"][0].get("href", "")
                elif "alternate" in item and len(item["alternate"]) > 0:
                    url = item["alternate"][0].get("href", "")

                # 提取来源
                source = "Inoreader"
                if "origin" in item:
                    source = item["origin"].get("title", "Inoreader")

                # 提取发布时间
                published_at = datetime.fromtimestamp(item.get("published", time.time()))

                if not title and not content:
                    continue

                raw_item = RawNewsItem(
                    title=title,
                    content=content,
                    source=source,
                    url=url,
                    published_at=published_at,
                    raw_data=item
                )
                items.append(raw_item)

            self.logger.info(f"获取到 {len(items)} 条Inoreader新闻")
            return items

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                self.logger.error("Inoreader认证失败，token可能已过期")
                # 尝试刷新token
                if self.auth.refresh_token():
                    self.logger.info("Token刷新成功，重试获取内容")
                    return self.fetch(time_window_hours)
            self.logger.error(f"获取Inoreader内容失败: {e}")
            return []
        except Exception as e:
            self.logger.error(f"获取Inoreader内容异常: {e}")
            return []

    def test_connection(self) -> bool:
        """测试Inoreader连接"""
        if not self.auth.is_authenticated():
            self.logger.error("Inoreader未认证")
            return False

        try:
            access_token = self.auth.get_access_token()
            if not access_token:
                return False

            headers = {
                "Authorization": f"Bearer {access_token}"
            }

            response = requests.get(
                f"{self.api_base}/user-info",
                headers=headers,
                timeout=10
            )
            return response.status_code == 200
        except Exception as e:
            self.logger.error(f"Inoreader连接测试失败: {e}")
            return False

    def mark_as_read(self, item_ids: List[str]) -> bool:
        """标记文章为已读"""
        if not self.auth.is_authenticated():
            return False

        try:
            access_token = self.auth.get_access_token()
            if not access_token:
                return False

            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/x-www-form-urlencoded"
            }

            data = {
                "a": "user/-/state/com.google/read",
                "i": item_ids
            }

            response = requests.post(
                f"{self.api_base}/edit-tag",
                headers=headers,
                data=data,
                timeout=30
            )
            response.raise_for_status()
            self.logger.info(f"已标记 {len(item_ids)} 条文章为已读")
            return True

        except Exception as e:
            self.logger.error(f"标记已读失败: {e}")
            return False
