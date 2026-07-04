#!/usr/bin/env python3
"""
反馈数据存储层
负责人工评分反馈数据的持久化和管理
"""
import os
import json
import shutil
from datetime import datetime
from typing import List, Dict, Any, Optional
from src.utils.common import setup_logger, load_json, save_json
from src.config.settings import BASE_DIR

logger = setup_logger("feedback_store")

# 存储路径配置
FEEDBACK_DIR = os.path.join(BASE_DIR, "data", "feedback")
FEEDBACK_FILE = os.path.join(FEEDBACK_DIR, "feedback_records.json")
BACKUP_DIR = os.path.join(FEEDBACK_DIR, "backups")
BACKUP_RETENTION_DAYS = 30

class FeedbackStore:
    """反馈数据存储类"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self):
        """初始化存储目录和文件"""
        # 创建目录
        os.makedirs(FEEDBACK_DIR, exist_ok=True)
        os.makedirs(BACKUP_DIR, exist_ok=True)

        # 初始化反馈文件
        if not os.path.exists(FEEDBACK_FILE):
            self._save_data({"records": []})

        # 清理旧备份
        self._cleanup_old_backups()

    def _load_data(self) -> Dict[str, Any]:
        """加载反馈数据"""
        return load_json(FEEDBACK_FILE, {"records": []})

    def _save_data(self, data: Dict[str, Any]):
        """保存反馈数据，自动备份"""
        # 先备份现有文件
        if os.path.exists(FEEDBACK_FILE):
            backup_filename = f"feedback_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            backup_path = os.path.join(BACKUP_DIR, backup_filename)
            shutil.copy2(FEEDBACK_FILE, backup_path)
            logger.debug(f"已备份反馈数据到: {backup_path}")

        # 保存新数据
        save_json(data, FEEDBACK_FILE)

    def _cleanup_old_backups(self):
        """清理超过保留期限的备份"""
        try:
            cutoff_time = datetime.now().timestamp() - BACKUP_RETENTION_DAYS * 24 * 3600
            for filename in os.listdir(BACKUP_DIR):
                if filename.startswith("feedback_") and filename.endswith(".json"):
                    file_path = os.path.join(BACKUP_DIR, filename)
                    if os.path.getmtime(file_path) < cutoff_time:
                        os.unlink(file_path)
                        logger.debug(f"删除旧备份: {file_path}")
        except Exception as e:
            logger.warning(f"清理旧备份失败: {e}")

    def add_feedback(self, news_id: str, original_grade: str, original_score: int,
                     corrected_grade: str, corrected_score: int, reason: str = "",
                     entities: List[str] = None) -> bool:
        """
        添加一条反馈记录
        :param news_id: 新闻ID
        :param original_grade: 原始AI分级
        :param original_score: 原始AI评分
        :param corrected_grade: 修正后的分级
        :param corrected_score: 修正后的评分
        :param reason: 修正原因
        :param entities: 新闻相关实体
        :return: 是否添加成功
        """
        try:
            data = self._load_data()
            records = data.get("records", [])

            # 检查是否已有该新闻的反馈，有则更新
            existing_index = None
            for i, record in enumerate(records):
                if record.get("news_id") == news_id:
                    existing_index = i
                    break

            feedback_record = {
                "news_id": news_id,
                "original_grade": original_grade,
                "original_score": original_score,
                "corrected_grade": corrected_grade,
                "corrected_score": corrected_score,
                "reason": reason,
                "entities": entities or [],
                "timestamp": datetime.now().isoformat()
            }

            if existing_index is not None:
                # 更新现有记录
                records[existing_index] = feedback_record
                logger.info(f"更新反馈记录: news_id={news_id}")
            else:
                # 添加新记录
                records.append(feedback_record)
                logger.info(f"添加反馈记录: news_id={news_id}")

            data["records"] = records
            self._save_data(data)
            return True

        except Exception as e:
            logger.error(f"添加反馈失败: {e}")
            return False

    def get_feedback_by_news_id(self, news_id: str) -> Optional[Dict[str, Any]]:
        """根据新闻ID查询反馈记录"""
        try:
            data = self._load_data()
            records = data.get("records", [])
            for record in records:
                if record.get("news_id") == news_id:
                    return record
            return None
        except Exception as e:
            logger.error(f"查询反馈失败: {e}")
            return None

    def get_all_feedback(self, days: int = None) -> List[Dict[str, Any]]:
        """
        获取所有反馈记录
        :param days: 只获取最近N天的反馈，None表示全部
        :return: 反馈记录列表
        """
        try:
            data = self._load_data()
            records = data.get("records", [])

            if days is not None:
                cutoff_time = datetime.now().timestamp() - days * 24 * 3600
                filtered = []
                for record in records:
                    try:
                        record_time = datetime.fromisoformat(record.get("timestamp", "")).timestamp()
                        if record_time >= cutoff_time:
                            filtered.append(record)
                    except:
                        continue
                return filtered

            return records
        except Exception as e:
            logger.error(f"获取反馈失败: {e}")
            return []

    def get_feedback_by_entity(self, entity: str, days: int = None) -> List[Dict[str, Any]]:
        """根据实体查询相关反馈记录"""
        records = self.get_all_feedback(days)
        return [r for r in records if entity in r.get("entities", [])]

    def delete_feedback(self, news_id: str) -> bool:
        """删除指定新闻的反馈记录"""
        try:
            data = self._load_data()
            records = data.get("records", [])
            new_records = [r for r in records if r.get("news_id") != news_id]

            if len(new_records) == len(records):
                logger.warning(f"反馈记录不存在: news_id={news_id}")
                return False

            data["records"] = new_records
            self._save_data(data)
            logger.info(f"删除反馈记录: news_id={news_id}")
            return True

        except Exception as e:
            logger.error(f"删除反馈失败: {e}")
            return False
