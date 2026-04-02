#!/usr/bin/env python3
"""
事件分组处理器
自动将同事件的新闻归为一组
"""
from typing import List, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime
import uuid
import os
import shutil
import glob
from datetime import timedelta
from src.models.news import ProcessedNewsItem
from src.utils.similarity import calculate_news_similarity
from src.utils.common import setup_logger, save_json, load_json
from src.config.settings import DATA_DIR, EVENT_GROUPS_FILE

logger = setup_logger("event_grouper")

@dataclass
class Event:
    """事件数据类"""
    event_id: str
    title: str  # 事件主标题（取最高评分新闻的标题）
    main_news: ProcessedNewsItem  # 主新闻（最高评分/最新）
    news_list: List[ProcessedNewsItem] = field(default_factory=list)
    entities: List[str] = field(default_factory=list)
    max_grade: str = "B"
    max_score: int = 0
    start_time: datetime = field(default_factory=datetime.now)
    end_time: datetime = field(default_factory=datetime.now)
    news_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "event_id": self.event_id,
            "title": self.title,
            "max_grade": self.max_grade,
            "max_score": self.max_score,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "news_count": self.news_count,
            "entities": self.entities,
            "news_list": [item.to_frontend_dict() for item in self.news_list]
        }

class EventGrouper:
    """事件分组处理器"""

    def __init__(self, entity_threshold: int = 3, similarity_threshold: float = 0.85):
        self.entity_threshold = entity_threshold
        self.similarity_threshold = similarity_threshold
        self.grade_order = {"S": 5, "A+": 4, "A": 3, "B": 2, "C": 1}

    def group_news(self, news_items: List[ProcessedNewsItem]) -> List[Event]:
        """
        将新闻列表分组为事件
        :param news_items: 处理后的新闻列表
        :return: 事件列表
        """
        if not news_items:
            return []

        # 按发布时间升序排序，先处理早的新闻
        sorted_news = sorted(news_items, key=lambda x: x.published_at)
        events: List[Event] = []

        for news in sorted_news:
            matched_event = None
            max_similarity = 0.0

            # 查找最匹配的事件
            for event in events:
                # 和事件中的每条新闻比较，取最高相似度
                event_max_sim = 0.0
                for event_news in event.news_list:
                    sim = calculate_news_similarity(
                        news, event_news,
                        entity_threshold=self.entity_threshold,
                        similarity_threshold=self.similarity_threshold
                    )
                    if sim > event_max_sim:
                        event_max_sim = sim

                if event_max_sim > max_similarity and event_max_sim >= self.similarity_threshold:
                    max_similarity = event_max_sim
                    matched_event = event

            if matched_event:
                # 添加到已有事件
                matched_event.news_list.append(news)
                # 更新事件属性
                self._update_event_properties(matched_event)
            else:
                # 创建新事件
                new_event = self._create_new_event(news)
                events.append(new_event)

        # 按事件重要性排序（最高评分降序，新闻数量降序）
        events.sort(key=lambda e: (self.grade_order[e.max_grade], e.max_score, e.news_count), reverse=True)

        # 给每条新闻添加event_id标记
        for event in events:
            for news in event.news_list:
                news.event_id = event.event_id

        logger.info(f"事件分组完成: {len(news_items)}条新闻 → {len(events)}个事件")
        return events

    def _create_new_event(self, news: ProcessedNewsItem) -> Event:
        """创建新事件"""
        event_id = str(uuid.uuid4())[:8]  # 8位UUID作为事件ID
        return Event(
            event_id=event_id,
            title=news.chinese_title,
            main_news=news,
            news_list=[news],
            entities=news.entities.copy(),
            max_grade=news.grade,
            max_score=news.score,
            start_time=news.published_at,
            end_time=news.published_at,
            news_count=1
        )

    def _update_event_properties(self, event: Event):
        """更新事件属性"""
        # 更新新闻数量
        event.news_count = len(event.news_list)

        # 更新时间范围
        publish_times = [n.published_at for n in event.news_list]
        event.start_time = min(publish_times)
        event.end_time = max(publish_times)

        # 找到最高评分的新闻作为主新闻
        event.news_list.sort(key=lambda x: (self.grade_order[x.grade], x.score), reverse=True)
        main_news = event.news_list[0]
        event.title = main_news.chinese_title
        event.main_news = main_news
        event.max_grade = main_news.grade
        event.max_score = main_news.score

        # 更新实体集合（合并所有新闻的实体，去重）
        all_entities = set()
        for n in event.news_list:
            all_entities.update(n.entities)
        event.entities = sorted(list(all_entities))

    def _events_to_dict(self, events: List[Event]) -> List[Dict[str, Any]]:
        """转换事件列表为存储格式（仅包含news_ids，不存储完整新闻）"""
        result = []
        for event in events:
            result.append({
                "group_id": event.event_id,
                "event_title": event.title,
                "first_seen_at": event.start_time.isoformat(),
                "last_seen_at": event.end_time.isoformat(),
                "news_ids": [news.id for news in event.news_list],
                "max_score": event.max_score,
                "max_grade": event.max_grade,
                "entities": event.entities
            })
        return result

    def _create_backup(self, file_path: str) -> bool:
        """创建每日备份，保留最近7天"""
        if not os.path.exists(file_path):
            return True

        date_str = datetime.now().strftime("%Y-%m-%d")
        backup_path = f"{file_path}-{date_str}.bak"

        # 当天已有备份则不重复创建
        if os.path.exists(backup_path):
            return True

        try:
            # 复制当前文件到备份
            shutil.copy2(file_path, backup_path)
            # 清理超过7天的备份
            self._cleanup_old_backups(os.path.dirname(file_path))
            logger.info(f"备份创建成功: {backup_path}")
            return True
        except IOError as e:
            logger.error(f"创建备份失败: {e}")
            return False

    def _cleanup_old_backups(self, dir_path: str, days: int = 7) -> None:
        """清理超过指定天数的备份文件"""
        cutoff_date = datetime.now() - timedelta(days=days)
        backup_pattern = os.path.join(dir_path, "*.bak")

        for backup_file in glob.glob(backup_pattern):
            try:
                # 从文件名提取日期: 格式为 filename-YYYY-MM-DD.bak
                # 日期格式是固定的 10 个字符 (YYYY-MM-DD)，所以直接取最后 10 个字符
                file_name = os.path.basename(backup_file)
                # 移除 .bak 后缀后，取末尾 10 个字符就是日期
                name_without_ext = file_name[:-4]
                if len(name_without_ext) >= 10:
                    date_str = name_without_ext[-10:]
                    backup_date = datetime.strptime(date_str, "%Y-%m-%d")
                    if backup_date < cutoff_date:
                        os.remove(backup_file)
                        logger.info(f"清理过期备份: {backup_file}")
            except (ValueError, IOError) as e:
                logger.warning(f"处理备份文件失败 {backup_file}: {e}")

    def save_event_groups(self, events: List[Event], output_path: str = None) -> bool:
        """保存事件分组到文件"""
        if output_path is None:
            output_path = EVENT_GROUPS_FILE

        # 创建备份
        if os.path.exists(output_path):
            self._create_backup(output_path)

        # 转换为存储格式
        data = self._events_to_dict(events)

        # 保存文件
        return save_json(data, output_path)

    def load_event_groups(self, input_path: str = None) -> List[Dict[str, Any]]:
        """加载事件分组文件"""
        if input_path is None:
            input_path = EVENT_GROUPS_FILE

        return load_json(input_path, [])

    def incremental_group(self, existing_groups: List[Dict], new_items: List[ProcessedNewsItem]) -> List[Event]:
        """
        增量分组：将新条目添加到现有分组中，或创建新分组
        :param existing_groups: 现有分组列表（从文件加载的字典格式）
        :param new_items: 新的新闻条目列表
        :return: 更新后的事件列表
        """
        if not existing_groups and not new_items:
            return []

        # 将现有分组转换为Event对象
        existing_events = []

        # 首先收集所有现有新闻和新新闻，用于重建完整的事件对象
        all_news_items = {}
        # 添加新条目到字典
        for item in new_items:
            all_news_items[item.id] = item

        for group_dict in existing_groups:
            try:
                # 从存储格式重建事件基本信息
                event_id = group_dict.get("group_id", group_dict.get("event_id", str(uuid.uuid4())[:8]))
                title = group_dict.get("event_title", group_dict.get("title", "未命名事件"))
                max_grade = group_dict.get("max_grade", "B")
                max_score = group_dict.get("max_score", 0)
                entities = group_dict.get("entities", [])

                # 解析时间
                start_time = datetime.fromisoformat(group_dict["first_seen_at"]) if "first_seen_at" in group_dict else datetime.now()
                end_time = datetime.fromisoformat(group_dict["last_seen_at"]) if "last_seen_at" in group_dict else datetime.now()

                # 重建该事件的新闻列表：从现有新闻中查找匹配的ID
                news_list = []
                for news_id in group_dict.get("news_ids", []):
                    if news_id in all_news_items:
                        news_list.append(all_news_items[news_id])

                # 只有当新闻列表非空时才保留这个事件
                if news_list:
                    # 创建事件对象
                    event = Event(
                        event_id=event_id,
                        title=title,
                        main_news=news_list[0],  # 临时设置，后面会更新
                        news_list=news_list,
                        entities=entities,
                        max_grade=max_grade,
                        max_score=max_score,
                        start_time=start_time,
                        end_time=end_time,
                        news_count=len(news_list)
                    )
                    # 更新事件属性
                    self._update_event_properties(event)
                    existing_events.append(event)

            except Exception as e:
                logger.warning(f"跳过无效的现有分组: {e}")
                continue

        # 将新条目添加到现有事件或创建新事件
        events = existing_events.copy()

        for news in new_items:
            matched_event = None
            max_similarity = 0.0

            # 查找最匹配的现有事件
            for event in events:
                # 和事件中的每条新闻比较，取最高相似度
                event_max_sim = 0.0
                for event_news in event.news_list:
                    sim = calculate_news_similarity(
                        news, event_news,
                        entity_threshold=self.entity_threshold,
                        similarity_threshold=self.similarity_threshold
                    )
                    if sim > event_max_sim:
                        event_max_sim = sim

                if event_max_sim > max_similarity and event_max_sim >= self.similarity_threshold:
                    max_similarity = event_max_sim
                    matched_event = event

            if matched_event:
                # 添加到已有事件
                matched_event.news_list.append(news)
                # 更新事件属性
                self._update_event_properties(matched_event)
            else:
                # 创建新事件
                new_event = self._create_new_event(news)
                events.append(new_event)

        # 按事件重要性排序
        events.sort(key=lambda e: (self.grade_order[e.max_grade], e.max_score, e.news_count), reverse=True)

        # 给每条新闻添加event_id标记
        for event in events:
            for news in event.news_list:
                news.event_id = event.event_id

        logger.info(f"增量分组完成: {len(new_items)}条新新闻 → 更新后共{len(events)}个事件")
        return events
