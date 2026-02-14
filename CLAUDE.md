# CLAUDE.md

Developer guide for the RFQ Automation codebase.

## Project Overview

RFQ Automation is a Python tool that scrapes government/military part data (NSNs) from DIBBS (Defense Logistics Agency Internet Bid Board System) and WBParts, then discovers supplier contact information using the Firecrawl API. It has three interfaces: CLI, Streamlit web app, and FastAPI REST API.

## Common Commands

```bash
# Install dependencies
pip3 install -r requirements.txt
python3 -m playwright install chromium

# Run CLI batch processing
python3 cli.py --file nsns.txt --force        # Process all NSNs fresh
python3 cli.py --file nsns.txt                # Resume from last progress
python3 cli.py --nsns "5306003733291,6685011396216"

# Run Streamlit web app
streamlit run app.py                          # Launches at http://localhost:8501

# Run FastAPI server
uvicorn api:app --host 0.0.0.0 --port 8000   # API docs at http://localhost:8000/docs

# Unified entry point
python3 main.py api|cli|streamlit

# Run unit tests
pytest tests/test_data_validation.py -v

# Run live integration tests (requires Railway deployment)
pytest tests/test_api_live.py -v

# Run API contract tests
pytest tests/test_api_contracts.py -v

# Local dev: colored log output
LOG_FORMAT=pretty python3 main.py api
```

## Architecture

### Data Flow (Single NSN)
`core.scrape_nsn()` orchestrates the full pipeline:
1. **Scrape DIBBS + WBParts in parallel** (async) — gets approved sources, solicitations, manufacturers
2. **Discover contacts** via Firecrawl for each unique supplier (sequential with rate limiting)
3. **Build EnhancedRFQResult** combining all data

### Three Interfaces, One Core
All interfaces delegate to `core.py` for business logic:
- **`cli.py`** — Batch processor with resume capability, incremental CSV/JSON saves, progress bars
- **`app.py`** — Streamlit UI for single/batch NSN processing
- **`api.py`** — FastAPI REST endpoints including Phase 2 date-based scraping

### Key Modules

| Module | Purpose |
|--------|---------|
| `core.py` | Shared business logic: `scrape_nsn()`, `scrape_batch()`, result flattening |
| `models.py` | Pydantic models with camelCase aliases (`by_alias=True` for JSON output) |
| `config.py` | Config loader: checks Streamlit secrets first, then `.env` / env vars |
| `scrapers/dibbs.py` | Playwright-based DIBBS scraper (handles DoD consent banner) |
| `scrapers/dibbs_date.py` | Date-based NSN listing scraper with pagination |
| `scrapers/wbparts.py` | Playwright-based WBParts scraper |
| `scrapers/browser_pool.py` | Shared Playwright browser pool for FastAPI (limits concurrent pages) |
| `services/firecrawl.py` | Firecrawl API client: search for websites, extract contacts |
| `services/normalizer.py` | Unified lead schema normalizer for multi-source data |
| `services/document.py` | PDF download and text extraction from bid packages |
| `utils/helpers.py` | NSN formatting/validation, file I/O, timestamps |
| `utils/logging.py` | Structured JSON/pretty logging with correlation IDs |

### Pydantic Model Conventions
All models use `Field(alias="camelCase")` with `populate_by_name = True`. When constructing models, use camelCase kwargs (e.g., `companyName=...`). For JSON serialization, use `model_dump(by_alias=True, exclude_none=True)`.

### NSN Format
NSNs are 13-digit numbers in format `XXXX-XX-XXX-XXXX` (with dashes) or `XXXXXXXXXXXXX` (without). Use `format_nsn_with_dashes()` from `utils/helpers.py` for display and `format_nsn()` for raw digits.

### Contact Confidence Levels
- **HIGH**: email + phone + address + website (all 4 present)
- **MEDIUM**: at least phone number
- **LOW**: website only (filtered out by Phase 2 API endpoints)

See [docs/](docs/) for architecture diagrams, project status, and summary.

### Deployment
- **Railway** via Dockerfile (uses `run.py` as entrypoint to handle PORT env var)
- Docker base image: `mcr.microsoft.com/playwright/python:v1.49.1-noble` (Python 3.10)
- **Streamlit Cloud** limited: no Playwright support, so scraping doesn't work there
- Phase 2 API endpoints require `X-API-Key` header when `RFQ_API_KEY` env var is set

## Environment Variables

Required: `FIRECRAWL_API_KEY` (must start with `fc-`)
Optional: `OPENROUTER_API_KEY` (enables LLM features: email classification, reply drafting, quote extraction)
Optional: `RFQ_API_KEY` (enables API authentication for Phase 2 endpoints)
See `.env.example` for full list including timeouts, retry config, and rate limiting.

---

## Code Style Rules

