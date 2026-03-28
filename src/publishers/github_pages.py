#!/usr/bin/env python3
"""
GitHub Pages 发布器
将新闻数据发布到GitHub Pages
"""
from typing import List, Dict, Any
import json
import os
import subprocess
from datetime import datetime, timedelta

from src.publishers.base import BasePublisher
from src.models.news import ProcessedNewsItem
from src.config.settings import DATA_FILE, GITHUB_BRANCH, settings
from src.utils.common import save_json, load_json, is_similar_text

class GitHubPagesPublisher(BasePublisher):
    """GitHub Pages发布器"""

    def __init__(self):
        super().__init__("github_pages")
        self.repo_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.data_file = os.path.join(self.repo_dir, DATA_FILE)
        self.index_html_file = os.path.join(self.repo_dir, "index.html")

    def publish(self, items: List[ProcessedNewsItem], update_existing: bool = True, **kwargs) -> bool:
        """
        发布新闻到GitHub Pages
        :param items: 处理后的新闻项列表
        :param update_existing: 是否更新已存在的新闻
        :param kwargs: 额外参数
        :return: 是否发布成功
        """
        if not items:
            self.logger.warning("没有新闻需要发布")
            return False

        try:
            # 1. 合并新闻数据
            updated_count, new_count = self._merge_news_data(items, update_existing)

            if updated_count == 0 and new_count == 0:
                self.logger.info("没有需要更新的新闻")
                return True

            self.logger.info(f"数据合并完成: 新增{new_count}条, 更新{updated_count}条")

            # 2. 提交并推送
            commit_message = f"更新新闻: 新增{new_count}条, 更新{updated_count}条 [{datetime.now().strftime('%Y-%m-%d %H:%M')}]"
            if self._push_to_github(commit_message):
                self.logger.info("GitHub Pages发布成功")
                return True
            else:
                self.logger.error("GitHub Pages发布失败")
                return False

        except Exception as e:
            self.logger.error(f"发布过程异常: {e}")
            return False

    def _merge_news_data(self, new_items: List[ProcessedNewsItem], update_existing: bool = True) -> tuple[int, int]:
        """
        合并新的新闻数据到现有数据中
        :param new_items: 新的新闻项列表
        :param update_existing: 是否更新已存在的新闻
        :return: (更新数量, 新增数量)
        """
        # 加载现有数据
        existing_data = load_json(self.data_file, {})

        # 兼容旧的列表格式数据
        if isinstance(existing_data, list):
            self.logger.info("检测到旧版列表格式数据，正在转换为按日期分组格式")
            existing_dict = {}
            for item in existing_data:
                try:
                    item_id = item["id"]
                    existing_dict[item_id] = item
                except Exception as e:
                    self.logger.warning(f"跳过无效历史新闻条目: {e}")
        else:
            # 现有数据已经是按日期分组的格式，先展开成id映射
            existing_dict = {}
            for date in existing_data:
                for item in existing_data[date]:
                    try:
                        item_id = item["id"]
                        existing_dict[item_id] = item
                    except Exception as e:
                        self.logger.warning(f"跳过无效历史新闻条目: {e}")

        updated_count = 0
        new_count = 0
        duplicate_by_title_count = 0

        # 预处理现有标题映射，用于快速相似度比较
        existing_titles = {}
        for item_id, item in existing_dict.items():
            title = item.get("chinese_title", item.get("title", "")).strip()
            if title:
                existing_titles[item_id] = title

        for item in new_items:
            item_dict = item.to_dict()
            item_id = item_dict["id"]
            item_title = item.chinese_title.strip()

            if item_id in existing_dict:
                if update_existing:
                    # 保留原有的所有字段，只更新新数据中存在的字段
                    # 特别保留时间相关字段避免被覆盖
                    existing_item = existing_dict[item_id]
                    for key, value in item_dict.items():
                        # 时间相关字段特殊处理：不覆盖已有的时间
                        if key not in ["published_at", "processed_at", "timestamp"]:
                            existing_item[key] = value
                    existing_dict[item_id] = existing_item
                    updated_count += 1
            else:
                # 检查是否有标题相似的已存在条目（相同新闻事件）
                is_duplicate = False
                if item_title:
                    for existing_id, existing_title in existing_titles.items():
                        if existing_title and is_similar_text(item_title, existing_title, threshold=0.7):
                            # 相似标题，视为同一新闻事件
                            is_duplicate = True
                            duplicate_by_title_count += 1
                            # 更新现有条目的来源链接
                            existing_item = existing_dict[existing_id]
                            if "sourceLinks" in item_dict:
                                new_links = item_dict["sourceLinks"]
                                existing_links = existing_item.get("sourceLinks", [])
                                # 合并来源链接，去重
                                existing_urls = {link["url"] for link in existing_links}
                                for link in new_links:
                                    if link["url"] not in existing_urls:
                                        existing_links.append(link)
                                        existing_urls.add(link["url"])
                                existing_item["sourceLinks"] = existing_links
                                existing_item["sources"] = len(existing_links)
                            break

                if not is_duplicate:
                    existing_dict[item_id] = item_dict
                    existing_titles[item_id] = item_title
                    new_count += 1

        if duplicate_by_title_count > 0:
            self.logger.info(f"标题相似去重: 跳过了{duplicate_by_title_count}条相同新闻事件")

        # 清理超过30天的过期数据
        thirty_days_ago = datetime.now() - timedelta(days=30)
        filtered_dict = {}
        deleted_count = 0
        for item in existing_dict.values():
            try:
                # 解析处理时间，支持多种格式 - 使用处理时间而非原始发布时间判断过期
                # 兼容旧数据：如果没有processed_at字段，使用published_at
                time_field = item.get("processed_at", item.get("published_at"))
                if isinstance(time_field, str):
                    process_time = datetime.fromisoformat(time_field.replace('Z', '+00:00'))
                    # 转换为本地时区的naive datetime进行比较
                    process_time = process_time.astimezone().replace(tzinfo=None)
                else:
                    process_time = datetime.fromtimestamp(time_field)
                if process_time >= thirty_days_ago:
                    filtered_dict[item["id"]] = item
                else:
                    deleted_count += 1
            except Exception as e:
                # 时间解析失败的话保留数据
                filtered_dict[item["id"]] = item
                self.logger.warning(f"新闻时间解析失败，保留该条目: {e}")

        if deleted_count > 0:
            self.logger.info(f"清理过期新闻: 删除了{deleted_count}条超过30天的旧新闻")

        # 按日期分组
        news_by_date = {}
        for item in filtered_dict.values():
            try:
                # 提取日期key - 使用处理时间而非原始发布时间
                # 兼容旧数据：如果没有processed_at字段，使用published_at
                time_field = item.get("processed_at", item.get("published_at"))
                date_key = time_field.split('T')[0] if isinstance(time_field, str) else \
                           datetime.fromtimestamp(time_field).strftime('%Y-%m-%d')

                # 检查是否是已经处理好的前端格式数据（有timestamp和title字段）
                if "timestamp" in item and "title" in item:
                    # 已经是前端格式，直接使用
                    front_item = item
                else:
                    # 转换为前端格式 - 直接使用模型层的标准方法
                    news_item = ProcessedNewsItem.from_dict(item)
                    front_item = news_item.to_frontend_dict()

                if date_key not in news_by_date:
                    news_by_date[date_key] = []
                news_by_date[date_key].append(front_item)

            except Exception as e:
                self.logger.warning(f"新闻处理失败，跳过该条目: {e}")
                continue

        # 每个日期内的新闻按发布时间降序排序
        for date in news_by_date:
            news_by_date[date].sort(key=lambda x: x["timestamp"], reverse=True)

        # 保存前先备份现有数据
        if os.path.exists(self.data_file):
            backup_file = f"{self.data_file}.bak.{datetime.now().strftime('%Y%m%d%H%M%S')}"
            try:
                import shutil
                shutil.copy(self.data_file, backup_file)
                self.logger.info(f"已备份原有数据到: {backup_file}")
            except Exception as e:
                self.logger.warning(f"数据备份失败: {e}")

        # 保存合并后的数据（按日期分组格式）
        save_json(news_by_date, self.data_file)

        return updated_count, new_count

    def _push_to_github(self, commit_message: str) -> bool:
        """
        提交并推送到GitHub
        :param commit_message: 提交信息
        :return: 是否成功
        """
        try:
            # 切换到目标分支
            subprocess.run(
                ["git", "checkout", GITHUB_BRANCH],
                cwd=self.repo_dir,
                capture_output=True,
                text=True,
                check=True
            )

            # 添加变更
            subprocess.run(
                ["git", "add", self.data_file, self.index_html_file],
                cwd=self.repo_dir,
                capture_output=True,
                text=True,
                check=True
            )

            # 检查是否有变更
            status_result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=self.repo_dir,
                capture_output=True,
                text=True
            )

            if not status_result.stdout.strip():
                self.logger.info("没有变更需要提交")
                return True

            # 提交
            subprocess.run(
                ["git", "commit", "-m", commit_message],
                cwd=self.repo_dir,
                capture_output=True,
                text=True,
                check=True
            )

            # 推送：如果配置了GITHUB_TOKEN，则使用token进行推送
            push_cmd = ["git", "push"]
            if settings.GITHUB_TOKEN:
                # 获取当前remote URL
                remote_result = subprocess.run(
                    ["git", "remote", "get-url", "origin"],
                    cwd=self.repo_dir,
                    capture_output=True,
                    text=True
                )
                if remote_result.returncode == 0:
                    remote_url = remote_result.stdout.strip()
                    # 转换为带token的https URL
                    if remote_url.startswith("https://"):
                        # 已有的https URL，注入token
                        if "@" in remote_url:
                            # 已经有token的情况，替换
                            remote_url = f"https://{settings.GITHUB_TOKEN}@" + remote_url.split("@", 1)[1]
                        else:
                            remote_url = f"https://{settings.GITHUB_TOKEN}@" + remote_url[8:]
                    elif remote_url.startswith("git@"):
                        # ssh URL转换为https URL
                        repo_path = remote_url.split(":", 1)[1].replace(".git", "")
                        remote_url = f"https://{settings.GITHUB_TOKEN}@github.com/{repo_path}.git"
                    push_cmd = ["git", "push", remote_url, GITHUB_BRANCH]
                else:
                    push_cmd = ["git", "push", "origin", GITHUB_BRANCH]
            else:
                push_cmd = ["git", "push", "origin", GITHUB_BRANCH]

            push_result = subprocess.run(
                push_cmd,
                cwd=self.repo_dir,
                capture_output=True,
                text=True
            )

            if push_result.returncode != 0:
                self.logger.error(f"Git推送失败: {push_result.stderr}")
                return False

            self.logger.info("Git推送成功")
            return True

        except subprocess.CalledProcessError as e:
            self.logger.error(f"Git操作失败: {e.stderr}")
            return False
        except Exception as e:
            self.logger.error(f"Git操作异常: {e}")
            return False

    def test_connection(self) -> bool:
        """测试GitHub连接"""
        try:
            result = subprocess.run(
                ["git", "remote", "-v"],
                cwd=self.repo_dir,
                capture_output=True,
                text=True
            )
            return result.returncode == 0 and "origin" in result.stdout
        except Exception as e:
            self.logger.error(f"GitHub连接测试失败: {e}")
            return False

    def get_publish_stats(self) -> Dict[str, Any]:
        """获取发布统计信息"""
        existing_data = load_json(self.data_file, {})
        total_news = 0
        latest_timestamp = 0
        latest_update = None

        if isinstance(existing_data, list):
            total_news = len(existing_data)
            if existing_data:
                latest_update = existing_data[0].get("processed_at")
        else:
            for date in existing_data:
                total_news += len(existing_data[date])
                for item in existing_data[date]:
                    if item.get("timestamp", 0) > latest_timestamp:
                        latest_timestamp = item["timestamp"]
                        latest_update = item.get("processed_at")

        return {
            "total_news": total_news,
            "latest_update": latest_update
        }
