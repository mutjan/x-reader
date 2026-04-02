# Architecture Patterns

**Domain:** 科技新闻选题聚合系统 - 同事件新闻分组功能
**Researched:** 2026-04-01
**Confidence:** HIGH (基于现有系统架构分析，所有修改均为非破坏性扩展)

## Recommended Architecture

### High-Level Integration Design
```
┌─────────────────────────────────────────────────────────────────┐
│                     Existing Processing Pipeline                 │
├─────────┬─────────┬──────────┬────────────┬─────────┬───────────┤
│  Fetch  │ Dedupe  │  Filter  │ AI Process │ Dedupe  │  Publish  │
│         │ (Raw)   │          │            │(Process)│           │
└─────────┴─────────┴──────────┴────────────┴─────────┴───────────┘
                                      │
                                      ▼
                        ┌─────────────────────────┐
                        │   Remove merge_similar  │
                        │   from deduplicate.py   │
                        └─────────────────────────┘
                                      │
                                      ▼
                        ┌─────────────────────────┐
                        │   New EventGrouper      │
                        │   (Standalone stage)    │
                        └─────────────────────────┘
                                      │
              ┌───────────────────────┴───────────────────────┐
              ▼                                               ▼
┌──────────────────────────────┐            ┌──────────────────────────────┐
│  news_data.json              │            │  event_groups.json           │
│  (Unchanged structure)       │            │  (New file)                  │
│  - All news items independent│            │  - event_id → list of news_ids│
│  - Each has event_id field   │            │  - Event metadata (title, etc)│
└──────────────────────────────┘            └──────────────────────────────┘
```

### Component Boundaries

| Component | Responsibility | Changes Required | Communicates With |
|-----------|---------------|------------------|-------------------|
| **Main Pipeline (main.py)** | Orchestrate processing flow | Modified: Remove merge_similar_news call, add event grouping stage | DuplicateRemover, EventGrouper, Publisher |
| **DuplicateRemover** | News deduplication | Modified: Remove merge_similar_news method entirely | RawNewsItem, ProcessedNewsItem |
| **EventGrouper** | Same-event news grouping | Refactored: Generate separate grouping file instead of embedding in news_data.json | ProcessedNewsItem, Event data model |
| **GitHubPagesPublisher** | Publish to GitHub Pages | Modified: Write separate event_groups.json, add to git commit | ProcessedNewsItem, EventGrouper |
| **ProcessedNewsItem** | Data model | No changes: Already has event_id field | All components |
| **Frontend** | Display news | Modified: Aggregate news by event_id and show as timeline | news_data.json, event_groups.json |

### Data Flow

1. **Processing Pipeline Flow:**
   ```
   Raw News → Fetch → Dedupe → Filter → AI Processing → Dedupe →
   → Event Grouping → [news_data.json] + [event_groups.json] → Publish
   ```

2. **Grouping Process:**
   - EventGrouper takes full list of processed news items
   - Groups similar news into events using entity + similarity matching
   - Assigns event_id to each grouped news item
   - Generates event_groups.json containing:
     ```json
     {
       "events": [
         {
           "event_id": "abc123",
           "title": "OpenAI releases GPT-5",
           "max_grade": "S",
           "max_score": 95,
           "news_ids": ["id1", "id2", "id3"],
           "start_time": "2026-04-01T00:00:00",
           "end_time": "2026-04-01T12:00:00",
           "entities": ["OpenAI", "GPT"],
           "news_count": 3
         }
       ],
       "last_updated": "2026-04-01T12:00:00"
     }
     ```

3. **Frontend Integration:**
   - Load both news_data.json and event_groups.json
   - Map news items to their respective events using event_id
   - Display events as aggregated timeline entries with all related news

## Patterns to Follow

### Pattern 1: Non-destructive Integration
**What:** Keep existing news_data.json structure 100% backward compatible
**When:** All changes to storage layer
**Rationale:** Avoid breaking existing frontend, API, and tooling that depend on the current format
**Example:**
```python
# No changes to news item storage structure
news_item.event_id = event.event_id  # Only add this field, keep rest unchanged
```

