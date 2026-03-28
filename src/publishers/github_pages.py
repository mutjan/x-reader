#!/usr/bin/env python3
"""
GitHub Pages 发布器
将新闻数据发布到GitHub Pages
"""
from typing import List, Dict, Any
import json
import os
import subprocess
from datetime import datetime

from src.publishers.base import BasePublisher
from src.models.news import ProcessedNewsItem
from src.config.settings import DATA_FILE, GITHUB_BRANCH
from src.utils.common import save_json, load_json

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
        existing_data = load_json(self.data_file, [])
        existing_dict = {item["id"]: item for item in existing_data}

        updated_count = 0
        new_count = 0

        for item in new_items:
            item_dict = item.to_dict()
            item_id = item_dict["id"]

            if item_id in existing_dict:
                if update_existing:
                    # 保留原有的发布时间，更新其他字段
                    item_dict["published_at"] = existing_dict[item_id].get("published_at", item_dict["published_at"])
                    existing_dict[item_id] = item_dict
                    updated_count += 1
            else:
                existing_dict[item_id] = item_dict
                new_count += 1

        # 转换回列表并按发布时间降序排序
        merged_list = sorted(existing_dict.values(), key=lambda x: x["published_at"], reverse=True)

        # 保存合并后的数据
        save_json(merged_list, self.data_file)

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

            # 推送
            push_result = subprocess.run(
                ["git", "push", "origin", GITHUB_BRANCH],
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
        existing_data = load_json(self.data_file, [])
        return {
            "total_news": len(existing_data),
            "latest_update": existing_data[0]["processed_at"] if existing_data else None
        }
