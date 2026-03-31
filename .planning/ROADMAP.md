# 科技新闻选题聚合系统 Roadmap
**Version:** v1.0
**Last updated:** 2026-03-31
**Granularity:** Standard
**Coverage:** 18/18 requirements mapped

## Phases
- [ ] **Phase 1: Data Layer Stability** - Resolve historical data consistency issues and build stable data foundation
- [ ] **Phase 2: Core AI Topic Processing** - Implement core AI evaluation, classification, and summarization capabilities
- [ ] **Phase 3: AI Enhancement & Calibration** - Add event association and score feedback calibration mechanisms
- [ ] **Phase 4: Source Management & Access Control** - Implement source whitelist and internal access restriction
- [ ] **Phase 5: Scheduling & Incremental Updates** - Implement hourly automatic updates and scheduled execution scripts
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
- [ ] 01-01-PLAN.md — URL normalization + snapshot generation + existing functionality validation
- [ ] 01-02-PLAN.md — Strict URL matching + snapshot import + auto cleanup

### Phase 2: Core AI Topic Processing
**Goal**: Deliver core AI-powered topic evaluation and content processing capabilities
**Depends on**: Phase 1
**Requirements**: AI-01, AI-02, AI-03
**Success Criteria** (what must be TRUE):
  1. Every news item gets a multi-dimensional score (heat, novelty, domain match, timeliness)
  2. News is automatically classified into predefined technology subdomains with relevant tags
  3. Concise, accurate summaries are generated for all news items highlighting core content
**Plans**: TBD

### Phase 3: AI Enhancement & Calibration
**Goal**: Add advanced AI processing and feedback calibration mechanisms
**Depends on**: Phase 2
**Requirements**: AI-04, AI-05
**Success Criteria** (what must be TRUE):
  1. Related news reports on the same event are automatically grouped into event timelines
  2. System supports manual feedback on AI scores to continuously improve evaluation accuracy
**Plans**: TBD

### Phase 4: Source Management & Access Control
**Goal**: Ensure content quality and restrict access to internal users only
**Depends on**: Phase 1
**Requirements**: INFRA-03, INFRA-04
**Success Criteria** (what must be TRUE):
  1. Administrators can manage RSS source whitelist, add/remove/update sources
  2. System access is restricted to internal editorial team only, no public access
**Plans**: TBD

### Phase 5: Scheduling & Incremental Updates
**Goal**: Ensure news timeliness with automated hourly updates
**Depends on**: Phase 4
**Requirements**: INFRA-01, INFRA-02
**Success Criteria** (what must be TRUE):
  1. System provides executable scripts for scheduled execution by orchestration agents
  2. News data is updated incrementally every hour without full reprocessing overhead
**Plans**: TBD

### Phase 6: Web UI & Editorial Interaction
**Goal**: Deliver complete usable interface for editorial teams to discover and manage topics
**Depends on**: Phase 3, Phase 5
**Requirements**: UI-01, UI-02, UI-03, UI-04, UI-05
**Success Criteria** (what must be TRUE):
  1. Users can filter news by domain, heat, time, and score
  2. Users can sort news by heat, time, and score
  3. Users can mark news with "selected", "follow up", "ignore" statuses
  4. News list displays all required information: title, summary, score, tags, source, time
  5. Users can click news to jump to original source page
**Plans**: TBD
**UI hint**: yes

## Progress Table
| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Data Layer Stability | 0/2 | Not started | - |
| 2. Core AI Topic Processing | 0/3 | Not started | - |
| 3. AI Enhancement & Calibration | 0/2 | Not started | - |
| 4. Source Management & Access Control | 0/2 | Not started | - |
| 5. Scheduling & Incremental Updates | 0/2 | Not started | - |
| 6. Web UI & Editorial Interaction | 0/5 | Not started | - |
