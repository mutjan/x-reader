#!/usr/bin/env python3
"""
AI新闻处理模块
将原始新闻转换为标准化的处理结果
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
import json
import os
import subprocess
import tempfile
from datetime import datetime

from src.models.news import RawNewsItem, ProcessedNewsItem, EntityNormalizer
from src.utils.common import setup_logger, truncate_text, save_json, load_json, sanitize_content
import hashlib
from src.config.settings import DEFAULT_BATCH_SIZE, TEMP_DIR, SNAPSHOT_DIR
from src.processors.zeitgeist import zeitgeist_manager

logger = setup_logger("ai_processor")

class BaseAIProcessor(ABC):
    """AI处理器抽象基类"""

    def __init__(self):
        self.system_prompt = self._load_system_prompt()

    def _load_system_prompt(self) -> str:
        """加载系统提示词"""
        return """
你是一位资深科技媒体编辑，负责筛选和加工科技新闻选题。

请对以下新闻进行批量处理，返回 JSON 格式结果：

处理要求：

0. **Twitter内容特殊处理**：对于Twitter转发贴，内容判断以被转发的原贴内容为准，转发者的quote评论仅作为补充参考。如果内容中包含"转发评论:"字样，前面的是原贴内容，后面的是转发者评论，优先基于原贴内容进行判断。

1. **生成量子位风格中文标题**：
   - 纯中文，15-35字
   - 情绪饱满但克制，避免过度使用"刚刚"、"突发"、"炸裂"等感叹词
   - 突出核心信息，用内容本身的新闻性吸引读者

2. **生成一句话摘要**：
   - AI基于理解生成，50-100字
   - 严禁直接复制原文
   - 不含HTML标签

3. **标注类型**（从以下12种类型中选择最贴切的一种）：
   - product(产品发布): 新产品、新功能、开源项目发布
   - funding(融资上市): 融资、IPO、并购、估值变动
   - personnel(人事变动): 高管离职/入职、团队变动、人才挖角
   - opinion(观点访谈): 行业领袖观点、深度访谈、公开发言
   - industry(行业动态): 公司战略调整、市场竞争、合作变动
   - safety(安全伦理): AI安全事件、监管政策、伦理争议
   - research(研究成果): 论文发表、技术突破、基准测试
   - financial(商业数据): 营收、用户数据、业绩报告
   - breaking(突发事件): 突发新闻、内幕消息、独家报道
   - tool(工具技巧): 开发者工具、效率应用、使用技巧
   - society(社会影响): AI对社会结构、文化现象、生活方式的影响
   - hardware(硬件基建): 芯片、算力、数据中心、硬件设备

4. **分析扩展性**：
   - 思考该事件可能引发的连锁反应和延伸报道角度
   - 例如：谷歌新技术→影响美股芯片→影响A股芯片；产品发布→竞品反应→用户迁移→市场份额变化
   - 用1-2句话简洁描述扩展角度

5. **识别核心实体**（2-5个）：公司、产品、人物、技术/概念

   **实体提取规则（重要）**：
   - **产品系列统一**：提取基础产品名，不带版本号。如 `Gemini 2.5 Pro` → `Gemini`，`GPT-4o` → `GPT`，`Claude 3.5` → `Claude`
   - **公司/品牌统一**：同一主体的不同表述统一。如 `Manus AI` 和 `Manus` 都提取为 `Manus`，`OpenAI o3` 和 `o3` 都提取为 `OpenAI`
   - **人物用全名**：如 `Sam Altman` 而非 `Altman`，`Elon Musk` 而非 `Musk`

返回格式必须是严格的JSON数组，每个元素包含：
{
  "index": 0,
  "original_url": "原始新闻URL，与输入完全一致",
  "chinese_title": "中文标题",
  "summary": "一句话摘要",
  "type": "product",
  "extension": "扩展分析",
  "entities": ["实体1", "实体2", "实体3"]
}

