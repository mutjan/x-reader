# Research Summary: 科技新闻选题聚合系统
**Synthesized:** 2026-03-31
**Based on:** STACK.md, FEATURES.md, ARCHITECTURE.md, PITFALLS.md

## Executive Summary
This is an internal tech news topic aggregation system for editorial teams, built as an extension of the existing x-reader codebase rather than a greenfield project. The recommended approach leverages mature, compatible Python ecosystem tools and modularly extends the existing pipeline architecture, minimizing rewrite risk while reusing proven core capabilities (RSS fetching, deduplication, AI processing). The core value proposition is AI-powered multi-dimensional topic evaluation, classification, and auto-summarization to reduce editorial screening workload by 60%+ while improving hotspot capture timeliness.

Critical risks include unstable AI scoring consistency, loss of hotspot timeliness, and low-quality source content risks, all of which have targeted mitigation strategies tied to specific development phases. The MVP focuses on delivering core table-stakes features first, with advanced differentiator features deferred to v2 after core product validation and data accumulation.

## Key Findings
### From STACK.md
- **RSS parsing**: feedparser 6.0.11 (most mature Python RSS library, compatible with existing requests stack, no rewrite needed)
- **AI processing**: OpenAI SDK 1.30.5 + tiktoken 0.7.0 (seamless integration with existing AI workflow, precise token counting for cost control)
- **Semantic processing**: sentence-transformers 3.0.1 (industry standard for similarity calculation, 32% more accurate than keyword matching for deduplication/clustering)
- **Backend admin**: Flask-Admin 3.0.1 + Flask-SQLAlchemy 3.1.1 (native Flask 3.x support, auto-generates CRUD interfaces, 60% faster development than custom UI)
- **Frontend**: HTMX 2.0.1 + Bulma CSS 1.0.0 (no JavaScript build process, 50% higher development efficiency for internal tools compared to React/Vue)
- All new dependencies are compatible with the existing x-reader tech stack, no major refactoring required.

### From FEATURES.md
#### Must-have (Table Stakes)
- Multi-source RSS aggregation and auto-deduplication (reuse existing functionality)
- Multi-dimensional topic value scoring (heat, novelty, domain match, timeliness)
- Intelligent domain classification and tag generation
- Auto news summary generation
- Multi-dimensional filtering/sorting and topic marking
- Hourly auto content updates

#### Should-have (Differentiators, v2)
- Hotspot trend prediction
- Same-event news context linking
- Dynamic topic score adjustment
- Editor preference adaptive recommendation
- Team collaboration features
- Cross-tool export capability

#### Explicitly Avoid (Anti-features)
- Public-facing information site (keep as internal tool only)
- Content publishing functionality (only integrate with existing publishing systems via export)
- Social media content scraping (v1 focus solely on RSS sources)
- Complex user permission systems (basic access control only)
- Full-text content storage (only store metadata, link to original sources)
- AI writing functionality (focus exclusively on topic discovery)

### From ARCHITECTURE.md
- **Architecture pattern**: Modular pipeline extension, insert new topic processing layer between existing deduplication and AI processing stages without disrupting existing flows
- **Core components**:
  - Topic Evaluation Engine: Rule-based multi-dimensional scoring
  - Intelligent Classifier: Auto classification and tagging
  - Heat Calculator: Real-time heat calculation with time decay
  - Topic Storage: Persistence layer for all topic data
  - Editor Management Module: Source configuration, threshold adjustment, topic management
- **Key patterns**:
  - Pipeline embedding: Minimal disruption to existing mature workflows
  - Dual scoring: Weighted combination of rule-based scoring (stability) and AI scoring (semantic understanding)
- **Dependency order**: Data model extension → Evaluation engine → AI processing extension → Topic storage → Classifier → Web UI → Admin module

### From PITFALLS.md
#### Top 5 Critical/High-Impact Pitfalls + Mitigation
1. **AI scoring drift**: AI rating consistency deviates >30% from manual judgment → Mitigate with standardized benchmark datasets, layered rule logic, and manual feedback calibration loops
2. **Hotspot timeliness loss**: Hot events appear >2 hours late in system → Mitigate with tiered crawl frequencies (15min for high-priority sources), failure alerts, and priority processing for hot keywords
3. **Source quality control**: Low-quality source content rated as high-value → Mitigate with source whitelists, source grading and weighting, and AI evaluation incorporating source credibility dimension
4. **AI result mismatch**: AI outputs matched to wrong news entries → Mitigate with URL as primary matching key, list snapshots before AI processing, index matching only as fallback
5. **Entity normalization errors**: Same entity with different expressions not recognized → Mitigate with alias mapping library and manual feedback update loops

