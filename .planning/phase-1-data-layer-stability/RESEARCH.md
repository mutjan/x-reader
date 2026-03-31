# Phase 1: Data Layer Stability - Research

**Researched:** 2026-03-31
**Domain:** Data pipeline stability, unique key mechanism, snapshot persistence
**Confidence:** HIGH

## Summary

This research analyzes the existing x-reader codebase to identify gaps and implement requirements for a stable data foundation. The existing pipeline already implements multi-source fetching and deduplication, but suffers from AI result matching misalignment due to lack of snapshot persistence between prompt generation and result import.

**Primary recommendation:** Implement pre-processing list snapshot storage at prompt generation time, enforce URL-based primary key matching as the only matching mechanism (remove index fallback), and modify the import workflow to use the persisted snapshot instead of re-fetching data.

## User Constraints (from Requirements)

### Locked Decisions
1. Reuse existing x-reader functionality for fetching and deduplication
2. URL as unique primary key mechanism
3. Pre-processing list snapshot mechanism to ensure AI input/output consistency

### Out of Scope
- Rewriting existing fetching/deduplication logic
- Adding new data sources
- Changing AI processing business logic

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DATA-01 | Multi-source RSS news automatic fetching and aggregation | Existing functionality fully implemented in `main.py` and `src/fetchers/` |
| DATA-02 | Automatic news deduplication | Existing functionality fully implemented in `src/processors/duplicate.py` |
| DATA-03 | News URL unique primary key mechanism | Partial implementation exists, need to enforce URL as only matching key |
| DATA-04 | Pre-processing list snapshot mechanism | Not implemented, need to add snapshot storage/loading |

## Standard Stack
No new libraries required, all functionality can be implemented using existing dependencies:
- Python 3.x
- Pydantic (already used for config)
- JSON serialization (already used throughout codebase)

## Existing Code Analysis

### DATA-01: Multi-source Fetching (Already Working)
**Location:**
- `main.py` lines 54-80: Fetcher orchestration
- `src/fetchers/`: Twitter and Inoreader fetchers with factory pattern
- Each fetcher implements `test_connection()` and `fetch()` interface

**Current capabilities:**
- Supports Twitter and Inoreader sources
- Time window based fetching (default 24h)
- Connection testing before fetching
- Raw item aggregation across sources

### DATA-02: Automatic Deduplication (Already Working)
**Location:** `src/processors/duplicate.py`
- `deduplicate_raw()`: Raw item deduplication using normalized URL + title similarity
- `deduplicate_processed()`: Post-processing deduplication
- `merge_similar_news()`: Similar news merging with historical data comparison
- `is_processed()`: Checks against processed ID history to avoid reprocessing

**Current capabilities:**
- URL normalization before deduplication
- Title similarity threshold (0.8) for duplicate detection
- Historical processed ID tracking (up to 5000 entries)
- Similar news merging with entity overlap detection

### DATA-03: URL Unique Primary Key (Partial Implementation)
**Location:**
- `src/models/news.py` lines 23-34: `get_unique_id()` generates MD5 hash from normalized URL
- `src/processors/ai_processor.py` lines 148-166: Matching logic uses URL as primary, falls back to index
- `src/processors/ai_processor.py` lines 383-400: Same matching logic for scoring

**Issues found:**
1. **Fallback to index matching:** When URL match fails, the system falls back to index-based matching which causes misalignment when feed content changes between prompt generation and result import
2. **Re-fetch on import:** `scripts/import_results.py` re-runs the entire fetch/dedupe/filter pipeline when importing AI results, which can produce a different list than what was used to generate the prompt
3. **URL normalization consistency:** Normalization logic is duplicated in `duplicate.py` and `news.py`

### DATA-04: Pre-processing List Snapshot (Not Implemented)
**Current workflow gap:**
1. `main.py` generates AI prompt from filtered list but does not save the list
2. User runs import script later, which re-fetches data from sources
3. If feed updated in between, the filtered list is different, leading to index mismatch
4. No persisted state between prompt generation and result import

## Architecture Patterns

### Recommended Snapshot Structure
```json
{
  "snapshot_id": "uuid",
  "created_at": "2026-03-31T10:00:00",
  "time_window_hours": 24,
  "min_score": 10,
  "items": [
    {
      "url": "https://example.com/news/1",
      "unique_id": "md5_hash",
      "title": "News title",
      "content": "News content",
      "source": "Twitter",
      "published_at": "2026-03-30T14:30:00"
    }
  ]
}
```

### Snapshot Workflow Pattern
1. **Generation phase (main.py):** After pre-filtering, save snapshot to temp directory with unique ID, generate prompt from snapshot items
2. **Import phase (import_results.py):** Load snapshot instead of re-fetching, use snapshot items for AI result matching
3. **Matching enforcement:** Only use URL matching, remove index fallback entirely

### Anti-Patterns to Avoid
- **Re-fetching data during import:** This guarantees list mismatch when feeds update
- **Index-based matching:** Fragile to any changes in list ordering
- **Ephemeral state:** Not persisting the exact list used for prompt generation

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Unique ID generation | Custom hash functions | Existing `get_unique_id()` method | Already handles URL normalization and edge cases for missing URLs |
| Snapshot serialization | Custom binary formats | JSON serialization | Already used throughout codebase, human readable, easy to debug |
| List matching logic | Custom similarity matching | Direct URL exact matching | 100% accurate for the problem domain, no false matches |