注意：
- 只返回JSON，不要任何其他解释性文字
- 确保JSON格式完全正确，没有语法错误
- 所有新闻都需要处理，不要过滤任何内容
"""

    @abstractmethod
    def process_batch(self, items: List[RawNewsItem]) -> List[ProcessedNewsItem]:
        """
        批量处理新闻项
        :param items: 原始新闻项列表
        :return: 处理后的新闻项列表
        """
        pass

    def build_prompt(self, items: List[RawNewsItem]) -> str:
        """构建AI处理提示词"""
        news_list = []
        for i, item in enumerate(items):
            content = item.content
            # 对于Twitter内容，优先保证原贴内容完整，避免截断原贴重要信息
            if item.source.startswith("Twitter"):
                # 如果有转发评论分隔，优先保留原贴内容
                if "转发评论:" in content:
                    original_part = content.split("转发评论:", 1)[0]
                    comment_part = content.split("转发评论:", 1)[1]
                    # 原贴内容最多保留400字符，评论部分保留100字符
                    truncated_original = truncate_text(original_part, max_length=400)
                    truncated_comment = truncate_text(comment_part.strip(), max_length=100)
                    truncated_content = f"{truncated_original}\n\n转发评论: {truncated_comment}"
                else:
                    # 普通Twitter内容保留500字符
                    truncated_content = truncate_text(content, max_length=500)
            else:
                # 其他来源内容正常截断
                truncated_content = truncate_text(content, max_length=500)

            news_item = {
                "index": i,
                "title": item.title,
                "content": truncated_content,
                "source": item.source,
                "url": item.url
            }
            news_list.append(news_item)

        prompt = f"{self.system_prompt}\n\n输入新闻：\n{json.dumps(news_list, ensure_ascii=False, indent=2)}"
        return prompt

    def parse_response(self, response_text: str, original_items: List[RawNewsItem]) -> List[ProcessedNewsItem]:
        """解析AI返回的响应"""
        try:
            # 尝试提取JSON部分
            json_start = response_text.find('[')
            json_end = response_text.rfind(']') + 1

            if json_start == -1 or json_end == 0:
                logger.error("响应中找不到JSON数组")
                return []

            json_text = response_text[json_start:json_end]
            results = json.loads(json_text)

            # Build URL → item lookup for fast exact matching
            url_to_item = {item.url: item for item in original_items if item.url}

            processed_items = []
            for result in results:
                original_item = None
                original_url = result.get("original_url", "")

                # Primary: URL exact match
                if original_url and original_url in url_to_item:
                    original_item = url_to_item[original_url]
                else:
                    # Fallback: index match
                    index = result.get("index", -1)
                    if 0 <= index < len(original_items):
                        original_item = original_items[index]
                        if original_url:
                            logger.warning(f"URL匹配失败，使用索引匹配: index={index}, expected_url={original_url}")

                if original_item is None:
                    continue

                # 标准化实体
                entities = EntityNormalizer.normalize_list(result.get("entities", []))

                processed_item = ProcessedNewsItem(
                    id=original_item.get_unique_id(),
                    original_title=original_item.title,
                    original_content=original_item.content,
                    source=original_item.source,
                    url=original_item.url,
                    published_at=original_item.published_at,
                    chinese_title=sanitize_content(result.get("chinese_title", "")),
                    summary=sanitize_content(result.get("summary", "")),
                    grade="",  # 后续打分阶段填充
                    score=0,   # 后续打分阶段填充
                    news_type=result.get("type", ""),
                    extension=sanitize_content(result.get("extension", "")),
                    entities=entities,
                    raw_item=original_item
                )

                processed_items.append(processed_item)

            logger.info(f"AI基础处理完成: 输入{len(original_items)}条 → 输出{len(processed_items)}条新闻")
            return processed_items

        except json.JSONDecodeError as e:
            logger.error(f"解析AI响应失败: {e}")
            logger.debug(f"响应内容: {response_text[:500]}...")
            return []
        except Exception as e:
            logger.error(f"处理AI响应异常: {e}")
            return []

class LocalAgentProcessor(BaseAIProcessor):
    """本地Agent处理器，通过subprocess调用本地AI"""

    def process_batch(self, items: List[RawNewsItem]) -> List[ProcessedNewsItem]:
        """使用本地Agent处理批量新闻"""
        if not items:
            return []

        logger.info(f"开始本地Agent处理，共{len(items)}条新闻")

        # 构建提示词
        prompt = self.build_prompt(items)

        # 创建临时文件
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', encoding='utf-8', delete=False, dir=TEMP_DIR) as f:
            f.write(prompt)
            prompt_file = f.name

        try:
            # 调用本地AI（这里需要根据实际情况调整命令）
            # 示例：使用claw命令处理
            result_file = os.path.join(TEMP_DIR, f"ai_result_{datetime.now().strftime('%Y%m%d%H%M%S')}.json")

            cmd = [
                "claw", "process",
                "--input", prompt_file,
                "--output", result_file,
                "--model", "claude-3-opus"
            ]

            logger.debug(f"执行命令: {' '.join(cmd)}")

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

            if result.returncode != 0:
                logger.error(f"本地Agent调用失败: {result.stderr}")
                return []

            # 读取结果
            if os.path.exists(result_file):
                with open(result_file, 'r', encoding='utf-8') as f:
                    response_text = f.read()
            else:
                response_text = result.stdout

            return self.parse_response(response_text, items)

        finally:
            # 清理临时文件
            os.unlink(prompt_file)
            if 'result_file' in locals() and os.path.exists(result_file):
                os.unlink(result_file)

class ManualProcessor(BaseAIProcessor):
    """手动处理模式，生成提示词供用户手动处理"""

    def process_batch(self, items: List[RawNewsItem]) -> List[ProcessedNewsItem]:
        """生成提示词，等待用户手动处理"""
        if not items:
            return []

        # 生成快照ID（8位MD5哈希）
        snapshot_content = json.dumps([item.to_dict() if hasattr(item, 'to_dict') else {
            "url": item.url,
            "title": item.title,
            "content": item.content,
            "source": item.source,
            "published_at": item.published_at.isoformat()
        } for item in items], ensure_ascii=False)
        snapshot_id = hashlib.md5(snapshot_content.encode()).hexdigest()[:8]

        # 创建快照对象
        snapshot = {
            "snapshot_id": snapshot_id,
            "created_at": datetime.now().isoformat(),
            "items_count": len(items),
            "items": [
                {
                    "index": i,
                    "id": item.get_unique_id(),
                    "url": item.url,
                    "title": item.title,
                    "content": item.content,
                    "source": item.source,
                    "published_at": item.published_at.isoformat()
                } for i, item in enumerate(items)
            ]
        }

        # 保存快照文件
        snapshot_file = os.path.join(SNAPSHOT_DIR, f"snapshot_{snapshot_id}.json")
        save_json(snapshot, snapshot_file)

        # 生成提示词，包含snapshot_id在文件名中
        prompt = self.build_prompt(items)
        prompt_file = os.path.join(TEMP_DIR, f"ai_prompt_{snapshot_id}.txt")

        with open(prompt_file, 'w', encoding='utf-8') as f:
            f.write(prompt)

        logger.info(f"已生成处理快照: {snapshot_file}")
        logger.info(f"已生成手动处理提示词文件: {prompt_file}")
        logger.info(f"快照ID: {snapshot_id}")
        logger.info("请将提示词发送给AI处理，将结果保存为JSON文件后重新运行脚本")

        # 这里返回空列表，需要用户手动处理后重新运行
        return []

    def load_manual_result(self, result_file: str, original_items: List[RawNewsItem]) -> List[ProcessedNewsItem]:
        """加载手动处理的结果"""
        if not os.path.exists(result_file):
            logger.error(f"结果文件不存在: {result_file}")
            return []

        with open(result_file, 'r', encoding='utf-8') as f:
            response_text = f.read()

        return self.parse_response(response_text, original_items)


class AIScorer:
    """AI新闻打分器，独立负责新闻的打分和定级"""

    def __init__(self):
        self.system_prompt = self._load_scoring_prompt()

    def _load_scoring_prompt(self) -> str:
        """加载打分系统提示词"""
        return """
