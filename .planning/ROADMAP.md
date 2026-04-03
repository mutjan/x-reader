# 科技新闻选题聚合系统 Roadmap
**Version:** v2.0
**Last updated:** 2026-04-03
**Granularity:** Standard
**Coverage:** 15/15 requirements mapped

## Phases
- [x] **Phase 1: Data Layer Stability** - Resolve historical data consistency issues and build stable data foundation
- [x] **Phase 2: Core AI Topic Processing** - Implement core AI evaluation, classification, and summarization capabilities
- [x] **Phase 3: AI Enhancement & Calibration** - Add event association and score feedback calibration mechanisms
- [x] **Phase 4: Source Management & Access Control** - Implement source whitelist and internal access restriction
- [x] **Phase 5: Scheduling & Incremental Updates** - Implement hourly automatic updates and scheduled execution scripts
- [x] **Phase 6: Web UI & Editorial Interaction** - Deliver complete editorial interaction interface
- [x] **Phase 7: Cleanup Existing Merge Logic** - Remove old similar news merge functionality and prepare for new grouping architecture (completed 2026-04-02)
- [x] **Phase 8: EventGrouper Core Component Development** - Implement event grouping core logic and data model (completed 2026-04-02)
- [x] **Phase 9: Pipeline Integration & Publishing Workflow** - Integrate grouping into processing pipeline and dual-file publishing (completed 2026-04-02)
- [x] **Phase 10: Frontend Event Timeline Display** - Implement event timeline presentation and user interaction features (completed 2026-04-02)
- [x] **Phase 11: Event Table Refactor** - Refactor event display to table style with expand/collapse functionality (completed 2026-04-02)
- [x] **Phase 12: UX 体验优化** - 优化前端交互体验：扩展性字段截断hover展开、事件表头排序、工具栏功能、筛选控件样式 (completed 2026-04-02)
- [x] **Phase 13: 事件展示与实体识别优化** - 事件表格显示消息源链接、调整实体识别流程顺序、统一事件行高度限制 (completed 2026-04-03)
- [ ] **Phase 14: 前端新闻表格统一化优化** - 新闻列表行高统一由标题决定、事件链接显示消息来源名称、修复实体列高度显示问题

## Phase Details

### Phase 7: Cleanup Existing Merge Logic
**Goal**: Remove conflicting legacy merge logic and prepare system for new grouping functionality
**Depends on**: Phase 6
**Requirements**: GRP-04
**Success Criteria** (what must be TRUE):
  1. `merge_similar_news` function is completely removed from processing pipeline
  2. All news items are preserved as individual entries in news_data.json, no merging occurs
  3. Processing pipeline runs successfully without errors after removal
  4. Existing news_data.json structure remains completely unchanged
**Plans**: 1 plan
Plans:
- [x] 07-01-PLAN.md — Remove legacy merge_similar_news functionality from all components
### Phase 8: EventGrouper Core Component Development
**Goal**: Build complete event grouping core functionality with proper data storage
**Depends on**: Phase 7
**Requirements**: GRP-01, GRP-02, STOR-01, STOR-03
**Success Criteria** (what must be TRUE):
  1. EventGrouper component can automatically group similar news items based on multi-dimensional similarity
  2. event_groups.json file is created with proper structure storing group to news ID mappings
  3. Automatic backup mechanism preserves last 7 days of grouping history
  4. Grouping process generates consistent, reproducible results for the same input data
**Plans**: 4 plans

Plans:
- [x] 08-04-PLAN.md — 配置系统集成与配置文件创建
- [x] 08-05-PLAN.md — 存储格式修复与单条事件过滤移除
- [x] 08-05a-PLAN.md — 持久化方法实现（save/load）
- [x] 08-06-PLAN.md — 自动备份与过期清理机制实现

### Phase 9: Pipeline Integration & Publishing Workflow
**Goal**: Integrate grouping into processing pipeline and ensure reliable dual-file publishing
**Depends on**: Phase 8
**Requirements**: GRP-03, STOR-02, INT-01, INT-02, INT-03
**Success Criteria** (what must be TRUE):
  1. EventGrouper runs after AI processing stage in main pipeline
  2. Incremental updates work correctly - new articles are added to existing groups or create new groups
  3. Dual-file atomic write ensures news_data.json and event_groups.json are always consistent
  4. GitHub Pages publishing process deploys both files correctly
**Plans**: 6 plans

Plans:
- [x] 09-01-PLAN.md — Write test cases for all integration scenarios
- [x] 09-02-PLAN.md — Integrate EventGrouper into publisher with incremental update and cleanup logic
- [x] 09-03-PLAN.md — Implement dual-file atomic write for data consistency
- [x] 09-04-PLAN.md — Update GitHub Pages publishing to include event_groups.json
- [x] 09-05-PLAN.md — End-to-end automated testing
- [x] 09-06-PLAN.md — Human verification checkpoint

### Phase 10: Frontend Event Timeline Display
**Goal**: Deliver event timeline presentation and maintain existing user experience
**Depends on**: Phase 9
**Requirements**: UI-01, UI-02, UI-03
**Success Criteria** (what must be TRUE):
  1. Same event news are aggregated and displayed as chronological timelines
  2. Users can still view individual news items without grouping
  3. All existing filter and sort functions work correctly with grouped events
  4. Frontend loads and renders performance is not significantly degraded
**Plans**: 6 plans
**UI hint**: yes