## Implications for Roadmap
### Suggested Phase Structure
#### Phase 1: Core Foundation (Weeks 1-2)
- **Rationale**: Resolve historical known issues and build base data structures first to avoid downstream rework
- **Delivers**: Extended data models, URL-based AI matching, content truncation fixes, improved deduplication
- **Features**: Core data layer stability, fixes for known historical bugs
- **Pitfalls to avoid**: AI result mismatch, content truncation information loss, duplicate content residue, temporary file leaks
- **Research flag**: No research needed, standard patterns and well-documented fixes for existing issues

#### Phase 2: AI Topic Engine (Weeks 3-4)
- **Rationale**: Build core value proposition of AI-powered topic evaluation
- **Delivers**: Rule-based scoring system, extended AI prompt templates, classification, auto-summary generation
- **Features**: All core AI table-stakes features
- **Pitfalls to avoid**: AI scoring drift, entity normalization errors, rule conflicts, classification errors, summary inaccuracy
- **Research flag**: Needs limited research to create 100+ labeled benchmark calibration dataset

#### Phase 3: Data Acquisition Enhancement (Weeks 5-6)
- **Rationale**: Ensure stable, high-quality input data before building user-facing features
- **Delivers**: Source management system, tiered crawling configuration, failure monitoring
- **Features**: Source whitelisting, quality grading, crawl reliability improvements
- **Pitfalls to avoid**: Source quality control failures, crawl failures without alerts
- **Research flag**: No research needed, standard RSS crawl patterns

#### Phase 4: Scheduling & Timeliness (Weeks 7-8)
- **Rationale**: Timeliness is critical for editorial use cases, must be implemented before UI release
- **Delivers**: Incremental updates, priority processing for hot content, monitoring alerts
- **Features**: Hourly auto-updates, 15min crawl frequency for high-priority sources, failure alerts
- **Pitfalls to avoid**: Hotspot timeliness loss
- **Research flag**: No research needed, standard cron/scheduling patterns

#### Phase 5: Web UI & Management (Weeks 9-10)
- **Rationale**: Deliver usable interface for editorial teams to validate core functionality
- **Delivers**: Topic listing, multi-dimensional filtering, topic marking, admin configuration, export functionality
- **Features**: All table-stakes UI features
- **Pitfalls to avoid**: Rule configuration errors
- **Research flag**: No research needed, standard Flask-Admin patterns

#### Phase 6: Advanced Features (v2, Post-MVP)
- **Rationale**: Build differentiators only after core product validation and sufficient data accumulation
- **Delivers**: Hotspot trend prediction, editor preference adaptation, team collaboration
- **Features**: All differentiator features
- **Pitfalls to avoid**: Premature optimization without user data
- **Research flag**: Needs significant research for ML models, requires post-launch data accumulation

## Confidence Assessment
| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All technologies are mature, fully compatible with existing stack, alternatives evaluated thoroughly |
| Features | MEDIUM | Based on editorial workflow domain knowledge, no external market validation but MVP scope tightly aligned with core user needs |
| Architecture | HIGH | Extends existing proven x-reader pipeline architecture, follows standard industry patterns, clear component boundaries |
| Pitfalls | HIGH | Based on actual historical project issues and real editorial team feedback, all critical pitfalls have concrete mitigation strategies |

### Gaps to Address
1. No labeled benchmark dataset for AI scoring calibration, needs manual creation during Phase 2
2. No existing entity alias mapping library, needs iterative construction based on real content
3. No historical user behavior data for personalization features, requires post-launch accumulation
4. No historical heat data for trend prediction models, requires at least 3 months of operation data before implementation

## Sources
Aggregated from all research files:
- Official library documentation (feedparser, OpenAI SDK, Flask-Admin, HTMX)
- Existing x-reader system architecture and codebase analysis
- Internal editorial team workflow research
- Historical project issue records
- Content tool industry best practices