## Common Pitfalls

### Pitfall 1: Feed content change between prompt and import
**What goes wrong:** News items are added/removed from feeds between prompt generation and result import, leading to index mismatch
**Why it happens:** Import script currently re-fetches data instead of using the original list
**How to avoid:** Persist the exact filtered list as a snapshot when generating the prompt
**Warning signs:** "URL matching failed, using index matching" warnings in logs

### Pitfall 2: URL normalization inconsistencies
**What goes wrong:** Same URL normalized differently in different parts of the system, leading to missed matches
**Why it happens:** Normalization logic duplicated in multiple files
**How to avoid:** Centralize URL normalization in a single utility function, use it consistently everywhere
**Warning signs:** Duplicate entries with same URL appearing in output

### Pitfall 3: Orphaned snapshot files
**What goes wrong:** Snapshot files accumulate in temp directory and consume disk space
**Why it happens:** No cleanup mechanism for old snapshots
**How to avoid:** Add automatic cleanup of snapshots older than 7 days, or let users manually delete them
**Warning signs:** Large number of `snapshot_*.json` files in temp directory

## Code Examples

### Snapshot Generation Example
```python
# In ManualProcessor.process_batch()
def process_batch(self, items: List[RawNewsItem]) -> List[ProcessedNewsItem]:
    if not items:
        return []

    # Generate snapshot
    snapshot = {
        "snapshot_id": hashlib.md5(str(datetime.now()).encode()).hexdigest()[:8],
        "created_at": datetime.now().isoformat(),
        "items": [
            {
                "url": item.url,
                "unique_id": item.get_unique_id(),
                "title": item.title,
                "content": item.content,
                "source": item.source,
                "published_at": item.published_at.isoformat()
            } for item in items
        ]
    }

    # Save snapshot
    snapshot_file = os.path.join(TEMP_DIR, f"snapshot_{snapshot['snapshot_id']}.json")
    save_json(snapshot, snapshot_file)

    # Generate prompt
    prompt = self.build_prompt(items)
    prompt_file = os.path.join(TEMP_DIR, f"ai_prompt_{snapshot['snapshot_id']}.txt")

    with open(prompt_file, 'w', encoding='utf-8') as f:
        f.write(prompt)

    logger.info(f"Generated snapshot: {snapshot_file}")
    logger.info(f"Generated prompt: {prompt_file}")
    logger.info("Use snapshot ID when importing results to ensure matching")

    return []
```

### Strict URL Matching Example
```python
# In parse_response() - remove index fallback entirely
def parse_response(self, response_text: str, original_items: List[RawNewsItem]) -> List[ProcessedNewsItem]:
    try:
        # ... existing JSON parsing logic ...

        # Build URL → item lookup for fast exact matching
        url_to_item = {item.url: item for item in original_items if item.url}

        processed_items = []
        for result in results:
            original_item = None
            original_url = result.get("original_url", "")

            # Only use URL exact match, no fallback
            if original_url and original_url in url_to_item:
                original_item = url_to_item[original_url]
            else:
                logger.error(f"No match found for URL: {original_url}")
                continue

            # ... rest of processing logic ...
    except:
        # ... existing error handling ...
```

## Environment Availability
All required dependencies are already available:
- Python 3.x: ✅
- JSON serialization: Built-in
- All existing project dependencies already installed

No additional dependencies required.

## Validation Architecture
### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (recommended, not yet configured) |
| Config file | none — see Wave 0 |
| Quick run command | `pytest tests/ -x` |
| Full suite command | `pytest tests/` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DATA-01 | Multi-source fetch works without data loss | integration | `pytest tests/test_fetchers.py -x` | ❌ Wave 0 |
| DATA-02 | Deduplication removes duplicate URLs and similar titles | unit | `pytest tests/test_duplicate.py -x` | ❌ Wave 0 |
| DATA-03 | URL matching correctly maps AI results to original items | unit | `pytest tests/test_ai_processor.py::test_url_matching -x` | ❌ Wave 0 |
| DATA-04 | Snapshot save/load produces identical list | unit | `pytest tests/test_snapshot.py -x` | ❌ Wave 0 |

### Wave 0 Gaps
- [ ] `tests/test_fetchers.py` — covers DATA-01
- [ ] `tests/test_duplicate.py` — covers DATA-02
- [ ] `tests/test_ai_processor.py` — covers DATA-03
- [ ] `tests/test_snapshot.py` — covers DATA-04
- [ ] pytest framework configuration

## Sources
### Primary (HIGH confidence)
- `/Users/lzw/Documents/LobsterAI/lzw/x-reader/main.py` — Pipeline flow
- `/Users/lzw/Documents/LobsterAI/lzw/x-reader/src/processors/duplicate.py` — Deduplication logic
- `/Users/lzw/Documents/LobsterAI/lzw/x-reader/src/processors/ai_processor.py` — AI processing and matching logic
- `/Users/lzw/Documents/LobsterAI/lzw/x-reader/src/models/news.py` — Data models and unique ID generation
- `/Users/lzw/Documents/LobsterAI/lzw/x-reader/scripts/import_results.py` — Import workflow

## Metadata
**Confidence breakdown:**
- Standard stack: HIGH — No new dependencies required
- Architecture: HIGH — Pattern validated by existing codebase and known industry practices
- Pitfalls: HIGH — Based on known historical issues documented in project memory

**Research date:** 2026-03-31
**Valid until:** 2026-04-30
