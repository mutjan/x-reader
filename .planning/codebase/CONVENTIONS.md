# Coding Conventions

**Analysis Date:** 2026-03-31

## Naming Patterns

**Files:**
- Lowercase with underscores (snake_case) pattern
- Examples: `ai_processor.py`, `news.py`, `github_pages.py`

**Functions:**
- Lowercase with underscores (snake_case) pattern
- Examples: `get_unique_id()`, `build_prompt()`, `to_frontend_dict()`

**Variables:**
- Lowercase with underscores (snake_case) pattern
- Examples: `normalized_url`, `content_hash`, `entity_mappings`

**Types/Classes:**
- PascalCase (upper camel case) pattern
- Examples: `RawNewsItem`, `ProcessedNewsItem`, `BaseAIProcessor`

## Code Style

**Formatting:**
- Not detected (no prettier/black config found)
- Observed 4-space indentation, consistent line breaks

**Linting:**
- Not detected (no flake8/pylint/ruff config found)

## Import Organization

**Order:**
1. Standard library imports (os, json, datetime, etc.)
2. Third-party package imports (requests, flask, pydantic, etc.)
3. Local module imports (src.models, src.utils, etc.)
- Example from `src/processors/ai_processor.py`:
  ```python
  from abc import ABC, abstractmethod
  from typing import List, Dict, Any, Optional
  import json
  import os

  from src.models.news import RawNewsItem, ProcessedNewsItem
  from src.utils.common import setup_logger
  ```

**Path Aliases:**
- No aliases used, full relative paths from project root

## Error Handling

**Patterns:**
- Limited explicit error handling observed
- Uses return values and default fallbacks where appropriate

## Logging

**Framework:** Custom logger from `src.utils.common.setup_logger()`
**Patterns:**
- Logger initialized at module level with module name as identifier
- Example: `logger = setup_logger("ai_processor")`

## Comments

**When to Comment:**
- Module-level docstring at top of every file describing purpose
- Class docstrings describing class responsibility
- Method docstrings describing purpose, parameters, return values
- Inline comments for non-obvious business logic

**JSDoc/TSDoc:**
- Not applicable (Python project, uses reST-style docstrings in triple quotes)

## Function Design

**Size:** Typically <50 lines, focused on single responsibility
**Parameters:** Type hints required for all function parameters and return values
**Return Values:** Explicit return statements, type annotated

## Module Design

**Exports:** Classes and functions exported directly, no barrel files
**Barrel Files:** Not used

---

*Convention analysis: 2026-03-31*
