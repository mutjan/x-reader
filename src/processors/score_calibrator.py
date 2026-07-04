#!/usr/bin/env python3
"""
评分校准器
基于历史数据分布分析自动生成校准规则，定期批量校准新闻评分
"""
import os
from typing import List, Dict, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from src.models.news import ProcessedNewsItem
from src.utils.common import setup_logger, save_json, load_json
from src.config.settings import BASE_DIR

logger = setup_logger("score_calibrator")

# 配置
CALIBRATION_RULES_FILE = os.path.join(BASE_DIR, "data", "feedback", "calibration_rules.json")
CALIBRATION_REPORT_DIR = os.path.join(BASE_DIR, "data", "feedback", "reports")
SCORING_CONFIG_FILE = os.path.join(BASE_DIR, "prompts", "scoring_config.json")
NEWS_DATA_FILE = os.path.join(BASE_DIR, "data", "news_data.json")
RULE_EXPIRY_DAYS = 30
MIN_SAMPLE_COUNT = 15  # 生成规则最少需要的样本数量
MIN_CONFIDENCE = 0.8   # 规则最低置信度

@dataclass
class CalibrationRule:
    """校准规则数据类"""
    rule_id: str
    rule_type: str  # entity/grade_shift/keyword/source
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
    """校准规则生成器 — 基于历史数据分布分析"""

    def __init__(self, news_data_file: str = None, config_file: str = None):
        self.news_data_file = news_data_file or NEWS_DATA_FILE
        self.config_file = config_file or SCORING_CONFIG_FILE
        self.thresholds = self._load_thresholds()

    def _load_thresholds(self) -> Dict[str, int]:
        """从 scoring_config.json 读取等级阈值"""
        config = load_json(self.config_file, {})
        return config.get("grade_thresholds", {"S": 90, "A+": 85, "A": 75, "B": 65, "C": 0})

    def _load_historical_items(self) -> List[Dict[str, Any]]:
        """从 news_data.json 加载所有历史评分数据"""
        data = load_json(self.news_data_file, {})
        all_items = []
        for date_str, items in data.get("news", {}).items():
            for item in items:
                if "score" in item:
                    item["_date"] = date_str
                    all_items.append(item)
        return all_items

    def _score_to_grade(self, score: float) -> str:
        """根据阈值将分数映射到等级"""
        if score >= self.thresholds.get("S", 90):
            return "S"
        elif score >= self.thresholds.get("A+", 85):
            return "A+"
        elif score >= self.thresholds.get("A", 75):
            return "A"
        elif score >= self.thresholds.get("B", 65):
            return "B"
        else:
            return "C"

    @staticmethod
    def _percentile(sorted_values: List[float], p: float) -> float:
        """计算分位数"""
        if not sorted_values:
            return 0
        n = len(sorted_values)
        k = (n - 1) * p
        f = int(k)
        c = f + 1
        if c >= n:
            return sorted_values[f]
        return sorted_values[f] + (k - f) * (sorted_values[c] - sorted_values[f])

    def generate_rules(self, days: int = None) -> List[CalibrationRule]:
        """
        基于历史数据分布分析生成校准规则
        :param days: 未使用，保留接口兼容
        :return: 校准规则列表
        """
        items = self._load_historical_items()
        if len(items) < MIN_SAMPLE_COUNT:
            logger.info(f"历史数据不足 ({len(items)} < {MIN_SAMPLE_COUNT})，无法生成校准规则")
            return []

        logger.info(f"分析 {len(items)} 条历史评分数据，生成校准规则")

        rules = []

        # 1. grade_shift 规则：每个等级分区的分数分布偏移
        grade_groups: Dict[str, List[float]] = {}
        for item in items:
            grade = item.get("rating") or self._score_to_grade(item["score"])
            if grade not in grade_groups:
                grade_groups[grade] = []
            grade_groups[grade].append(float(item["score"]))

        for grade, scores in grade_groups.items():
            if len(scores) < MIN_SAMPLE_COUNT:
                logger.debug(f"等级 {grade} 样本不足 ({len(scores)} < {MIN_SAMPLE_COUNT})，跳过")
                continue

            sorted_scores = sorted(scores)
            p25 = self._percentile(sorted_scores, 0.25)
            p50 = self._percentile(sorted_scores, 0.50)  # median
            p75 = self._percentile(sorted_scores, 0.75)

            # 偏移 = 该等级的中位数 - 该等级的阈值
            threshold = self.thresholds.get(grade, 0)
            offset = p50 - threshold

            if abs(offset) < 1:
                logger.debug(f"等级 {grade} 偏移过小 ({offset:.1f})，跳过")
                continue

            # 置信度 = 偏移方向一致的样本比例
            if offset > 0:
                direction_count = sum(1 for s in scores if s > threshold)
            else:
                direction_count = sum(1 for s in scores if s <= threshold)
            confidence = direction_count / len(scores)

            if confidence < MIN_CONFIDENCE:
                logger.debug(f"等级 {grade} 置信度不足 ({confidence:.2f} < {MIN_CONFIDENCE})，跳过")
                continue

            adjustment = int(round(offset))
            adjustment = max(min(adjustment, 10), -10)

            if adjustment == 0:
                continue

            rule = CalibrationRule(
                rule_id=f"grade_shift_{grade}_{int(datetime.now().timestamp())}",
                rule_type="grade_shift",
                value=grade,
                score_adjustment=adjustment,
                confidence=confidence,
                sample_count=len(scores)
            )
            rules.append(rule)
            logger.info(f"生成等级偏移规则: {grade} → 调整{adjustment:+d}分 (P50={p50:.1f}, 阈值={threshold}, 置信度{confidence:.2f}, 样本{len(scores)})")

        # 2. entity 规则：特定实体的评分偏差
        overall_mean = sum(float(item["score"]) for item in items) / len(items)
        entity_scores: Dict[str, List[float]] = {}
        for item in items:
            for entity in item.get("entities", []):
                if entity not in entity_scores:
                    entity_scores[entity] = []
                entity_scores[entity].append(float(item["score"]))

        for entity, scores in entity_scores.items():
            if len(scores) < MIN_SAMPLE_COUNT:
                continue

            entity_mean = sum(scores) / len(scores)
            bias = entity_mean - overall_mean

            if abs(bias) < 3:
                continue

            # 置信度 = 偏差方向一致的样本比例
            if bias > 0:
                direction_count = sum(1 for s in scores if s > overall_mean)
            else:
                direction_count = sum(1 for s in scores if s <= overall_mean)
            confidence = direction_count / len(scores)

            if confidence < MIN_CONFIDENCE:
                continue

            adjustment = int(round(bias))
            adjustment = max(min(adjustment, 10), -10)

            if adjustment == 0:
                continue

            rule = CalibrationRule(
                rule_id=f"entity_{entity.replace(' ', '_')}_{int(datetime.now().timestamp())}",
                rule_type="entity",
                value=entity,
                score_adjustment=adjustment,
                confidence=confidence,
                sample_count=len(scores)
            )
            rules.append(rule)
            logger.info(f"生成实体规则: {entity} → 调整{adjustment:+d}分, 置信度{confidence:.2f}, 样本{len(scores)}")

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
        self.thresholds = self._load_thresholds()

    def _load_thresholds(self) -> Dict[str, int]:
        """从 scoring_config.json 读取等级阈值"""
        config = load_json(SCORING_CONFIG_FILE, {})
        return config.get("grade_thresholds", {"S": 90, "A+": 85, "A": 75, "B": 65, "C": 0})

    def _score_to_grade(self, score: float) -> str:
        """根据配置的阈值将分数映射到等级"""
        if score >= self.thresholds.get("S", 90):
            return "S"
        elif score >= self.thresholds.get("A+", 85):
            return "A+"
        elif score >= self.thresholds.get("A", 75):
            return "A"
        elif score >= self.thresholds.get("B", 65):
            return "B"
        else:
            return "C"

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
            if rule.rule_type == "grade_shift":
                # 等级偏移规则：匹配该新闻的当前等级
                current_grade = self._score_to_grade(original_score)
                if rule.value == current_grade:
                    total_adjustment += rule.score_adjustment
                    logger.debug(f"应用规则[{rule.rule_id}]: grade_shift {rule.value} {rule.score_adjustment:+d}分")
            elif rule.rule_type == "entity":
                # 实体规则匹配
                if rule.value in news_item.entities:
                    total_adjustment += rule.score_adjustment
                    logger.debug(f"应用规则[{rule.rule_id}]: entity {rule.value} {rule.score_adjustment:+d}分")

        # 应用调整，分数限制在0-100之间
        new_score = max(min(original_score + total_adjustment, 100), 0)

        if new_score != original_score:
            # 使用配置阈值重新计算分级
            new_grade = self._score_to_grade(new_score)

            news_item.score = new_score
            news_item.grade = new_grade
            logger.debug(f"新闻{news_item.id}校准完成: {original_score} → {new_score} ({new_grade})")

        return news_item

    def apply_calibration_raw(self, score: float, entities: List[str], title: str = "") -> float:
        """
        对原始分数应用校准规则（在 ProcessedNewsItem 创建之前使用）
        用于 parse_scoring_response() 流水线中

        Args:
            score: 当前 ai_score（zeitgeist boost 之后）
            entities: 新闻实列表
            title: 新闻标题（保留参数，用于关键词匹配扩展）
        Returns:
            调整后的分数（限制在 0-100）
        """
        if not self.rules:
            return score

        total_adjustment = 0
        current_grade = self._score_to_grade(score)

        for rule in self.rules:
            if rule.rule_type == "grade_shift":
                if rule.value == current_grade:
                    total_adjustment += rule.score_adjustment
                    logger.debug(f"校准规则[{rule.rule_id}]: grade_shift {rule.value} {rule.score_adjustment:+d}分")
            elif rule.rule_type == "entity":
                if rule.value in entities:
                    total_adjustment += rule.score_adjustment
                    logger.debug(f"校准规则[{rule.rule_id}]: entity {rule.value} {rule.score_adjustment:+d}分")

        new_score = max(min(score + total_adjustment, 100), 0)

        if new_score != score:
            logger.info(f"校准调整: {score:.1f} -> {new_score:.1f} (调整量: {total_adjustment:+d})")

        return new_score

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
