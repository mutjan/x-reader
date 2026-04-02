# Project Research Summary

**Project:** x-reader 科技新闻选题聚合系统（v2.0 同事件新闻分组功能）
**Domain:** 内部编辑工具/科技新闻聚合平台
**Researched:** 2026-04-01
**Confidence:** HIGH

## Executive Summary

这是一个面向内部编辑团队的科技新闻选题聚合系统，通过自动化抓取、AI评估、智能分类等功能，帮助编辑快速发现高价值报道线索，降低信息搜集成本。v2.0版本新增同事件新闻分组功能，将属于同一事件的多条新闻聚合展示，呈现事件发展脉络，进一步提升编辑工作效率。

基于研究，推荐采用非破坏性扩展架构，在现有处理流程中新增独立的事件分组阶段，使用rapidfuzz库实现高性能文本相似度计算，采用增量层次聚类算法实现事件分组。所有分组数据独立存储于event_groups.json文件，完全兼容现有news_data.json结构，避免破坏现有系统稳定性。

核心风险包括双文件写入原子性问题、分组信息丢失、并发写入冲突等，通过原子替换写入模式、同步清理机制、文件锁等方案可以有效规避。整体方案完全复用现有技术栈，新增依赖最小，实现成本可控，风险可防。

## Key Findings

### Recommended Stack

v2.0同事件分组功能采用增量扩展方案，完全兼容现有Python/Flask技术栈，仅新增必要的算法依赖，不修改现有存储架构和数据模型。详细内容见[STACK.md](STACK.md)。

**Core technologies:**
- rapidfuzz >=3.9.0: 文本相似度计算 — MIT协议，纯Python实现，性能比fuzzywuzzy快5-10倍，支持中文多语言场景，替代现有简单余弦相似度实现
- 增量层次聚类算法: 事件分组核心 — 支持每小时增量更新，无需全局重新计算，适合现有批处理架构，算法复杂度低，易调试维护
- JSON文件存储: 分组关系持久化 — 保持现有架构轻量，新增event_groups.json文件存储组ID到新闻ID列表的映射，无需引入数据库

### Expected Features

v2.0版本聚焦同事件分组核心功能，优先实现基础分组能力，高级特性逐步迭代。详细内容见[FEATURES.md](FEATURES.md)。

**Must have (table stakes):**
- 独立分组关系存储 — 不修改现有news_data.json结构，分组信息独立存储
- 自动事件分组识别 — 基于标题、摘要、实体多维度相似度自动识别同事件新闻
- 事件时间线展示 — 同一事件的新闻按时间顺序聚合展示，呈现发展脉络
- 增量更新支持 — 新抓取新闻自动匹配已有事件组或创建新组

**Should have (competitive):**
- 事件热度聚合计算 — 同一事件热度值聚合计算，提升高价值事件排序优先级
- 手动分组调整功能 — 支持编辑手动调整分组关系，修正自动分组错误
- 分组信息双向关联 — 每条新闻可查看所属事件组，事件组可查看所有相关新闻

**Defer (v2.1+):**
- 智能事件标题生成 — 需要AI能力集成，可后续迭代
- 事件发展脉络摘要 — 高复杂度，非核心需求
- 事件追踪提醒 — 增值功能，优先级较低

### Architecture Approach

采用非破坏性扩展架构，在现有处理流水线AI处理阶段后新增独立的事件分组阶段，不修改现有数据结构和核心逻辑，保证向后兼容性。详细内容见[ARCHITECTURE.md](ARCHITECTURE.md)。

**Major components:**
1. EventGrouper: 事件分组核心组件 — 负责相似度计算、事件聚类、分组关系生成
2. 双文件存储层: 保持news_data.json不变，新增event_groups.json存储分组关系，通过event_id字段关联
3. 前端聚合层: 同时加载两个JSON文件，在展示层实现事件时间线聚合，不修改后端API
4. 增量更新机制: 每次批处理仅对新新闻执行分组匹配，避免全量重新计算，提升性能

### Critical Pitfalls

v2.0新增功能存在多个特有的架构风险，需要在开发阶段重点防控。详细内容见[PITFALLS.md](PITFALLS.md)。

1. **双文件原子性写入失败** — 采用"先写临时文件，再原子替换"的写入模式，写入前校验分组引用完整性，实现自动恢复机制
2. **分组信息丢失（新闻过期删除）** — 新闻过期清理时同步更新分组文件，分组保存独立元数据，延长参与分组的新闻保留周期
3. **并发写入冲突** — 实现文件锁机制，写入前做版本校验，避免并发覆盖
4. **分组算法迭代导致数据震荡** — 分组算法版本化，新算法结果尽可能与旧分组匹配合并，重要事件支持人工锁定
5. **历史数据迁移不完整** — 迁移前全量扫描现有event_id格式，编写幂等迁移脚本，迁移后做一致性校验

## Implications for Roadmap

基于研究，建议分4个阶段实现v2.0同事件分组功能：

