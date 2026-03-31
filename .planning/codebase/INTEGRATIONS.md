# External Integrations

**Analysis Date:** 2026-03-31

## APIs & External Services

**Content Sources:**
- Twitter - Used to fetch Twitter timeline content via local RSS proxy
  - Endpoint: http://localhost:1200/twitter/home/...
  - SDK/Client: Custom fetcher (`src/fetchers/twitter_fetcher.py`)
  - Auth: None (uses local proxy)
- Inoreader - RSS reader API source for content aggregation
  - SDK/Client: Custom implementation
  - Auth: `INOREADER_CLIENT_ID`, `INOREADER_CLIENT_SECRET` environment variables

**Publishing:**
- GitHub - Used for hosting and publishing to GitHub Pages
  - SDK/Client: Git CLI integration
  - Auth: `GITHUB_TOKEN` environment variable
  - Implementation: `src/publishers/github_pages.py`

## Data Storage

**Databases:**
- None (no database server)
  - Storage: Local JSON files
  - Client: Custom JSON serialization/deserialization utilities

**File Storage:**
- Local filesystem only

**Caching:**
- None (uses `.processed_ids.json` file to track processed items and avoid reprocessing)

## Authentication & Identity

**Auth Provider:**
- Custom
  - Implementation: API key based authentication for external services only, no user authentication system

## Monitoring & Observability

**Error Tracking:**
- None

**Logs:**
- Standard Python logging to console, no centralized logging

## CI/CD & Deployment

**Hosting:**
- GitHub Pages for static frontend
- No dedicated application hosting (processing runs locally/manually)

**CI Pipeline:**
- None

## Environment Configuration

**Required env vars:**
- `GITHUB_TOKEN` - GitHub API access for publishing
- `INOREADER_CLIENT_ID` - Inoreader API client ID
- `INOREADER_CLIENT_SECRET` - Inoreader API client secret

**Secrets location:**
- Environment variables only, no dedicated secrets manager

## Webhooks & Callbacks

**Incoming:**
- None

**Outgoing:**
- None

---

*Integration audit: 2026-03-31*