你是一位资深科技媒体主编，负责对已经初步处理的科技新闻进行打分和定级。

请对以下新闻进行批量打分，返回 JSON 格式结果：

打分标准：
综合以下五个维度打分（0-100分）：
- **话题热度**（社交转发量、讨论量、舆论爆发点）
- **独特性**（颠覆认知/反预期/稀缺视角，而非常规进展）
- **读者价值**（对目标读者的实际影响、认知增益、决策参考；微信是国民级APP，凡涉及微信生态的新闻读者价值自动+10分）
- **可延伸深度**（话题是否可深挖，有无背景故事/数据/关联线索）
- **扩展性**（事件可能引发的连锁反应和延伸报道角度）

级别划分：
- S级（90-100分）：五维均高，必须报道。典型：AI大模型重大发布、马斯克/SpaceX重大动态、Nature/Science顶刊、AGI里程碑
- A+级（85-89分）：至少三维突出，尤其独特性或可延伸深度强。典型：重要产品更新、反预期的行业内幕、大额融资、知名人物重要观点
- A级（75-84分）：两维以上较好，有一定读者价值。典型：科技巨头动态、国产大模型、开源爆款、学术突破
- B级（65-74分）：单维亮点，读者价值有限。典型：产品评测、技术解析
- C级（<65分）：五维均弱，信息密度低，无独特角度，直接过滤

