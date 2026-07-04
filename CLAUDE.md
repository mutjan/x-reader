<!-- GSD:project-start source:PROJECT.md -->
## Project

**科技新闻选题聚合系统**

一个面向内部编辑的科技新闻选题聚合系统，自动从RSS源获取科技新闻，通过AI评估筛选高价值选题，按领域和热度分类展示，帮助编辑团队快速发现优质报道线索。

**Core Value:** **自动发现高价值科技选题，降低编辑信息搜集成本，提升选题效率和质量。**
<!-- GSD:project-end -->

<!-- GSD:stack-start source:codebase/STACK.md -->
## Technology Stack

## Languages
- Python 3.x (3.7+) - Used for all backend logic, processing pipelines, and web interface
- HTML/JavaScript - Used for frontend `index.html`
## Runtime
- Python 3.x
- pip
- Lockfile: Missing (only `requirements.txt` present)
## Frameworks
- Flask >=3.0.0 - Web administration interface
- Not detected
- Not detected (uses standard Python tooling)
## Key Dependencies
- requests >=2.31.0 - Network requests for fetching RSS/API content
- beautifulsoup4 >=4.12.0 - HTML content parsing and extraction
- pydantic >=2.5.0 + pydantic-settings >=2.1.0 - Configuration validation and management
- python-dateutil >=2.8.2 - Date and time processing
- tenacity >=8.2.3 - Retry logic for network operations
- Git CLI - Used for GitHub Pages publishing
## Configuration
- Configured via pydantic-settings with environment variable override support
- Key environment variables required: `GITHUB_TOKEN`, `INOREADER_CLIENT_ID`, `INOREADER_CLIENT_SECRET`
- Main config file: `src/config/settings.py`
- No build process (Python interpreted, static HTML frontend)
## Platform Requirements
- Python 3.7+
- pip package manager
- Git CLI
- Processing scripts: Any Python 3 supported environment
- Frontend: GitHub Pages hosting
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

## Naming Patterns
- Lowercase with underscores (snake_case) pattern
- Examples: `ai_processor.py`, `news.py`, `github_pages.py`
- Lowercase with underscores (snake_case) pattern
- Examples: `get_unique_id()`, `build_prompt()`, `to_frontend_dict()`
- Lowercase with underscores (snake_case) pattern
- Examples: `normalized_url`, `content_hash`, `entity_mappings`
- PascalCase (upper camel case) pattern
- Examples: `RawNewsItem`, `ProcessedNewsItem`, `BaseAIProcessor`
## Code Style
- Not detected (no prettier/black config found)
- Observed 4-space indentation, consistent line breaks
- Not detected (no flake8/pylint/ruff config found)
## Import Organization
- Example from `src/processors/ai_processor.py`:
- No aliases used, full relative paths from project root
## Error Handling
- Limited explicit error handling observed
- Uses return values and default fallbacks where appropriate
## Logging
- Logger initialized at module level with module name as identifier
- Example: `logger = setup_logger("ai_processor")`
## Comments
- Module-level docstring at top of every file describing purpose
- Class docstrings describing class responsibility
- Method docstrings describing purpose, parameters, return values
- Inline comments for non-obvious business logic
- Not applicable (Python project, uses reST-style docstrings in triple quotes)
## Function Design
## Module Design
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

## Pattern Overview
- Linear processing pipeline with distinct stages
- Factory pattern for fetchers and publishers to support multiple data sources and output targets
- Two-step AI processing workflow (prompt generation + manual result import) to avoid LLM API costs and provide full control
- Abstract base classes for all core components to enable easy extension
## Layers
- Purpose: Retrieve raw news content from external sources
- Location: `src/fetchers/`
- Contains: Base fetcher interface, implementation for each data source, factory to instantiate fetchers
- Depends on: External APIs (Twitter, Inoreader), `src/models/news.py` data models
- Used by: Main pipeline orchestration
- Purpose: Transform and enhance raw news data
- Location: `src/processors/`
- Contains: Duplicate remover, content filter, AI processor, zeitgeist analyzer
- Depends on: `src/models/news.py`, utility functions
- Used by: Main pipeline orchestration
- Purpose: Define standardized data structures for raw and processed news
- Location: `src/models/`
- Contains: RawNewsItem, ProcessedNewsItem data classes and serialization logic
- Depends on: No internal dependencies
- Used by: All layers
- Purpose: Export processed news to output targets
- Location: `src/publishers/`
- Contains: Base publisher interface, implementation for each output target, factory to instantiate publishers
- Depends on: `src/models/news.py`, external services (GitHub Pages)
- Used by: Main pipeline orchestration
- Purpose: Provide user interface for interacting with the system
- Location: `src/web/`
- Contains: Flask web application, templates
- Depends on: Processors, Models layers
- Used by: End users via browser
## Data Flow
- Stateless pipeline processing with all state persisted to disk
- Processed item IDs are stored to avoid reprocessing across runs
- Temporary files are used for AI prompt/result exchange between system and user
## Key Abstractions
- Purpose: Standard interface for all data source fetchers
- Examples: `src/fetchers/base.py`, `src/fetchers/twitter_fetcher.py`, `src/fetchers/inoreader_fetcher.py`
- Pattern: Abstract base class with `test_connection()` and `fetch()` methods
- Purpose: Standard interface for all output publishers
- Examples: `src/publishers/base.py`, `src/publishers/github_pages.py`
- Pattern: Abstract base class with `publish()` method
- Purpose: Standard interface for AI processing implementations
- Examples: `src/processors/ai_processor.py`
- Pattern: Abstract base class with `process_batch()` method, supporting both manual and automated LLM workflows
## Entry Points
- Location: `main.py`
- Triggers: Invoked from command line with parameters
- Responsibilities: Orchestrate the entire processing pipeline, handle command line arguments, coordinate all components
- Location: `src/web/app.py`
- Triggers: Invoked via web server, accessed by users through browser
- Responsibilities: Provide user interface for viewing news, managing processing workflow
## Error Handling
- Each stage validates input and returns early with clear logging if no items remain
- Comprehensive logging at each step for debugging
- JSON validation before publishing to ensure output consistency
## Cross-Cutting Concerns
<!-- GSD:architecture-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd:quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd:debug` for investigation and bug fixing
- `/gsd:execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd:profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
