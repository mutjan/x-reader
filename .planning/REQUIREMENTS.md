# v1 Requirements

**Project:** 科技新闻选题聚合系统
**Version:** v1.0
**Last updated:** 2026-03-31

## v1 Requirements

### Data Layer (DATA)
- [ ] **DATA-01**: 多源RSS新闻自动抓取聚合（复用现有x-reader功能）
- [ ] **DATA-02**: 新闻自动去重（复用现有x-reader功能）
- [ ] **DATA-03**: 新闻URL唯一主键机制，彻底解决AI结果匹配错位问题
- [ ] **DATA-04**: 处理前列表快照机制，保证AI输入输出一致性

### AI Processing Layer (AI)
- [ ] **AI-01**: 多维度选题价值评分（热度、新颖度、领域匹配度、时效性），Agent在上下文处理，不使用独立脚本
- [ ] **AI-02**: 智能分类与标签生成（按AI、半导体、硬科技、消费电子等科技子领域归类）
- [ ] **AI-03**: 新闻摘要自动生成，帮助编辑快速了解核心内容
- [ ] **AI-04**: 同源新闻脉络关联，自动识别同一事件的相关报道，形成事件时间线
- [ ] **AI-05**: 选题评分校准机制，支持人工反馈调整评分模型

### Interaction Layer (UI)
- [ ] **UI-01**: 多维度筛选功能，支持按领域、热度、时间、评分筛选
- [ ] **UI-02**: 多维度排序功能，支持按热度、时间、评分排序
- [ ] **UI-03**: 选题标记功能，支持标记「入选」「待跟进」「忽略」状态
- [ ] **UI-04**: 新闻列表展示，包含标题、摘要、评分、标签、来源、发布时间
- [ ] **UI-05**: 原文跳转功能，点击新闻跳转至来源站点

### Infrastructure Layer (INFRA)
- [ ] **INFRA-01**: 定时任务脚本和技能定义（由其他Agent负责调度执行，本项目只提供可执行脚本）
- [ ] **INFRA-02**: 增量更新机制，小时级更新新闻数据
- [ ] **INFRA-03**: 信源白名单管理，保障内容质量
- [ ] **INFRA-04**: 基础访问控制，仅限内部编辑使用

## v2 Deferred Requirements
- [ ] 选题热度趋势预测（高复杂度，需要历史数据积累）
- [ ] 选题价值动态调整（需要实时数据处理能力）
- [ ] 编辑偏好自适应（需要用户行为数据积累）
- [ ] 选题池协作功能（小团队初期可手动同步）
- [ ] 选题导出功能（非核心需求，后续根据使用情况添加）
- [ ] 复杂用户权限系统（内部使用无需复杂权限）

## Out of Scope
- ❌ 面向普通用户的公开资讯站 - 保持内部工具属性
- ❌ 内容发布功能 - 仅提供选题线索，不涉及内容生产
- ❌ 社交媒体内容抓取 - v1阶段仅处理RSS信源
- ❌ 全文内容存储 - 仅存储元数据，避免版权风险
- ❌ 智能写稿功能 - 聚焦选题发现，不涉及内容生成

## Traceability
| Requirement ID | Phase | Status |
|----------------|-------|--------|
| DATA-01 | TBD | Pending |
| DATA-02 | TBD | Pending |
| DATA-03 | TBD | Pending |
| DATA-04 | TBD | Pending |
| AI-01 | TBD | Pending |
| AI-02 | TBD | Pending |
| AI-03 | TBD | Pending |
| AI-04 | TBD | Pending |
| AI-05 | TBD | Pending |
| UI-01 | TBD | Pending |
| UI-02 | TBD | Pending |
| UI-03 | TBD | Pending |
| UI-04 | TBD | Pending |
| UI-05 | TBD | Pending |
| INFRA-01 | TBD | Pending |
| INFRA-02 | TBD | Pending |
| INFRA-03 | TBD | Pending |
| INFRA-04 | TBD | Pending |
