#!/usr/bin/env python3
"""
RSS源存储管理模块
"""
import os
import json
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional
from src.utils.common import setup_logger, save_json, load_json
from src.config.settings import BASE_DIR, RSS_CONFIG

logger = setup_logger("source_store")

# 配置
SOURCES_FILE = os.path.join(BASE_DIR, "data", "sources", "sources.json")
BACKUP_DIR = os.path.join(BASE_DIR, "data", "sources", "backups")
MAX_BACKUP_COUNT = 30  # 保留最多30天备份

class SourceStore:
    """RSS源存储管理类"""

    def __init__(self):
        os.makedirs(os.path.dirname(SOURCES_FILE), exist_ok=True)
        os.makedirs(BACKUP_DIR, exist_ok=True)
        # 首次运行初始化默认源
        if not os.path.exists(SOURCES_FILE):
            self._init_default_sources()

    def _init_default_sources(self):
        """初始化默认源配置"""
        logger.info("初始化默认源配置")
        default_sources = []
        for source_id, config in RSS_CONFIG.items():
            # 处理没有url字段的源类型（如inoreader）
            url = config.get("url", "")
            if not url and source_id == "inoreader":
                url = config.get("api", "https://www.inoreader.com/reader/api/0")

            source = {
                "id": source_id,
                "name": config.get("name", source_id),
                "url": url,
                "type": config.get("type", "rss"),
                "enabled": True,
                "weight": 1.0,
                "config": {k: v for k, v in config.items() if k not in ["name", "url", "type"]},
                "last_fetched": None,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }
            default_sources.append(source)

        data = {
            "version": "1.0",
            "updated_at": datetime.now().isoformat(),
            "sources": default_sources
        }
        save_json(data, SOURCES_FILE)
        self._backup()

    def _backup(self):
        """自动备份源配置"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_file = os.path.join(BACKUP_DIR, f"sources_{timestamp}.json")
            with open(SOURCES_FILE, 'r', encoding='utf-8') as f:
                content = f.read()
            with open(backup_file, 'w', encoding='utf-8') as f:
                f.write(content)

            # 清理旧备份
            backups = sorted([f for f in os.listdir(BACKUP_DIR) if f.startswith("sources_") and f.endswith(".json")])
            if len(backups) > MAX_BACKUP_COUNT:
                for old_backup in backups[:-MAX_BACKUP_COUNT]:
                    os.remove(os.path.join(BACKUP_DIR, old_backup))

            logger.debug(f"源配置已备份到: {backup_file}")
        except Exception as e:
            logger.error(f"备份源配置失败: {e}")

    def get_all_sources(self, include_disabled: bool = False) -> List[Dict[str, Any]]:
        """获取所有源"""
        try:
            data = load_json(SOURCES_FILE, {})
            sources = data.get("sources", [])
            if not include_disabled:
                sources = [s for s in sources if s.get("enabled", True)]
            return sources
        except Exception as e:
            logger.error(f"获取源列表失败: {e}")
            return []

    def get_source(self, source_id: str) -> Optional[Dict[str, Any]]:
        """根据ID获取源"""
        sources = self.get_all_sources(include_disabled=True)
        return next((s for s in sources if s["id"] == source_id), None)

    def add_source(self, name: str, url: str, source_type: str, enabled: bool = True, weight: float = 1.0, config: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """添加新源"""
        try:
            data = load_json(SOURCES_FILE, {})
            sources = data.get("sources", [])

            # 生成唯一ID
            source_id = str(uuid.uuid4()).replace("-", "")[:12]

            new_source = {
                "id": source_id,
                "name": name,
                "url": url,
                "type": source_type,
                "enabled": enabled,
                "weight": weight,
                "config": config or {},
                "last_fetched": None,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }

            sources.append(new_source)
            data["sources"] = sources
            data["updated_at"] = datetime.now().isoformat()

            save_json(data, SOURCES_FILE)
            self._backup()

            logger.info(f"添加源成功: {name} (ID: {source_id})")
            return new_source
        except Exception as e:
            logger.error(f"添加源失败: {e}")
            return None

    def update_source(self, source_id: str, **kwargs) -> Optional[Dict[str, Any]]:
        """更新源信息"""
        try:
            data = load_json(SOURCES_FILE, {})
            sources = data.get("sources", [])

            index = next((i for i, s in enumerate(sources) if s["id"] == source_id), None)
            if index is None:
                logger.warning(f"更新源失败，源不存在: {source_id}")
                return None

            # 更新字段
            allowed_fields = ["name", "url", "type", "enabled", "weight", "config", "last_fetched"]
            for key, value in kwargs.items():
                if key in allowed_fields:
                    sources[index][key] = value

            sources[index]["updated_at"] = datetime.now().isoformat()
            data["sources"] = sources
            data["updated_at"] = datetime.now().isoformat()

            save_json(data, SOURCES_FILE)
            self._backup()

            logger.info(f"更新源成功: {source_id}")
            return sources[index]
        except Exception as e:
            logger.error(f"更新源失败: {e}")
            return None

    def delete_source(self, source_id: str) -> bool:
        """删除源"""
        try:
            data = load_json(SOURCES_FILE, {})
            sources = data.get("sources", [])

            index = next((i for i, s in enumerate(sources) if s["id"] == source_id), None)
            if index is None:
                logger.warning(f"删除源失败，源不存在: {source_id}")
                return False

            deleted_source = sources.pop(index)
            data["sources"] = sources
            data["updated_at"] = datetime.now().isoformat()

            save_json(data, SOURCES_FILE)
            self._backup()

            logger.info(f"删除源成功: {deleted_source['name']} (ID: {source_id})")
            return True
        except Exception as e:
            logger.error(f"删除源失败: {e}")
            return False

    def update_last_fetched(self, source_id: str) -> bool:
        """更新源的最后抓取时间"""
        return self.update_source(source_id, last_fetched=datetime.now().isoformat()) is not None

# 全局实例
source_store = SourceStore()