**特殊降分规则**：
- 元宇宙/Metaverse/VR/AR/MR相关内容（除非与AI大模型深度结合或有重大突破），总分自动-20分，最高不超过B级
- 军事/政治相关内容（如涉及军方、政府打压、国际冲突等），总分自动-15分，最高不超过A级
- 不知名公司融资新闻（公司知名度低、缺乏行业影响力），总分自动-20分，最高不超过B级
- **不知名人物创业新闻**（创业者非行业知名领袖、公司无显著影响力或创新突破），总分自动-25分，最高不超过A级
- 一般法律诉讼/败诉/赔偿新闻（常规商业纠纷、专利诉讼等），总分自动-15分，最高不超过A级。但具有重大新闻价值的戏剧性案件除外，如"马斯克起诉OpenAI"、"重大反垄断判决"等
- 地质、环境、考古相关的研究内容，总分自动-15分，最高不超过B级
- 强化学习相关内容（除非有重大理论突破或性能提升超过50%），总分自动不享受额外加分，且最高不超过A+级

**S级新闻严格标准**：
S级（90-100分）必须满足以下条件之一：
- 全球顶级科技公司（OpenAI、Google、Meta、Microsoft、Apple、Amazon、NVIDIA、Tesla/SpaceX、腾讯、阿里、字节、百度等）的重大产品发布或战略调整
- 公认的行业领袖（如马斯克、Sam Altman、Sundar Pichai、Satya Nadella、Jeff Dean、Andrej Karpathy等）的重要公开发言或动态
- Nature/Science/Cell等顶刊发表的重大技术突破
- 具有行业里程碑意义的事件（如AGI相关、重大安全事件、颠覆性技术发布）
- 估值超过100亿美元的知名独角兽公司的重大动态

**不满足上述条件的，即使分数达到90分，最高也只能评为A+级**

返回格式必须是严格的JSON数组，每个元素包含：
{
  "index": 0,
  "original_url": "原始新闻URL，与输入完全一致",
  "grade": "S/A+/A/B/C",
  "score": 88
}