### Phase 1: 移除旧合并逻辑 + 基础架构准备
**Rationale:** 首先清理现有系统中已有的相似新闻合并逻辑，为新分组功能腾出位置，同时准备配置和数据模型
**Delivers:** 可运行的基础流水线，无合并逻辑冲突，配置项就绪
**Addresses:** 架构清理准备，为后续分组功能集成打基础
**Avoids:** 新旧逻辑冲突导致的重复分组或数据丢失
**Research flag:** No research needed, simple code removal and configuration changes

### Phase 2: EventGrouper核心组件开发
**Rationale:** 独立开发分组核心逻辑，不影响现有流水线，便于单独测试和优化算法
**Delivers:** 功能完整的事件分组组件，支持增量分组，生成正确的event_groups.json文件
**Uses:** rapidfuzz相似度库，增量层次聚类算法
**Implements:** EventGrouper核心组件，相似度计算逻辑，分组持久化功能
**Avoids:** 算法选择错误、分组ID冲突等核心风险
**Research flag:** Needs research for similarity threshold tuning and algorithm parameter optimization based on real data

### Phase 3: 流水线集成与发布流程改造
**Rationale:** 将分组组件集成到现有处理流水线，修改发布流程支持双文件同时发布
**Delivers:** 完整的后端处理流程，可正确生成并发布news_data.json和event_groups.json两个文件
**Addresses:** 双文件原子性写入、并发写入冲突、分组信息丢失等关键陷阱
**Avoids:** 数据不一致、并发覆盖、引用失效等架构风险
**Research flag:** Needs research for atomic write mechanisms and concurrency control patterns

### Phase 4: 前端时间线展示与用户交互
**Rationale:** 后端功能稳定后再开发前端展示，可并行进行不影响后端迭代
**Delivers:** 事件时间线展示功能，支持事件分组浏览，双向关联跳转
**Addresses:** 事件时间线展示、双向关联等用户可见功能
**Avoids:** 前端加载性能下降、引用失效导致的渲染错误
**Research flag:** No research needed, standard frontend data aggregation and rendering patterns

### Phase Ordering Rationale

- 遵循依赖关系：从架构清理到核心组件开发，再到集成和前端展示，每个阶段依赖前一阶段的输出，风险逐步释放
- 架构模式匹配：符合现有流水线的分层架构，保持各组件职责单一，便于测试和维护
- 风险前置：核心算法和架构风险在前期阶段解决，避免后期发现根本性问题导致大规模返工
- 渐进式交付：每个阶段都有可验证的产出，可随时暂停或调整，不影响现有系统运行

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 2: EventGrouper核心组件开发** — 相似度阈值调整、算法参数优化需要基于真实数据测试，可能需要多次迭代
- **Phase 3: 流水线集成与发布流程改造** — 双文件原子性写入、并发控制需要模拟各种异常场景测试，确保可靠性

Phases with standard patterns (skip research-phase):
- **Phase 1: 移除旧合并逻辑** — 简单的代码删除和配置添加，已有明确方案
- **Phase 4: 前端时间线展示** — 标准的前端数据聚合和渲染，无特殊技术难点

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | 基于成熟开源库和现有架构扩展，所有技术选择均经过验证，有明确的性能对比和选型理由 |
| Features | MEDIUM | 基于编辑团队需求和行业最佳实践，缺少公开市场竞品数据验证，但核心需求明确 |
| Architecture | HIGH | 基于现有系统架构的非破坏性扩展，所有修改均不破坏现有功能，有清晰的集成路径和回滚方案 |
| Pitfalls | HIGH | 基于项目历史问题和静态文件架构的共性风险，所有陷阱均有明确的预防和检测方案 |

**Overall confidence:** HIGH

### Gaps to Address

- 相似度阈值优化：当前推荐的0.75阈值需要基于真实新闻数据进行测试调整，可能需要多轮迭代找到最优值
- 算法性能验证：当单批次新闻量超过1000条时，需要验证rapidfuzz的性能是否满足要求，是否需要引入scikit-learn优化
- 历史数据迁移：现有系统中已有event_id字段的格式和分布需要实际扫描确认，迁移脚本需要根据实际情况调整
- 前端性能：当事件数量超过1000个时，前端聚合渲染性能需要实际测试，可能需要分页或懒加载优化

## Sources

### Primary (HIGH confidence)
- [rapidfuzz official documentation](https://github.com/maxbachmann/RapidFuzz) — 文本相似度库选型
- [scikit-learn incremental clustering guide](https://scikit-learn.org/stable/modules/clustering.html) — 聚类算法研究
- 现有代码base分析 (main.py, duplicate.py, event_grouper.py, github_pages.py) — 架构集成方案
- 项目历史Issue: 标题-链接错位问题（2026-03-28修复） — 陷阱识别

### Secondary (MEDIUM confidence)
- [Event-based news clustering best practices](https://towardsdatascience.com/event-clustering-for-news-articles-8a3b7c8a8e7d) — 事件分组算法参考
- [RapidFuzz vs FuzzyWuzzy performance comparison](https://maxbachmann.github.io/RapidFuzz/performance.html) — 性能对比
- 内部编辑团队工作流程调研 — 功能需求分析
- 静态JSON多文件一致性处理行业实践 — 风险防控方案

---
*Research completed: 2026-04-01*
*Ready for roadmap: yes*