### Pattern 2: Separation of Concerns
**What:** Event grouping is a separate pipeline stage, not embedded in deduplication or publishing
**When:** Pipeline architecture
**Rationale:** Makes grouping logic independent, easier to test and modify without affecting other stages
**Example:**
```python
# In main.py, after deduplication
event_grouper = EventGrouper()
events = event_grouper.group_news(processed_items)
# Save events to separate file
event_grouper.save_events(events, EVENT_GROUPS_FILE)
```

### Pattern 3: Idempotent Grouping
**What:** Event IDs are stable across runs for the same set of news
**When:** Event generation logic
**Rationale:** Prevent event ID churn that would break frontend bookmarks and user interactions
**Implementation:** Hash of sorted news IDs in the event as the event ID

## Anti-Patterns to Avoid

### Anti-Pattern 1: Monolithic Grouping
**What:** Embedding grouping logic in the deduplication or publishing stages
**Why bad:** Creates tight coupling, makes testing and modification harder
**Instead:** Keep EventGrouper as an independent component with clear interface

### Anti-Pattern 2: Data Structure Changes
**What:** Modifying the existing news_data.json structure to include event data
**Why bad:** Breaks backward compatibility with all existing consumers
**Instead:** Use separate event_groups.json file and reference via event_id field

### Anti-Pattern 3: Full Regeneration on Every Run
**What:** Regenerating all event groups from scratch every pipeline run
**Why bad:** Causes event ID instability and unnecessary processing
**Instead:** Incremental grouping - only process new items against existing events

## Scalability Considerations

| Concern | At 100 users | At 10K users | At 1M users |
|---------|--------------|--------------|-------------|
| Grouping performance | O(n²) comparison acceptable | Add semantic hashing to reduce comparisons | Distributed grouping with vector databases |
| Storage size | Both files < 1MB | Compress historical data | Shard events by time range |
| Frontend rendering | Client-side aggregation fine | Paginate events | Server-side rendering of event timelines |
| Event consistency | Manual review sufficient | Add event merging rules | Automated conflict resolution |

## Changes Required vs New Components

### Modified Components
1. **main.py**
   - Remove call to `duplicate_remover.merge_similar_news()` at line 134
   - Add new EventGrouper stage after deduplication
   - Pass both news items and events to publisher

2. **src/processors/duplicate.py**
   - Remove `merge_similar_news()` method entirely
   - Remove all similar news merging logic
   - Keep only basic deduplication functionality

3. **src/publishers/github_pages.py**
   - Add event_groups.json path to configuration
   - Modify publish() method to write and commit both files
   - Remove event embedding in news_data.json

4. **src/processors/event_grouper.py**
   - Modify to return event -> news_id mappings instead of full news objects
   - Add save_events() method to write event_groups.json
   - Implement incremental grouping logic

### New Components
1. **Event Data Model** (in event_grouper.py)
   - Simplified event structure with only metadata and news_ids
   - No nested news objects in events

2. **Configuration**
   - Add EVENT_GROUPS_FILE path in settings.py

## Recommended Build Order

### Phase 1: Remove Merging Logic (Low Risk)
1. Remove `merge_similar_news` call from main.py
2. Delete the method from duplicate.py
3. Test pipeline still runs correctly and produces all news items

### Phase 2: Refactor EventGrouper (Medium Risk)
1. Modify EventGrouper to produce separate event structure with news_ids
2. Add event_groups.json path to settings
3. Implement save/load functionality for event groups
4. Test grouping logic produces correct mappings

### Phase 3: Integrate into Pipeline (Medium Risk)
1. Add EventGrouper stage to main.py after deduplication
2. Pass events to publisher
3. Modify publisher to write both files
4. Test both files are generated correctly and committed to GitHub

### Phase 4: Frontend Integration (High Risk)
1. Modify frontend to load both JSON files
2. Implement event aggregation and timeline display
3. Test backward compatibility with existing data
4. Gradual rollout with fallback to non-grouped view

## Sources

- Existing codebase analysis: main.py, duplicate.py, event_grouper.py, github_pages.py
- Project requirements: .planning/PROJECT.md v2.0 milestone
- Data model: src/models/news.py
- Configuration: src/config/settings.py