- **Python 3.9+ compatibility required** (Docker uses 3.10, but keep 3.9-safe):
  - `List[dict]` not `list[dict]`, `Optional[X]` not `X | None`
  - No backslashes in f-string expressions (use a variable instead)
- **Import order:** stdlib -> third-party -> `sys.path.insert` hack -> local modules
- **Type annotations:** all public functions must have return types
- **Config access:** always `config.VAR` via the config singleton, never raw `os.getenv()`
- **Pydantic construction:** camelCase kwargs, serialize with `by_alias=True, exclude_none=True`
- **String formatting in logs:** use printf-style `%s` args, not f-strings (deferred evaluation)

## Async Rules

These prevent the most common bug class in this codebase:

- **NEVER** `time.sleep()` in async code -> use `await asyncio.sleep()`
- **NEVER** sync `requests.*` in async context -> use `httpx` or `asyncio.to_thread()`
- **NEVER** `asyncio.Semaphore()` at module level -> lazy-init inside the function (semaphores are bound to the event loop that creates them)

```python
# BAD: module-level semaphore breaks across event loops
_sem = asyncio.Semaphore(5)

# GOOD: lazy-init inside async function
_sem = None
async def do_work():
    global _sem
    if _sem is None:
        _sem = asyncio.Semaphore(5)
    async with _sem:
        ...
```

## Error Handling

- **NEVER** bare `except: pass` -> always log the error at minimum
- **Browser cleanup** MUST be in `finally` blocks; init variables (`browser = None`) before the `try`
- **Fail-safe defaults:** on error, choose the safe path (e.g., `is_excluded_domain` -> `True` on error to skip, not `False` to proceed)
- Catch specific exceptions first, use `Exception` as last resort
- Use `exc_info=True` kwarg for stack traces: `logger.error("msg", exc_info=True)`

## Logging Conventions

- Always `get_logger(__name__)` from `utils/logging.py`
- **NEVER** `logger.exception()` -> use `logger.error(..., exc_info=True)` (works with StructuredLogger)
- Use printf-style `%s` args for deferred formatting: `logger.info("Found %d items", count)`
- **Level guide:**
  - `DEBUG` = trace-level detail (request URLs, extraction attempts)
  - `INFO` = significant events (scrape complete, API request served)
  - `WARNING` = recoverable errors (retry, fallback used)
  - `ERROR` = failures requiring attention (scrape failed, API error)
- **CRITICAL:** production runs at INFO level — never log important errors at DEBUG

## Scraper Patterns

- **Dual-path pattern:** all scrapers accept `browser_context=None`
  - Pool path (FastAPI): receives context from `browser_pool.py`, creates page from it
  - Standalone path (CLI/Streamlit): launches own browser via `async_playwright()`
- **NEVER** spawn a browser per request in the API path -> use the shared pool
- **Page cleanup:** always `page.close()` in `try/finally`
- **Retry pattern:** exponential backoff with jitter, skip 4xx errors (they won't succeed on retry)
- **Shared helpers:** use `format_nsn()` and `format_nsn_with_dashes()` from `utils/helpers.py` — never duplicate locally

## Testing Conventions

- Class-based grouping (e.g., `TestNSNValidation`, `TestConfidenceLevels`)
- `@pytest.mark.slow` for live integration tests
- Always import and test the production function — never re-implement logic in tests
- No hardcoded secrets — use env vars via `conftest.py`
- Shared test constants belong in `tests/conftest.py`

## n8n Workflow Skills

This project has 8 n8n workflows (in `n8n/`) orchestrating daily scrapers, dedup, document pipeline, email monitor, and email outreach. Four project-level skills (`.claude/skills/`) provide n8n expertise:

| Skill | Slash Command | When to Use |
|-------|--------------|-------------|
| **n8n-workflow-patterns** | `/n8n-workflow-patterns` | Building new workflows, choosing architecture patterns (webhook, HTTP API, database, AI agent, scheduled tasks) |
| **n8n-workflow-architect** | `/n8n-workflow-architect` | Planning automation solutions, evaluating n8n vs Python, production-readiness decisions, tech stack integration |
| **n8n-mcp-tools-expert** | `/n8n-mcp-tools-expert` | Searching for n8n nodes, validating node configs, accessing templates, managing workflows via MCP tools |
| **n8n-workflow-testing-fundamentals** | `/n8n-workflow-testing-fundamentals` | Testing workflow execution, validating node connections, checking data flow, verifying error handling |

**Usage guidelines:**
- Use `/n8n-workflow-patterns` first when creating or modifying any `n8n/*.json` workflow — it has proven patterns for webhooks, HTTP integrations, and scheduled tasks
- Use `/n8n-workflow-architect` when deciding whether logic belongs in n8n or Python, or when planning new automation flows
- Use `/n8n-mcp-tools-expert` when you need to find the right n8n node for a task or validate node configuration
- Use `/n8n-workflow-testing-fundamentals` before deploying workflow changes — validate structure, data flow, and error paths
