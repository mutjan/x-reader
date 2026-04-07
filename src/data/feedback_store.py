#!/usr/bin/env python3
"""
用户反馈存储模块
用于存储和管理用户对新闻评分的反馈
"""
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import os
import json

from src.utils.common import load_json, save_json
from src.config.settings import settings


class FeedbackStore:
    """用户反馈存储"""

    def __init__(self, feedback_file: str = None):
        """
        初始化反馈存储
        :param feedback_file: 反馈数据文件路径
        """
        if feedback_file is None:
            # 默认存储在项目根目录的 _data 文件夹中
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            feedback_file = os.path.join(base_dir, "_data", "feedback.json")

        self.feedback_file = feedback_file
        self._ensure_file_exists()

    def _ensure_file_exists(self):
        """确保反馈文件存在"""
        os.makedirs(os.path.dirname(self.feedback_file), exist_ok=True)
        if not os.path.exists(self.feedback_file):
            save_json(self.feedback_file, [])

    def add_feedback(self, news_id: str, original_score: float, user_score: float,
                     feedback_type: str = "score_adjustment", comment: str = "") -> bool:
        """
        添加用户反馈
        :param news_id: 新闻ID
        :param original_score: 原始分数
        :param user_score: 用户评分
        :param feedback_type: 反馈类型
        :param comment: 用户评论
        :return: 是否添加成功
        """
        try:
            feedback_list = load_json(self.feedback_file, [])

            feedback_record = {
                "id": f"{news_id}_{int(datetime.now().timestamp())}",
                "news_id": news_id,
                "original_score": original_score,
                "user_score": user_score,
                "feedback_type": feedback_type,
                "comment": comment,
                "created_at": datetime.now().isoformat()
            }

            feedback_list.append(feedback_record)
            save_json(self.feedback_file, feedback_list)
            return True
        except Exception as e:
            print(f"添加反馈失败: {e}")
            return False

    def get_all_feedback(self, days: int = 30) -> List[Dict[str, Any]]:
        """
        获取指定天数内的所有反馈
        :param days: 天数
        :return: 反馈列表
        """
        try:
            feedback_list = load_json(self.feedback_file, [])
            cutoff_date = datetime.now() - timedelta(days=days)

            filtered_feedback = []
            for feedback in feedback_list:
                try:
                    created_at = datetime.fromisoformat(feedback.get("created_at", ""))
                    if created_at >= cutoff_date:
                        filtered_feedback.append(feedback)
                except:
                    continue

            return filtered_feedback
        except Exception as e:
            print(f"获取反馈失败: {e}")
            return []

    def get_feedback_by_news_id(self, news_id: str) -> List[Dict[str, Any]]:
        """
        获取指定新闻的所有反馈
        :param news_id: 新闻ID
        :return: 反馈列表
        """
        try:
            feedback_list = load_json(self.feedback_file, [])
            return [f for f in feedback_list if f.get("news_id") == news_id]
        except Exception as e:
            print(f"获取反馈失败: {e}")
            return []
