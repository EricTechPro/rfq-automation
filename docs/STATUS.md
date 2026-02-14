# Project Status: RFQ Automation

Automates government procurement (RFQ) workflows — scrapes solicitations from 4 portals, discovers supplier contacts, and handles email outreach — replacing a 3+ hour daily manual process.

See [Architecture Overview](ARCHITECTURE.md) for system diagrams.

**Tech stack:** Python 3.10 / FastAPI / Playwright / n8n / OpenRouter (Gemini Flash) / Firecrawl / Railway (Docker) / Google Sheets

## Current Status (Feb 13, 2026)

3-week roadmap in progress. See Updated Roadmap below.

### What's Live
- **3 of 4 scrapers running daily** — SAM.gov, Canada Buys, Alberta Purchasing push data to Google Sheet via n8n cron (1–4 AM)
- **Document pipeline** — PDF download + OCR extraction deployed on Railway
- **LLM endpoints** — classify-thread, draft-reply, extract-quote live on Railway (not yet wired to n8n)
- **Lead normalization** — all sources produce unified schema via `services/normalizer.py`

### Not Yet Started
- **Email inbox** — credentials received but not accessed; holding until DIBBS resolved and data validated
- **Email automation wiring** — n8n workflows exist but not connected to LLM endpoints or live inbox

## Blocker: DIBBS

DIBBS (`dibbs.bsm.dla.mil`) works locally but **fails on Railway** — the .mil site blocks cloud/datacenter IPs.

**Tried:** US West region migration, increased timeouts/retries (it's an IP block, not performance).

**Options:** residential proxy (most reliable), hybrid local/VPS approach, or alternative DLA data source.

## Updated Roadmap

| Week | Focus |
|------|-------|
| **Next Week** | Finalize DIBBS + Data Validation |
| **Week 2** | Email Bot — reading replies + AI drafting |
| **Week 3** | Full End-to-End Testing |

## Developer Quick Start

```bash
pip3 install -r requirements.txt && python3 -m playwright install chromium
cp .env.example .env   # fill in API keys
LOG_FORMAT=pretty uvicorn api:app --host 0.0.0.0 --port 8000
```

**Required env vars:** `FIRECRAWL_API_KEY` (contact discovery), `OPENROUTER_API_KEY` (LLM features), `RFQ_API_KEY` (API auth)

See [CLAUDE.md](../CLAUDE.md) for full developer guide — key modules, code conventions, async rules, scraper patterns, and all environment variables. See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed diagrams.

## Project History

| Date | Milestone |
|------|-----------|
| Dec 30, 2025 | Discovery call — manual RFQ process scoped |
| Jan 2, 2026 | Scoping call — NSN workflow defined, DIBBS + WBParts identified as sources |
| Jan 5, 2026 | Phase 1 kickoff — basic scraper built |
| Jan 12, 2026 | Phase 1 review — SAM.gov, Canada Buys, Alberta added |
| Jan 15, 2026 | Project paused — alignment issues |
| Jan 31, 2026 | Project resumed — Phase 2 kicked off |
| Feb 2, 2026 | Phase 2 scoping — email automation, document pipeline, multi-source expansion |
| Feb 4, 2026 | Bi-weekly sprint structure agreed (4 sprints) |
| Feb 9, 2026 | Unified lead schema designed — all sources normalized to one Sheet format |
| Feb 10, 2026 | Railway upgraded to Pro Plan, developer invited to workspace |
| Feb 11, 2026 | Migrated LLM from Azure OpenAI to OpenRouter (Gemini Flash) |
| Feb 12, 2026 | SAM.gov and DIBBS scrapers deployed; daily cron schedule set (1–4 AM) |
| Feb 13, 2026 | 3 of 4 scrapers live; DIBBS blocked by .mil IP filtering |