注意：
- 只返回JSON，不要任何其他解释性文字
- 确保JSON格式完全正确，没有语法错误
- 对于C级新闻（<65分），仍然返回但grade标记为"C"
"""

    def build_scoring_prompt(self, items: List[ProcessedNewsItem]) -> str:
        """构建打分提示词"""
        news_list = []
        for i, item in enumerate(items):
            news_item = {
                "index": i,
                "original_title": item.original_title,
                "original_content": item.original_content,
                "chinese_title": item.chinese_title,
                "summary": item.summary,
                "source": item.source,
                "url": item.url,
                "entities": item.entities,
                "type": item.news_type
            }
            news_list.append(news_item)

        prompt = f"{self.system_prompt}\n\n待打分新闻：\n{json.dumps(news_list, ensure_ascii=False, indent=2)}"
        return prompt

    def parse_scoring_response(self, response_text: str, processed_items: List[ProcessedNewsItem]) -> List[ProcessedNewsItem]:
        """解析打分响应"""
        try:
            # 尝试提取JSON部分
            json_start = response_text.find('[')
            json_end = response_text.rfind(']') + 1

            if json_start == -1 or json_end == 0:
                logger.error("打分响应中找不到JSON数组")
                return []

            json_text = response_text[json_start:json_end]
            results = json.loads(json_text)

            # Build URL → item lookup
            url_to_item = {item.url: item for item in processed_items if item.url}

            scored_items = []
            for result in results:
                item = None
                original_url = result.get("original_url", "")

                # Primary: URL exact match
                if original_url and original_url in url_to_item:
                    item = url_to_item[original_url]
                else:
                    # Fallback: index match
                    index = result.get("index", -1)
                    if 0 <= index < len(processed_items):
                        item = processed_items[index]
                        if original_url:
                            logger.warning(f"URL匹配失败，使用索引匹配: index={index}, expected_url={original_url}")

                if item is None:
                    continue

                # 获取AI给出的分数和等级
                ai_score = result.get("score", 0)
                ai_grade = result.get("grade", "C")

                # 特殊加分规则：Geoffrey Hinton相关内容自动+5分，最低85分（A+级）
                content_lower = (item.original_title + " " + item.original_content).lower()
                is_hinton_related = any(keyword in content_lower for keyword in ["hinton", "geoffrey hinton", "辛顿", "杰弗里·辛顿", "AI教父"])
                if is_hinton_related:
                    original_score = ai_score
                    ai_score = min(ai_score + 5, 100)  # 最高不超过100分
                    ai_score = max(ai_score, 85)       # 最低不低于85分
                    if ai_score > original_score:
                        logger.info(f"Hinton相关新闻加分: {original_score} → {ai_score}")

                # 时代情绪加分：符合当前热点趋势的新闻额外加分
                zeitgeist_boost, matched_trends = zeitgeist_manager.get_boost_for_content(
                    item.original_title, item.original_content, item.entities
                )
                if zeitgeist_boost > 0:
                    original_score = ai_score
                    ai_score = min(ai_score + zeitgeist_boost, 100)  # 最高不超过100分
                    if ai_score > original_score:
                        logger.info(f"时代情绪加分 [{','.join(matched_trends)}]: {original_score} → {ai_score}")

                # 根据调整后的分数重新评定等级
                if ai_score >= 90:
                    final_grade = "S"
                elif ai_score >= 85:
                    final_grade = "A+"
                elif ai_score >= 75:
                    final_grade = "A"
                elif ai_score >= 65:
                    final_grade = "B"
                else:
                    final_grade = "C"
                    continue  # C级直接过滤

                # 更新item的分数和等级
                item.score = ai_score
                item.grade = final_grade

                scored_items.append(item)

            logger.info(f"AI打分完成: 输入{len(processed_items)}条 → 输出{len(scored_items)}条有效新闻")
            return scored_items

        except json.JSONDecodeError as e:
            logger.error(f"解析打分响应失败: {e}")
            logger.debug(f"响应内容: {response_text[:500]}...")
            return []
        except Exception as e:
            logger.error(f"处理打分响应异常: {e}")
            return []

    def score_batch(self, items: List[ProcessedNewsItem]) -> List[ProcessedNewsItem]:
        """批量打分（手动模式，生成提示词供用户处理）"""
        if not items:
            return []

        prompt = self.build_scoring_prompt(items)
        prompt_file = os.path.join(TEMP_DIR, f"scoring_prompt_{datetime.now().strftime('%Y%m%d%H%M%S')}.txt")

        with open(prompt_file, 'w', encoding='utf-8') as f:
            f.write(prompt)

        logger.info(f"已生成分打提示词文件: {prompt_file}")
        logger.info("请将提示词发送给AI处理，将结果保存为JSON文件后重新运行脚本")

        # 这里返回空列表，需要用户手动处理后重新运行
        return []

    def load_manual_scoring_result(self, result_file: str, processed_items: List[ProcessedNewsItem]) -> List[ProcessedNewsItem]:
        """加载手动打分的结果"""
        if not os.path.exists(result_file):
            logger.error(f"打分结果文件不存在: {result_file}")
            return []

        with open(result_file, 'r', encoding='utf-8') as f:
            response_text = f.read()

        return self.parse_scoring_response(response_text, processed_items)
