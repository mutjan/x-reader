#!/usr/bin/env python3
"""
评分校准器
基于历史反馈数据自动生成校准规则，定期批量校准新闻评分
"""
import os
import json
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from src.models.news import ProcessedNewsItem
from src.data.feedback_store import FeedbackStore
from src.utils.common import setup_logger, save_json, load_json
from src.config.settings import BASE_DIR

logger = setup_logger("score_calibrator")

# 配置
CALIBRATION_RULES_FILE = os.path.join(BASE_DIR, "data", "feedback", "calibration_rules.json")
CALIBRATION_REPORT_DIR = os.path.join(BASE_DIR, "data", "feedback", "reports")
RULE_EXPIRY_DAYS = 30
MIN_SAMPLE_COUNT = 5  # 生成规则最少需要的样本数量
MIN_CONFIDENCE = 0.8   # 规则最低置信度

@dataclass
class CalibrationRule:
    """校准规则数据类"""
    rule_id: str
    rule_type: str  # entity/type/keyword/source
    value: str
    score_adjustment: int  # 分数调整值，可正可负
    confidence: float  # 0-1，置信度
    sample_count: int  # 样本数量
    created_at: datetime = field(default_factory=datetime.now)
    expires_at: datetime = field(default_factory=lambda: datetime.now() + timedelta(days=RULE_EXPIRY_DAYS))

    def is_valid(self) -> bool:
        """检查规则是否有效（未过期，置信度足够）"""
        return (self.confidence >= MIN_CONFIDENCE and
                self.sample_count >= MIN_SAMPLE_COUNT and
                datetime.now() < self.expires_at)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "rule_id": self.rule_id,
            "type": self.rule_type,
            "value": self.value,
            "score_adjustment": self.score_adjustment,
            "confidence": self.confidence,
            "sample_count": self.sample_count,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat()
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CalibrationRule':
        """从字典加载"""
        return cls(
            rule_id=data["rule_id"],
            rule_type=data["type"],
            value=data["value"],
            score_adjustment=data["score_adjustment"],
            confidence=data["confidence"],
            sample_count=data["sample_count"],
            created_at=datetime.fromisoformat(data["created_at"]),
            expires_at=datetime.fromisoformat(data["expires_at"])
        )

