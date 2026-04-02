# 科技新闻选题聚合系统 Roadmap
**Version:** v2.0
**Last updated:** 2026-04-01
**Granularity:** Standard
**Coverage:** 12/12 requirements mapped

## Phases
- [x] **Phase 1: Data Layer Stability** - Resolve historical data consistency issues and build stable data foundation
- [x] **Phase 2: Core AI Topic Processing** - Implement core AI evaluation, classification, and summarization capabilities
- [x] **Phase 3: AI Enhancement & Calibration** - Add event association and score feedback calibration mechanisms
- [x] **Phase 4: Source Management & Access Control** - Implement source whitelist and internal access restriction
- [x] **Phase 5: Scheduling & Incremental Updates** - Implement hourly automatic updates and scheduled execution scripts
- [x] **Phase 6: Web UI & Editorial Interaction** - Deliver complete editorial interaction interface
- [x] **Phase 7: Cleanup Existing Merge Logic** - Remove old similar news merge functionality and prepare for new grouping architecture (completed 2026-04-02)
- [ ] **Phase 8: EventGrouper Core Component Development** - Implement event grouping core logic and data model
- [ ] **Phase 9: Pipeline Integration & Publishing Workflow** - Integrate grouping into processing pipeline and dual-file publishing
- [ ] **Phase 10: Frontend Event Timeline Display** - Implement event timeline presentation and user interaction features

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
**Plans**: 3 plans

Plans:
- [ ] 08-01-PLAN.md — 配置系统与数据模型完善
- [ ] 08-02-PLAN.md — EventGrouper核心逻辑完善
- [ ] 08-03-PLAN.md — 自动备份机制实现

### Phase 9: Pipeline Integration & Publishing Workflow
**Goal**: Integrate grouping into processing pipeline and ensure reliable dual-file publishing
**Depends on**: Phase 8
**Requirements**: GRP-03, STOR-02, INT-01, INT-02, INT-03
**Success Criteria** (what must be TRUE):
  1. EventGrouper runs after AI processing stage in main pipeline
  2. Incremental updates work correctly - new articles are added to existing groups or create new groups
  3. Dual-file atomic write ensures news_data.json and event_groups.json are always consistent
  4. GitHub Pages publishing process deploys both files correctly
**Plans**: 3 plans

### Phase 10: Frontend Event Timeline Display
**Goal**: Deliver event timeline presentation and maintain existing user experience
**Depends on**: Phase 9
**Requirements**: UI-01, UI-02, UI-03
**Success Criteria** (what must be TRUE):
  1. Same event news are aggregated and displayed as chronological timelines
  2. Users can still view individual news items without grouping
  3. All existing filter and sort functions work correctly with grouped events
  4. Frontend loads and renders performance is not significantly degraded
**Plans**: 3 plans
**UI hint**: yes

## Progress Table
| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Data Layer Stability | 2/2 | Completed | 2026-03-31 |
| 2. Core AI Topic Processing | 3/3 | Completed | 2026-04-01 |
| 3. AI Enhancement & Calibration | 3/3 | Completed | 2026-04-01 |
| 4. Source Management & Access Control | 3/3 | Completed | 2026-04-01 |
| 5. Scheduling & Incremental Updates | 2/2 | Completed | 2026-04-01 |
| 6. Web UI & Editorial Interaction | 1/1 | Completed | 2026-04-01 |
| 7. Cleanup Existing Merge Logic | 1/1 | Complete   | 2026-04-02 |
| 8. EventGrouper Core Component Development | 0/0 | Not started | - |
| 9. Pipeline Integration & Publishing Workflow | 0/0 | Not started | - |
| 10. Frontend Event Timeline Display | 0/0 | Not started | - |
