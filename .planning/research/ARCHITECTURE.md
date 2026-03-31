# Architecture Patterns

**Domain:** 科技新闻选题聚合系统
**Researched:** 2026-03-31
**Confidence:** HIGH (基于现有系统架构扩展，符合行业通用模式)

## Recommended Architecture

基于现有x-reader系统的模块化流水线架构扩展，新增**选题处理层**嵌入现有处理流程，整体保持清晰的分层结构和责任边界：

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│  现有抓取层  │ →  │ 现有去重过滤 │ →  │  新增选题层  │ →  │ 现有AI处理层 │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
                                                               ↓
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│  编辑后台   │ ←  │  选题存储   │ ←  │ 结果后处理  │ ←  │ AI结果解析  │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
```

### Component Boundaries

| Component | Responsibility | Communicates With |
|-----------|---------------|-------------------|
| **选题评估引擎** (新增) | 多维度计算选题价值：热度、新颖度、领域匹配度、时效性评分 | 现有去重过滤模块、AI处理器 |
| **智能分类器** (新增) | 自动分类、标签生成、领域识别 | AI处理器、选题存储 |
| **热度计算器** (新增) | 基于传播数据、时间衰减计算实时热度 | 抓取层、选题存储 |
| **选题存储** (新增) | 持久化选题数据，支持按多维度查询 | 所有选题组件、Web层 |
| **编辑管理模块** (新增) | 信源配置、阈值调整、选题标记、导出功能 | 选题存储、Web层 |
| **现有抓取层** | 无改造，复用现有RSS抓取能力 | 去重过滤层 |
| **现有去重过滤层** | 无改造，复用现有去重过滤逻辑 | 选题评估引擎 |
| **现有AI处理层** | 扩展prompt模板，增加选题相关字段生成 | 选题评估引擎、结果解析 |
| **现有Web层** | 扩展页面，增加选题展示和管理界面 | 选题存储、编辑管理模块 |

### Data Flow

**集成后完整数据流：**
1. **抓取阶段**：现有RSS抓取器获取原始新闻 → 生成RawNewsItem
2. **预处理阶段**：现有去重模块去重 → 过滤模块排除低质量内容
3. **选题评估阶段**：
   - 选题评估引擎计算初始价值评分
   - 热度计算器基于传播数据和时间因子计算热度
4. **AI处理阶段**：
   - 扩展现有prompt模板，增加选题价值分析、分类、标签、摘要要求
   - 生成AI处理请求 → 导入AI结果 → 解析为带选题字段的ProcessedNewsItem
5. **后处理阶段**：
   - 智能分类器基于AI结果自动归类和打标签
   - 二次校准选题价值评分
   - 存储到选题数据库
6. **消费阶段**：
   - Web界面按领域/热度/时间维度展示选题
   - 编辑通过管理模块标记选题、调整配置、导出选题列表

## Patterns to Follow

### Pattern 1: 流水线嵌入模式
**What:** 选题处理作为独立阶段嵌入现有处理流水线，不破坏现有流程
**When:** 复用现有成熟的抓取、去重、AI处理能力
**Example:**
```python
# 现有main.py流水线扩展
def run_pipeline():
    raw_items = fetchers.fetch_all()
    deduped_items = duplicate_remover.process(raw_items)
    filtered_items = content_filter.process(deduped_items)
    # 新增选题评估阶段
    scored_items = topic_evaluator.process(filtered_items)
    # 现有AI处理阶段（扩展prompt）
    ai_results = ai_processor.process_batch(scored_items)
    # 新增选题后处理阶段
    processed_topics = topic_classifier.process(ai_results)
    topic_storage.save(processed_topics)
    # 现有发布流程
    publisher.publish(processed_topics)
```

### Pattern 2: 评分叠加模式
**What:** 基础规则评分 + AI评估评分双权重叠加，保证选题质量
**When:** 多维度选题价值评估
**Rationale:** 规则评分保证稳定性，AI评估保证语义理解能力，两者加权得到最终评分

## Anti-Patterns to Avoid

### Anti-Pattern 1: 重造现有能力
**What:** 重新开发抓取、去重、AI处理等已有功能
**Why bad:** 重复开发，增加维护成本，破坏现有系统稳定性
**Instead:** 完全复用现有成熟模块，仅扩展必要的选题相关字段和逻辑

### Anti-Pattern 2: 紧耦合设计
**What:** 将选题逻辑嵌入现有处理器内部，导致职责不清
**Why bad:** 后续难以扩展和修改选题逻辑，影响现有功能
**Instead:** 保持选题组件独立，通过标准接口与现有模块交互

## Build Order Dependencies

建议开发顺序（按依赖关系）：
1. **Phase 1: 数据模型扩展** → 扩展ProcessedNewsItem增加选题相关字段（评分、分类、标签、热度等）
   - 无上游依赖，基础准备
2. **Phase 2: 选题评估引擎** → 实现基于规则的基础评分和热度计算
   - 依赖数据模型扩展
3. **Phase 3: AI处理扩展** → 修改AI prompt模板，增加选题分析要求，扩展解析逻辑
   - 依赖数据模型扩展、选题评估引擎
4. **Phase 4: 选题存储** → 实现选题数据持久化和查询接口
   - 依赖数据模型扩展
5. **Phase 5: 智能分类器** → 实现自动分类和标签生成逻辑
   - 依赖AI处理扩展、选题存储
6. **Phase 6: Web界面扩展** → 实现选题展示和筛选功能
   - 依赖选题存储
7. **Phase 7: 编辑管理模块** → 实现配置和管理功能
   - 依赖选题存储、Web界面

## Scalability Considerations

| Concern | At 100 feeds | At 1000 feeds | At 10k feeds |
|---------|--------------|--------------|-------------|
| 评分计算 | 实时计算 | 批量异步计算 | 分布式计算队列 |
| 存储 | 单JSON文件 | SQLite数据库 | PostgreSQL + 全文索引 |
| 更新频率 | 每小时 | 每30分钟 | 每10分钟增量更新 |
| 热度计算 | 静态因子 | 实时衰减算法 | 流式计算框架 |

## Sources

- 现有x-reader系统架构分析 (.planning/codebase/ARCHITECTURE.md)
- 新闻聚合系统行业通用架构模式 (行业经验)
