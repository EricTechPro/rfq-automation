# RFQ Automation

Automated government procurement lead scraper with 4 data sources, LLM-powered email automation, and n8n workflow integration.

## What It Does

Scrapes government RFQ (Request for Quote) opportunities from multiple sources, discovers supplier contacts, and automates email outreach — all orchestrated through n8n workflows that push data to Google Sheets.

## Data Sources

| Source | Type | Method |
|--------|------|--------|
| **DIBBS** (DLA Internet Bid Board) | US military parts RFQs | Playwright browser scraping |
| **SAM.gov** | US federal contract opportunities | Playwright browser scraping |
| **Canada Buys** | Canadian federal tenders | CSV feed + HTTP fallback |
| **Alberta Purchasing** | Alberta provincial procurement | JSON API |

## Architecture

```
n8n Workflows (daily cron)
    |
    v
FastAPI REST API (Railway)  -->  Google Sheets
    |
    +-- Scrapers (Playwright / httpx)
    +-- Contact Discovery (Firecrawl)
    +-- LLM (OpenRouter / Gemini Flash)
    +-- Document Intelligence (PDF extraction)
```

**Deployment:** Railway (`https://web-production-d9a0e.up.railway.app`)

## Quick Start

```bash
# Install dependencies
pip3 install -r requirements.txt
python3 -m playwright install chromium

# Configure environment
cp .env.example .env
# Edit .env with your API keys

# Start the API server
uvicorn api:app --host 0.0.0.0 --port 8000
# Docs at http://localhost:8000/docs
```

## API Endpoints

All endpoints (except health) require `X-API-Key` header when `RFQ_API_KEY` is set.

### Scrapers (rate limited: 5 req/min)

| Endpoint | Description |
|----------|-------------|
| `POST /api/search-sam` | Search SAM.gov opportunities |
| `POST /api/search-canada-buys` | Search Canada Buys tenders |
| `POST /api/search-alberta-purchasing` | Search Alberta Purchasing |
| `POST /api/scrape-nsns-by-date` | Scrape DIBBS NSNs by date |
| `POST /api/scrape-nsn-suppliers` | Get supplier contacts for an NSN |
| `GET /api/available-dates` | List available DIBBS RFQ dates |
| `POST /api/batch` | Batch process NSNs (DIBBS + WBParts + contacts) |
| `POST /api/extract-document` | Download and parse PDF bid packages |

### LLM (rate limited: 20 req/min)

| Endpoint | Description |
|----------|-------------|
| `POST /api/classify-thread` | Classify email thread stage |
| `POST /api/draft-reply` | Draft context-aware reply |
| `POST /api/extract-quote` | Extract quote data from text |

### Normalize

| Endpoint | Description |
|----------|-------------|
| `POST /api/normalize-leads` | Scrape + normalize to unified schema |
| `POST /api/normalize-raw` | Normalize pre-fetched data |

### Health

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Service health with LLM/Firecrawl/Playwright checks |

## n8n Workflows

See **[n8n/README.md](n8n/README.md)** for import guide and setup instructions.

8 workflows:
1. **Dedup & Append** — Utility sub-workflow for deduplication before sheet append
2. **DIBBS Daily** — Scrapes DIBBS NSNs by date, discovers supplier contacts
3. **SAM.gov Daily** — Scrapes SAM.gov federal contract opportunities
4. **Canada Buys Daily** — Scrapes Canadian federal tenders
5. **Alberta Daily** — Scrapes Alberta provincial procurement
6. **Document Pipeline** — Webhook-triggered PDF extraction
7. **Email Monitor** — IMAP polling + LLM classification
8. **Email Outreach** — Automated reply drafting + SMTP sending

## CLI

```bash
# Process NSNs from file (with resume capability)
python3 cli.py --file nsns.txt

# Start fresh
python3 cli.py --file nsns.txt --force

# Process specific NSNs
python3 cli.py --nsns "5306003733291,6685011396216"
```

## Environment Variables

```env
# Required for contact discovery
FIRECRAWL_API_KEY=fc-your-key

# Required for LLM features (email classification, reply drafting)
OPENROUTER_API_KEY=sk-or-your-key

# API authentication (optional — disabled if not set)
RFQ_API_KEY=your-secret-key

# Logging level (default: INFO)
LOG_LEVEL=INFO
```

See `.env.example` for the full list.

## Project Structure

```
rfq-automation/
├── api.py                          # FastAPI REST API (11 endpoints)
├── core.py                         # Shared business logic
├── cli.py                          # CLI with resume capability
├── config.py                       # Config loader (.env + Streamlit secrets)
├── models.py                       # Pydantic models (camelCase aliases)
├── run.py                          # Railway entrypoint (PORT handling)
├── scrapers/
│   ├── dibbs.py                    # DIBBS NSN detail scraper
│   ├── dibbs_date.py               # DIBBS date-based listing scraper
│   ├── sam_gov.py                  # SAM.gov opportunity scraper
│   ├── canada_buys.py              # Canada Buys CSV/HTML scraper
│   ├── alberta_purchasing.py       # Alberta Purchasing API client
│   ├── wbparts.py                  # WBParts manufacturer scraper
│   └── browser_pool.py            # Shared Playwright browser pool (FastAPI)
├── services/
│   ├── llm.py                      # OpenRouter LLM client
│   ├── firecrawl.py                # Firecrawl contact discovery
│   ├── normalizer.py               # Unified lead schema normalizer
│   └── document.py                 # PDF download + text extraction
├── utils/
│   ├── helpers.py                  # NSN formatting, file I/O
│   └── logging.py                  # Structured JSON logging
├── n8n/
│   ├── README.md                   # Workflow import guide
│   └── workflow-*.json             # n8n workflow definitions
├── Dockerfile                      # Railway deployment (Playwright base)
└── requirements.txt
```

## License

MIT