class CalibrationRuleGenerator:
    """校准规则生成器"""

    def __init__(self):
        self.feedback_store = FeedbackStore()
        self.grade_score_map = {"S": 95, "A+": 87, "A": 80, "B": 70, "C": 60}

    def generate_rules(self, days: int = 30) -> List[CalibrationRule]:
        """
        基于最近N天的反馈数据生成校准规则
        :param days: 分析最近多少天的反馈
        :return: 校准规则列表
        """
        feedback_records = self.feedback_store.get_all_feedback(days)
        if not feedback_records:
            logger.info("没有反馈数据，无法生成校准规则")
            return []

        logger.info(f"分析 {len(feedback_records)} 条反馈记录，生成校准规则")

        # 按维度分组统计偏差
        entity_deviations = {}  # 实体 -> [偏差列表]
        type_deviations = {}    # 新闻类型 -> [偏差列表]

        for record in feedback_records:
            # 计算偏差：修正分 - 原始分
            original_score = record.get("original_score", 0)
            corrected_score = record.get("corrected_score", 0)
            deviation = corrected_score - original_score

            if deviation == 0:
                continue  # 没有偏差的跳过

            # 按实体统计
            entities = record.get("entities", [])
            for entity in entities:
                if entity not in entity_deviations:
                    entity_deviations[entity] = []
                entity_deviations[entity].append(deviation)

            # 按新闻类型统计
            # TODO: 从反馈记录中获取新闻类型

        rules = []

        # 生成实体规则
        for entity, deviations in entity_deviations.items():
            if len(deviations) < MIN_SAMPLE_COUNT:
                continue

            avg_deviation = sum(deviations) / len(deviations)
            # 置信度 = 偏差方向一致的样本比例
            positive_count = sum(1 for d in deviations if d > 0)
            negative_count = sum(1 for d in deviations if d < 0)
            max_direction_count = max(positive_count, negative_count)
            confidence = max_direction_count / len(deviations)

            if confidence < MIN_CONFIDENCE:
                continue

            # 规则调整值取平均偏差的整数部分，最多±10分
            adjustment = int(round(avg_deviation))
            adjustment = max(min(adjustment, 10), -10)

            if adjustment == 0:
                continue

            rule = CalibrationRule(
                rule_id=f"entity_{entity.replace(' ', '_')}_{int(datetime.now().timestamp())}",
                rule_type="entity",
                value=entity,
                score_adjustment=adjustment,
                confidence=confidence,
                sample_count=len(deviations)
            )
            rules.append(rule)
            logger.info(f"生成实体规则: {entity} → 调整{adjustment:+d}分, 置信度{confidence:.2f}, 样本{len(deviations)}")

        # 保存规则
        self._save_rules(rules)
        return rules

    def _save_rules(self, rules: List[CalibrationRule]):
        """保存规则到文件"""
        os.makedirs(os.path.dirname(CALIBRATION_RULES_FILE), exist_ok=True)
        rules_data = {
            "generated_at": datetime.now().isoformat(),
            "expires_at": (datetime.now() + timedelta(days=RULE_EXPIRY_DAYS)).isoformat(),
            "rules": [rule.to_dict() for rule in rules]
        }
        save_json(rules_data, CALIBRATION_RULES_FILE)
        logger.info(f"校准规则已保存到: {CALIBRATION_RULES_FILE}")

    def load_rules(self) -> List[CalibrationRule]:
        """加载有效规则"""
        if not os.path.exists(CALIBRATION_RULES_FILE):
            return []

        try:
            data = load_json(CALIBRATION_RULES_FILE, {})
            rules_data = data.get("rules", [])
            rules = [CalibrationRule.from_dict(r) for r in rules_data]
            # 只返回有效的规则
            valid_rules = [r for r in rules if r.is_valid()]
            logger.info(f"加载到 {len(valid_rules)} 条有效校准规则")
            return valid_rules
        except Exception as e:
            logger.error(f"加载校准规则失败: {e}")
            return []

class CalibrationEngine:
    """校准执行引擎"""

    def __init__(self):
        self.rule_generator = CalibrationRuleGenerator()
        self.rules = self.rule_generator.load_rules()

    def apply_calibration(self, news_item: ProcessedNewsItem) -> ProcessedNewsItem:
        """
        对单条新闻应用校准规则
        :param news_item: 原始新闻
        :return: 校准后的新闻
        """
        if not self.rules:
            return news_item

        original_score = news_item.score
        total_adjustment = 0

        # 应用所有匹配的规则
        for rule in self.rules:
            if rule.rule_type == "entity":
                # 实体规则匹配
                if rule.value in news_item.entities:
                    total_adjustment += rule.score_adjustment
                    logger.debug(f"应用规则[{rule.rule_id}]: {rule.value} {rule.score_adjustment:+d}分")

        # 应用调整，分数限制在0-100之间
        new_score = max(min(original_score + total_adjustment, 100), 0)

        if new_score != original_score:
            # 重新计算分级
            if new_score >= 90:
                new_grade = "S"
            elif new_score >= 85:
                new_grade = "A+"
            elif new_score >= 75:
                new_grade = "A"
            elif new_score >= 65:
                new_grade = "B"
            else:
                new_grade = "C"

            news_item.score = new_score
            news_item.grade = new_grade
            logger.debug(f"新闻{news_item.id}校准完成: {original_score} → {new_score} ({new_grade})")

        return news_item

    def batch_calibrate(self, news_items: List[ProcessedNewsItem]) -> List[ProcessedNewsItem]:
        """批量校准新闻"""
        if not self.rules:
            logger.info("没有有效校准规则，跳过校准")
            return news_items

        logger.info(f"开始批量校准 {len(news_items)} 条新闻")
        calibrated_items = [self.apply_calibration(item) for item in news_items]

        # 统计校准效果
        adjusted_count = sum(1 for original, calibrated in zip(news_items, calibrated_items)
                           if original.score != calibrated.score)
        logger.info(f"校准完成: {adjusted_count} 条新闻分数被调整")
        return calibrated_items
