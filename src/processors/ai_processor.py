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
from src.utils.common import setup_logger, truncate_text, save_json, load_json
from src.config.settings import DEFAULT_BATCH_SIZE, TEMP_DIR

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

1. **筛选选题**（S级/A+级/A级/B级），综合以下四个维度打分：
   - **话题热度**（社交转发量、讨论量、舆论爆发点）
   - **独特性**（颠覆认知/反预期/稀缺视角，而非常规进展）
   - **读者价值**（对目标读者的实际影响、认知增益、决策参考；微信是国民级APP，凡涉及微信生态的新闻读者价值自动+10分）
   - **可延伸深度**（话题是否可深挖，有无背景故事/数据/关联线索）
   - **扩展性**（事件可能引发的连锁反应和延伸报道角度，如：技术突破→产业链影响→资本市场反应→政策监管动向）

   五维综合得分决定级别：
   - S级（90-100分）：四维均高，必须报道。典型：AI大模型重大发布、马斯克/SpaceX重大动态、Nature/Science顶刊、AGI里程碑
   - A+级（85-89分）：至少三维突出，尤其独特性或可延伸深度强。典型：重要产品更新、反预期的行业内幕、大额融资、知名人物重要观点
   - A级（75-84分）：两维以上较好，有一定读者价值。典型：科技巨头动态、国产大模型、开源爆款、学术突破
   - B级（65-74分）：单维亮点，读者价值有限。典型：产品评测、技术解析
   - 过滤掉C级（<65分）：四维均弱，信息密度低，无独特角度

   **特殊降分规则**：
   - 元宇宙/Metaverse/VR/AR/MR相关内容（除非与AI大模型深度结合或有重大突破），总分自动-20分，最高不超过B级
   - 军事/政治相关内容（如涉及军方、政府打压、国际冲突等），总分自动-15分，最高不超过A级
   - 不知名公司融资新闻（公司知名度低、缺乏行业影响力），总分自动-20分，最高不超过B级
   - 一般法律诉讼/败诉/赔偿新闻（常规商业纠纷、专利诉讼等），总分自动-15分，最高不超过A级。但具有重大新闻价值的戏剧性案件除外，如"马斯克起诉OpenAI"、"重大反垄断判决"等

2. **生成量子位风格中文标题**：
   - 纯中文，15-35字
   - 情绪饱满但克制，避免过度使用"刚刚"、"突发"、"炸裂"等感叹词
   - 突出核心信息，用内容本身的新闻性吸引读者

3. **生成一句话摘要**：
   - AI基于理解生成，50-100字
   - 严禁直接复制原文
   - 不含HTML标签

4. **标注类型**（从以下12种类型中选择最贴切的一种）：
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

5. **分析扩展性**：
   - 思考该事件可能引发的连锁反应和延伸报道角度
   - 例如：谷歌新技术→影响美股芯片→影响A股芯片；产品发布→竞品反应→用户迁移→市场份额变化
   - 用1-2句话简洁描述扩展角度

6. **识别核心实体**（2-5个）：公司、产品、人物、技术/概念

   **实体提取规则（重要）**：
   - **产品系列统一**：提取基础产品名，不带版本号。如 `Gemini 2.5 Pro` → `Gemini`，`GPT-4o` → `GPT`，`Claude 3.5` → `Claude`
   - **公司/品牌统一**：同一主体的不同表述统一。如 `Manus AI` 和 `Manus` 都提取为 `Manus`，`OpenAI o3` 和 `o3` 都提取为 `OpenAI`
   - **人物用全名**：如 `Sam Altman` 而非 `Altman`，`Elon Musk` 而非 `Musk`

返回格式必须是严格的JSON数组，每个元素包含：
{
  "index": 0,
  "chinese_title": "中文标题",
  "summary": "一句话摘要",
  "grade": "S/A+/A/B/C",
  "score": 88,
  "type": "product",
  "extension": "扩展分析",
  "entities": ["实体1", "实体2", "实体3"]
}

注意：
- 只返回JSON，不要任何其他解释性文字
- 确保JSON格式完全正确，没有语法错误
- 对于C级新闻（<65分），仍然返回但grade标记为"C"，会在后续步骤中过滤
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
            # 截断过长的内容
            truncated_content = truncate_text(item.content, max_length=500)
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

            processed_items = []
            for result in results:
                index = result.get("index", -1)
                if index < 0 or index >= len(original_items):
                    continue

                original_item = original_items[index]
                grade = result.get("grade", "C")

                # 过滤C级新闻
                if grade == "C":
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
                    chinese_title=result.get("chinese_title", ""),
                    summary=result.get("summary", ""),
                    grade=grade,
                    score=result.get("score", 0),
                    news_type=result.get("type", ""),
                    extension=result.get("extension", ""),
                    entities=entities,
                    raw_item=original_item
                )

                processed_items.append(processed_item)

            logger.info(f"AI处理完成: 输入{len(original_items)}条 → 输出{len(processed_items)}条有效新闻")
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

        prompt = self.build_prompt(items)
        prompt_file = os.path.join(TEMP_DIR, f"ai_prompt_{datetime.now().strftime('%Y%m%d%H%M%S')}.txt")

        with open(prompt_file, 'w', encoding='utf-8') as f:
            f.write(prompt)

        logger.info(f"已生成手动处理提示词文件: {prompt_file}")
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
