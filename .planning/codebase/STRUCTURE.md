# Codebase Structure

**Analysis Date:** 2026-03-31

## Directory Layout

```
/Users/lzw/Documents/LobsterAI/lzw/x-reader/
├── .planning/          # Planning and documentation for the project
│   └── codebase/       # Codebase analysis documents
├── config/             # Configuration files for the application
├── logs/               # Application log files
├── scripts/            # Helper scripts for manual operations
├── src/                # Main source code
│   ├── config/         # Application settings and configuration loading
│   ├── fetchers/       # Data source fetchers implementation
│   ├── models/         # Data models and serialization
│   ├── processors/     # Data processing logic
│   ├── publishers/     # Output publisher implementations
│   ├── utils/          # Shared utility functions
│   └── web/            # Web application code
│       └── templates/  # HTML templates for web UI
└── main.py             # Main CLI entry point
```

## Directory Purposes

**src/fetchers:**
- Purpose: Implementations for each data source
- Contains: Base fetcher interface, factory, Twitter fetcher, Inoreader fetcher
- Key files: `src/fetchers/base.py`, `src/fetchers/factory.py`, `src/fetchers/twitter_fetcher.py`, `src/fetchers/inoreader_fetcher.py`

**src/processors:**
- Purpose: Core business logic for processing news items
- Contains: Duplicate removal, content filtering, AI processing, zeitgeist analysis
- Key files: `src/processors/duplicate.py`, `src/processors/filter.py`, `src/processors/ai_processor.py`, `src/processors/zeitgeist.py`

**src/models:**
- Purpose: Data structure definitions
- Contains: RawNewsItem and ProcessedNewsItem data classes
- Key files: `src/models/news.py`

**src/publishers:**
- Purpose: Output target implementations
- Contains: Base publisher interface, factory, GitHub Pages publisher
- Key files: `src/publishers/base.py`, `src/publishers/factory.py`, `src/publishers/github_pages.py`

**src/utils:**
- Purpose: Shared helper functions used across the codebase
- Contains: Logging setup, common helper functions, authentication utilities
- Key files: `src/utils/common.py`, `src/utils/auth.py`

**src/web:**
- Purpose: Web user interface
- Contains: Flask application, HTML templates
- Key files: `src/web/app.py`

## Key File Locations

**Entry Points:**
- `main.py`: Command line interface for running the full processing pipeline
- `src/web/app.py`: Web application entry point

**Configuration:**
- `config/zeitgeist.json`: Zeitgeist configuration for trend analysis
- `src/config/settings.py`: Application settings and environment variable loading

**Core Logic:**
- `src/processors/ai_processor.py`: AI prompt generation and result parsing logic
- `src/models/news.py`: Data model definitions for all news items

**Testing:**
- Test files not detected in current codebase

## Naming Conventions

**Files:**
- Pattern: Snake_case, descriptive names with suffix indicating type
- Example: `twitter_fetcher.py`, `ai_processor.py`, `duplicate.py`

**Directories:**
- Pattern: Plural nouns for category directories, singular for specific implementations
- Example: `fetchers/`, `processors/`, `models/`

## Where to Add New Code

**New Feature:**
- Primary code: `src/processors/` if it's processing logic, `src/[layer]/` as appropriate
- Tests: To be determined (no test directory structure exists yet)

**New Data Source:**
- Implementation: `src/fetchers/[name]_fetcher.py`
- Register in: `src/fetchers/factory.py`

**New Output Target:**
- Implementation: `src/publishers/[name]_publisher.py`
- Register in: `src/publishers/factory.py`

**Utilities:**
- Shared helpers: `src/utils/[module].py`

## Special Directories

**logs/:**
- Purpose: Application log files from each run
- Generated: Yes
- Committed: No

**config/:**
- Purpose: Configuration files that can be modified without changing code
- Generated: No (manually edited)
- Committed: Yes (except for sensitive environment config)

**scripts/:**
- Purpose: One-off and manual operation scripts
- Generated: No (manually added)
- Committed: Yes

---

*Structure analysis: 2026-03-31*
