# 科技新闻选题聚合系统 Roadmap
**Version:** v1.0
**Last updated:** 2026-04-01
**Granularity:** Standard
**Coverage:** 18/18 requirements mapped

## Phases
- [x] **Phase 1: Data Layer Stability** - Resolve historical data consistency issues and build stable data foundation
- [x] **Phase 2: Core AI Topic Processing** - Implement core AI evaluation, classification, and summarization capabilities
- [x] **Phase 3: AI Enhancement & Calibration** - Add event association and score feedback calibration mechanisms
- [x] **Phase 4: Source Management & Access Control** - Implement source whitelist and internal access restriction
- [x] **Phase 5: Scheduling & Incremental Updates** - Implement hourly automatic updates and scheduled execution scripts
- [ ] **Phase 6: Web UI & Editorial Interaction** - Deliver complete editorial interaction interface

## Phase Details

### Phase 1: Data Layer Stability
**Goal**: Establish stable, consistent data foundation and resolve historical AI matching errors
**Depends on**: Nothing (first phase)
**Requirements**: DATA-01, DATA-02, DATA-03, DATA-04
**Success Criteria** (what must be TRUE):
  1. Multi-source RSS feeds are fetched and aggregated without data loss
  2. Duplicate news entries are automatically detected and removed before processing
  3. All news items use URL as unique primary key, no AI result mismatch errors occur
  4. Pre-processing list snapshots are persisted, AI input and output are always aligned
**Plans**: 2 plans

Plans:
- [x] 01-01-PLAN.md — URL normalization + snapshot generation + existing functionality validation
- [x] 01-02-PLAN.md — Strict URL matching + snapshot import + auto cleanup

### Phase 2: Core AI Topic Processing
**Goal**: Deliver core AI-powered topic evaluation and content processing capabilities
**Depends on**: Phase 1
**Requirements**: AI-01, AI-02, AI-03
**Success Criteria** (what must be TRUE):
  1. Every news item gets a multi-dimensional score (heat, novelty, domain match, timeliness)
  2. News is automatically classified into predefined technology subdomains with relevant tags
  3. Concise, accurate summaries are generated for all news items highlighting core content
**Plans**: 3 plans

Plans:
- [x] 02-01-PLAN.md — Integrate AI scoring into manual processing workflow
- [x] 02-02-PLAN.md — Implement import workflow for scoring results
- [x] 02-03-PLAN.md — Extend output schema and frontend integration

### Phase 3: AI Enhancement & Calibration
**Goal**: Add advanced AI processing and feedback calibration mechanisms
**Depends on**: Phase 2
**Requirements**: AI-04, AI-05
**Success Criteria** (what must be TRUE):
  1. Related news reports on the same event are automatically grouped into event timelines
  2. System supports manual feedback on AI scores to continuously improve evaluation accuracy
**Plans**: 3 plans

Plans:
- [x] 03-01-PLAN.md — Implement same-event news automatic grouping
- [x] 03-02-PLAN.md — Implement manual scoring feedback mechanism
- [x] 03-03-PLAN.md — Implement offline scoring calibration mechanism

### Phase 4: Source Management & Access Control
**Goal**: Ensure content quality and restrict access to internal users only
**Depends on**: Phase 1
**Requirements**: INFRA-03, INFRA-04
**Success Criteria** (what must be TRUE):
  1. Administrators can manage RSS source whitelist, add/remove/update sources
  2. System access is restricted to internal editorial team only, no public access
**Plans**: 3 plans

Plans:
- [x] 04-01-PLAN.md — 实现后台简单密码认证功能
- [x] 04-02-PLAN.md — 实现源管理后端API和抓取集成
- [x] 04-03-PLAN.md — 实现源管理前端页面

### Phase 5: Scheduling & Incremental Updates
**Goal**: Ensure news timeliness with automated hourly updates
**Depends on**: Phase 4
**Requirements**: INFRA-01, INFRA-02
**Success Criteria** (what must be TRUE):
  1. System provides executable scripts for scheduled execution by orchestration agents
  2. News data is updated incrementally every hour without full reprocessing overhead
**Plans**: 2 plans

Plans:
- [x] 05-01-PLAN.md — 优化增量更新逻辑，默认2小时时间窗口
- [x] 05-02-PLAN.md — 提供可执行脚本和操作说明文档

### Phase 6: Web UI & Editorial Interaction
**Goal**: Deliver complete usable interface for editorial teams to discover high-quality topics
**Depends on**: Phase 3, Phase 5
**Requirements**: UI-01, UI-02, UI-03, UI-04, UI-05
**Success Criteria** (what must be TRUE):
  1. Users can filter news by domain, heat, time, and rating (per D-01)
  2. Users can sort news by heat, time, and sources count (per D-04)
  3. News list displays all required information: title, summary, score, tags, source, time
  4. Filter and sort conditions are combined with AND logic and take effect in real time (per D-02, D-03)
  5. Filter and sort parameters are preserved during pagination
**Plans**: 1 plan
**UI hint**: yes

Plans:
- [ ] 06-01-PLAN.md — 实现筛选和排序功能，包含后端接口扩展和前端交互

## Progress Table
| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Data Layer Stability | 2/2 | Completed | 2026-03-31 |
| 2. Core AI Topic Processing | 3/3 | Completed | 2026-04-01 |
| 3. AI Enhancement & Calibration | 3/3 | Completed | 2026-04-01 |
| 4. Source Management & Access Control | 3/3 | Completed | 2026-04-01 |
| 5. Scheduling & Incremental Updates | 2/2 | Completed | 2026-04-01 |
| 6. Web UI & Editorial Interaction | 0/1 | Not started | - |
