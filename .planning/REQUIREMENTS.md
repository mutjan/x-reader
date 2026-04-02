# v2.0 Requirements
**Project:** 科技新闻选题聚合系统
**Version:** v2.0
**Last updated:** 2026-04-01

## v2.0 Goals

重构同事件新闻自动分组功能，采用独立分组文件存储方案，保持原有新闻数据结构不变，前端聚合展示事件时间线，提升编辑对事件发展脉络的感知效率。解决v1.0中合并新闻导致原始信息丢失的问题。

---

## Grouping (GRP)

核心分组功能需求

- [ ] **GRP-01**: 独立分组关系存储 — 新增 `event_groups.json` 文件存储分组关系（组ID → 新闻ID列表），不修改原有 `news_data.json` 结构
- [ ] **GRP-02**: 自动事件分组识别 — 基于标题、摘要、实体多维度相似度计算，自动识别同事件新闻并分组
- [ ] **GRP-03**: 增量更新支持 — 每次增量抓取时，新新闻自动匹配已有事件组或创建新事件组，不需要全量重新分组
- [x] **GRP-04**: 移除原有合并逻辑 — 从处理流水线移除 `merge_similar_news` 逻辑，每条新闻保持独立存储

---

## Storage (STOR)

存储层需求

- [ ] **STOR-01**: `event_groups.json` 结构设计 — 每个事件组包含：group_id, event_title, first_seen_at, last_seen_at, news_ids list, score
- [ ] **STOR-02**: 原子写入保证 — 采用"临时文件+原子替换"写入模式，避免双文件数据不一致
- [ ] **STOR-03**: 自动备份 — 每次修改自动备份，保留最近30天备份

---

## Frontend (UI)

前端展示需求

- [ ] **UI-01**: 事件时间线展示 — 同一事件组内的多条新闻按发布时间排序聚合展示
- [ ] **UI-02**: 保持独立新闻浏览 — 单条新闻仍然可以独立浏览，不影响原有用户体验
- [ ] **UI-03**: 过滤排序兼容 — 现有过滤排序功能对事件分组正常工作

---

## Integration (INT)

流水线集成需求

- [ ] **INT-01**: 在处理流水线新增 EventGrouper 阶段 — 位置在 AI 处理后，发布前
- [ ] **INT-02**: 修改发布流程同时发布 `news_data.json` 和 `event_groups.json` 两个文件
- [ ] **INT-03**: GitHub Pages 发布流程同步更新，确保两个文件都被推送

---

## Deferred Requirements (v2.1+)

- GRP-05: 事件热度聚合计算 — 同一事件热度值聚合计算，提升排序优先级
- GRP-06: 手动分组调整 — 支持编辑手动修正自动分组错误
- GRP-07: 分组双向关联 — 每条新闻可查看所属事件组，事件组可查看所有相关新闻
- UI-04: 智能事件标题自动生成
- UI-05: 事件发展脉络自动摘要

## Out of Scope

- 修改 `news_data.json` 结构 — 保持不变，仅新增文件
- 引入数据库依赖 — 保持纯JSON文件存储架构
- 支持拆分已有事件组 — v2.0只支持自动分组，手动调整延期

---

## Traceability

| Requirement ID | Phase | Status |
|----------------|-------|--------|
| GRP-01 | Phase 8 | Pending |
| GRP-02 | Phase 8 | Pending |
| GRP-03 | Phase 9 | Pending |
| GRP-04 | Phase 7 | Complete |
| STOR-01 | Phase 8 | Pending |
| STOR-02 | Phase 9 | Pending |
| STOR-03 | Phase 8 | Pending |
| UI-01 | Phase 10 | Pending |
| UI-02 | Phase 10 | Pending |
| UI-03 | Phase 10 | Pending |
| INT-01 | Phase 9 | Pending |
| INT-02 | Phase 9 | Pending |
| INT-03 | Phase 9 | Pending |

*Traceability filled by gsd-roadmapper*
