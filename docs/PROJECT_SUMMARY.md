# RFQ Automation — Project Summary

Automated government procurement (RFQ) workflow that scrapes solicitations from 4 portals, discovers supplier contacts, and handles email outreach — replacing a 3+ hour daily manual process for defense contractor clients.

## Project Overview

A defense contractor manually processes aviation parts procurement through government bid boards. The daily workflow — checking open RFQs, finding approved manufacturers, locating contact information, and sending outreach emails — takes 3+ hours and limits throughput. This project automates the entire pipeline.

**Goal:** Scale daily NSN submissions with minimal manual intervention.

**Solution:** A FastAPI service (deployed on Railway) orchestrated by n8n workflows, scraping 4 government procurement portals, discovering supplier contacts via Firecrawl, and automating email outreach with LLM intelligence.

## Project Timeline

| Date | Milestone |
|------|-----------|
| Dec 30, 2025 | Discovery — manual RFQ process scoped |
| Jan 2, 2026 | Core workflow defined: NSN lookup → manufacturer discovery → contact extraction |
| Jan 5, 2026 | Working prototype reviewed; email automation and document extraction scoped |
| Jan 12, 2026 | DIBBS date-based listing discovered; scrape-by-date approach adopted |
| Jan 15, 2026 | Project paused for realignment |
| Jan 31, 2026 | Phase 2 kicked off |
| Feb 2, 2026 | Multi-source expansion: SAM.gov, Canada Buys, Alberta Purchasing added |
| Feb 4, 2026 | Sprint cadence established |
| Feb 9, 2026 | Unified lead schema — all sources normalized to single format |
| Feb 11, 2026 | LLM migrated to OpenRouter (Gemini Flash) |
| Feb 12, 2026 | Daily cron scrapers deployed (SAM.gov, Canada Buys, Alberta) |
| Feb 13, 2026 | 3 of 4 scrapers live; DIBBS blocked by .mil IP filtering |

## What's Been Built

### Scraping Infrastructure
- **4 government source scrapers** — DIBBS (DLA), SAM.gov, Canada Buys, Alberta Purchasing
- **Playwright browser automation** with shared browser pool for concurrent scraping
- **Unified lead normalization** — all sources produce a single schema for Google Sheets

### Contact Discovery
- **Firecrawl integration** — searches the web for supplier/manufacturer contact info
- **Confidence scoring** — HIGH (email + phone + address + website), MEDIUM (phone), LOW (website only)

### LLM Intelligence
- **Email classification** — categorizes incoming supplier replies by thread stage
- **Quote extraction** — pulls structured quote data from email text
- **Reply drafting** — generates context-aware responses for human review
- **Powered by OpenRouter** (Gemini Flash) for cost-effective inference

### Document Pipeline
- **PDF download and OCR** — extracts text from bid package documents
- **Structured field parsing** — eligibility, specs, quantity, delivery, deadlines

### Orchestration
- **8 n8n workflows** — 4 daily scrapers (cron 1–4 AM), dedup sub-workflow, document pipeline, email monitor, email outreach
- **FastAPI REST API** with 11+ endpoints, deployed on Railway (Docker)
- **Google Sheets integration** — n8n reads/writes rows as the shared data store

## Current Status (Feb 13, 2026)

### Live and Running
- 3 of 4 scrapers running daily via n8n cron (SAM.gov, Canada Buys, Alberta Purchasing)
- Document pipeline deployed (PDF download + OCR extraction)
- LLM endpoints live on Railway (classify-thread, draft-reply, extract-quote)
- Lead normalization producing unified schema across all sources

### Blocked
- **DIBBS scraper** works locally but fails on Railway — the `.mil` site blocks cloud/datacenter IPs. Options under evaluation: residential proxy, hybrid local/VPS approach, or alternative DLA data source.

### Not Yet Started
- Email inbox integration (credentials received, holding until DIBBS resolved)
- Email automation wiring (n8n workflows exist but not connected to live inbox)

## Roadmap

| Week | Focus |
|------|-------|
| **Week 1** | Finalize DIBBS proxy solution + data validation |
| **Week 2** | Email bot — inbox monitoring, reply classification, AI-drafted responses |
| **Week 3** | Full end-to-end testing across all sources and workflows |

## Tech Stack

| Component | Technology |
|-----------|-----------|
| **Backend** | Python 3.10 / FastAPI |
| **Browser Automation** | Playwright (headless Chromium) |
| **Orchestration** | n8n (self-hosted) |
| **LLM** | OpenRouter (Gemini Flash) |
| **Contact Discovery** | Firecrawl API |
| **Data Store** | Google Sheets |
| **Deployment** | Railway (Docker) |
| **Email** | IMAP / SMTP via n8n |
