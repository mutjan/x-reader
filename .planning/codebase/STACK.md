# Technology Stack

**Analysis Date:** 2026-03-31

## Languages

**Primary:**
- Python 3.x (3.7+) - Used for all backend logic, processing pipelines, and web interface

**Secondary:**
- HTML/JavaScript - Used for frontend `index.html`

## Runtime

**Environment:**
- Python 3.x

**Package Manager:**
- pip
- Lockfile: Missing (only `requirements.txt` present)

## Frameworks

**Core:**
- Flask >=3.0.0 - Web administration interface

**Testing:**
- Not detected

**Build/Dev:**
- Not detected (uses standard Python tooling)

## Key Dependencies

**Critical:**
- requests >=2.31.0 - Network requests for fetching RSS/API content
- beautifulsoup4 >=4.12.0 - HTML content parsing and extraction
- pydantic >=2.5.0 + pydantic-settings >=2.1.0 - Configuration validation and management
- python-dateutil >=2.8.2 - Date and time processing
- tenacity >=8.2.3 - Retry logic for network operations

**Infrastructure:**
- Git CLI - Used for GitHub Pages publishing

## Configuration

**Environment:**
- Configured via pydantic-settings with environment variable override support
- Key environment variables required: `GITHUB_TOKEN`, `INOREADER_CLIENT_ID`, `INOREADER_CLIENT_SECRET`
- Main config file: `src/config/settings.py`

**Build:**
- No build process (Python interpreted, static HTML frontend)

## Platform Requirements

**Development:**
- Python 3.7+
- pip package manager
- Git CLI

**Production:**
- Processing scripts: Any Python 3 supported environment
- Frontend: GitHub Pages hosting

---

*Stack analysis: 2026-03-31*