Plans:
- [x] 10-01-PLAN.md — Test scaffolding for frontend event functionality
- [x] 10-02-PLAN.md — Admin backend /api/events endpoint implementation
- [x] 10-03-PLAN.md — Admin frontend event timeline view
- [x] 10-04-PLAN.md — Public frontend event data integration
- [x] 10-05-PLAN.md — Public frontend event timeline enhancement
- [x] 10-06-PLAN.md — End-to-end testing and verification

### Phase 11: Event Table Refactor
**Goal**: 将事件时间线展示改为表格样式，与新闻列表视觉风格统一，支持展开/折叠多新闻事件
**Depends on**: Phase 10
**Requirements**: UI-01
**Success Criteria** (what must be TRUE):
  1. 事件列表以表格形式展示，列结构与新闻列表一致
  2. 单条新闻事件直接显示数据，无展开按钮
  3. 多条新闻事件显示展开按钮，点击后展开显示竖线连接的时间线
  4. 事件行显示主新闻的摘要、扩展性和更新时间
  5. 勾选框针对整个事件级别，选中即选中该事件下所有新闻
**Plans**: 3 plans
**UI hint**: yes

Plans:
- [x] 11-01-PLAN.md — Backend API updates to include summary/expansion fields
- [x] 11-02-PLAN.md — Admin frontend event table implementation
- [x] 11-03-PLAN.md — Public frontend event table integration

### Phase 12: UX 体验优化
**Goal**: 优化前端交互体验，统一UI风格，提升表格操作效率
**Depends on**: Phase 11
**Requirements**: UX-01, UX-02, UX-03, UX-04
**Success Criteria** (what must be TRUE):
  1. 扩展性字段默认显示2行，hover展开完整内容，不挤占表格空间
  2. 热点事件表格支持表头点击排序，显示升/降序指示符
  3. 事件视图显示完整顶部工具栏，支持全选、复制选中、排序功能
  4. 筛选控件样式与整体深色主题统一，交互效果一致
**Plans**: 4 plans
**UI hint**: yes

Plans:
- [x] 12-01-PLAN.md — 扩展性字段显示优化（2行截断+hover展开）
- [x] 12-02-PLAN.md — 热点事件表格表头点击排序功能
- [x] 12-03-PLAN.md — 事件表格顶部工具栏功能（排序+复制选中）
- [x] 12-04-PLAN.md — 筛选控件样式优化，与整体风格统一

### Phase 13: 事件展示与实体识别优化
**Goal**: 优化事件表格显示体验，调整实体识别流程顺序，统一事件行高度约束
**Depends on**: Phase 12
**Requirements**: UI-04, AI-01
**Success Criteria** (what must be TRUE):
  1. 事件追踪表格中显示消息源链接，单新闻事件显示该新闻链接，多新闻事件显示主事件链接
  2. 实体识别流程调整到生成标题摘要之前执行，只对英文原文进行实体识别
  3. 每个事件条目的整体高度由标题决定，实体、链接、扩展性内容超出标题高度时自动折叠，所有行高度保持一致
**Plans**: 3 plans planned
**UI hint**: yes

Plans:
- [x] 13-01-PLAN.md — 后端API添加main_news_url + 前端表格添加链接列
- [x] 13-02-PLAN.md — AI处理流水线调整 - 实体识别前置到标题生成之前
- [x] 13-03-PLAN.md — 统一行高约束 - 实体列、扩展性列、链接列统一截断样式

### Phase 14: 前端新闻表格统一化优化
**Goal**: 统一新闻列表和事件表格的行高约束，统一链接展示样式，修复实体列高度显示问题
**Depends on**: Phase 13
**Requirements**: UX-05, UX-06, UI-05
**Success Criteria** (what must be TRUE):
  1. 新闻列表每条行高度由标题高度决定，摘要、实体、扩展性列超出限制自动截断，所有新闻行高度保持一致
  2. 事件追踪列表的链接列显示消息来源名称（域名），而不是固定的"链接"文字，更易识别
  3. 实体列高度限制与链接列、扩展性列保持一致，都是最多显示到标题高度，不会只显示一半
**Plans**: 3 plans planned
**UI hint**: yes

Plans:
- [ ] 14-01-PLAN.md — 新闻列表行高统一约束优化
- [x] 14-02-PLAN.md — 事件表格链接显示来源域名
- [x] 14-03-PLAN.md — 实体列高度显示问题修复

## Progress Table
| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Data Layer Stability | 2/2 | Completed | 2026-03-31 |
| 2. Core AI Topic Processing | 3/3 | Completed | 2026-04-01 |
| 3. AI Enhancement & Calibration | 3/3 | Completed | 2026-04-01 |
| 4. Source Management & Access Control | 3/3 | Completed | 2026-04-01 |
| 5. Scheduling & Incremental Updates | 2/2 | Completed | 2026-04-01 |
| 6. Web UI & Editorial Interaction | 1/1 | Completed | 2026-04-01 |
| 7. Cleanup Existing Merge Logic | 1/1 | Completed | 2026-04-02 |
| 8. EventGrouper Core Component Development | 4/4 | Completed | 2026-04-02 |
| 9. Pipeline Integration & Publishing Workflow | 6/6 | Completed | 2026-04-02 |
| 10. Frontend Event Timeline Display | 6/6 | Completed | 2026-04-02 |
| 11. Event Table Refactor | 3/3 | Completed | 2026-04-02 |
| 12. UX 体验优化 | 4/4 | Completed | 2026-04-02 |
| 13. 事件展示与实体识别优化 | 3/3 | Completed | 2026-04-03 |
| 14. 前端新闻表格统一化优化 | 2/3 | In Progress|  |
