# Architecture

**Analysis Date:** 2026-03-31

## Pattern Overview

**Overall:** Modular pipeline architecture with clear separation of concerns

**Key Characteristics:**
- Linear processing pipeline with distinct stages
- Factory pattern for fetchers and publishers to support multiple data sources and output targets
- Two-step AI processing workflow (prompt generation + manual result import) to avoid LLM API costs and provide full control
- Abstract base classes for all core components to enable easy extension

## Layers

**Fetchers Layer:**
- Purpose: Retrieve raw news content from external sources
- Location: `src/fetchers/`
- Contains: Base fetcher interface, implementation for each data source, factory to instantiate fetchers
- Depends on: External APIs (Twitter, Inoreader), `src/models/news.py` data models
- Used by: Main pipeline orchestration

**Processors Layer:**
- Purpose: Transform and enhance raw news data
- Location: `src/processors/`
- Contains: Duplicate remover, content filter, AI processor, zeitgeist analyzer
- Depends on: `src/models/news.py`, utility functions
- Used by: Main pipeline orchestration

**Models Layer:**
- Purpose: Define standardized data structures for raw and processed news
- Location: `src/models/`
- Contains: RawNewsItem, ProcessedNewsItem data classes and serialization logic
- Depends on: No internal dependencies
- Used by: All layers

**Publishers Layer:**
- Purpose: Export processed news to output targets
- Location: `src/publishers/`
- Contains: Base publisher interface, implementation for each output target, factory to instantiate publishers
- Depends on: `src/models/news.py`, external services (GitHub Pages)
- Used by: Main pipeline orchestration

**Web Layer:**
- Purpose: Provide user interface for interacting with the system
- Location: `src/web/`
- Contains: Flask web application, templates
- Depends on: Processors, Models layers
- Used by: End users via browser

## Data Flow

**Standard News Processing Flow:**

1. **Fetch**: Data sources are fetched using appropriate fetcher implementations, returning RawNewsItem objects
2. **Deduplicate**: Raw items are deduplicated using content hashing and ID tracking
3. **Filter**: Low-quality or irrelevant items are filtered out based on score thresholds
4. **AI Processing**: Filtered items are batched, prompts are generated for LLM processing, results are imported and parsed back to ProcessedNewsItem objects
5. **Post-Processing**: Processed items are deduplicated again and similar items are merged
6. **Validation**: Output format is validated to ensure consistency
7. **Publish**: Final results are published to configured targets (GitHub Pages)

**State Management:**
- Stateless pipeline processing with all state persisted to disk
- Processed item IDs are stored to avoid reprocessing across runs
- Temporary files are used for AI prompt/result exchange between system and user

## Key Abstractions

**Base Fetcher:**
- Purpose: Standard interface for all data source fetchers
- Examples: `src/fetchers/base.py`, `src/fetchers/twitter_fetcher.py`, `src/fetchers/inoreader_fetcher.py`
- Pattern: Abstract base class with `test_connection()` and `fetch()` methods

**Base Publisher:**
- Purpose: Standard interface for all output publishers
- Examples: `src/publishers/base.py`, `src/publishers/github_pages.py`
- Pattern: Abstract base class with `publish()` method

**Base AI Processor:**
- Purpose: Standard interface for AI processing implementations
- Examples: `src/processors/ai_processor.py`
- Pattern: Abstract base class with `process_batch()` method, supporting both manual and automated LLM workflows

## Entry Points

**CLI Entry Point:**
- Location: `main.py`
- Triggers: Invoked from command line with parameters
- Responsibilities: Orchestrate the entire processing pipeline, handle command line arguments, coordinate all components

**Web Entry Point:**
- Location: `src/web/app.py`
- Triggers: Invoked via web server, accessed by users through browser
- Responsibilities: Provide user interface for viewing news, managing processing workflow

## Error Handling

**Strategy:** Defensive programming with explicit error checking at each pipeline stage

**Patterns:**
- Each stage validates input and returns early with clear logging if no items remain
- Comprehensive logging at each step for debugging
- JSON validation before publishing to ensure output consistency

## Cross-Cutting Concerns

**Logging:** Centralized logger setup in `src/utils/common.py` used across all components
**Validation:** Content sanitization and format validation at multiple pipeline stages
**Authentication:** Configured via environment variables for external services (Twitter, Inoreader, GitHub)

---

*Architecture analysis: 2026-03-31*
