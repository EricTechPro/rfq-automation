# RFQ Automation API - Endpoint Summary

> Generated: 2026-02-09 (updated with normalize endpoints)
> Server: `uvicorn api:app --host 0.0.0.0 --port 8000`
> API Docs: http://localhost:8000/docs

## Overview

| Source | Endpoint | Method | Output File | Live Data |
|--------|----------|--------|-------------|-----------|
| DIBBS | `/api/available-dates` | GET | [dibbs/available_dates.json](dibbs/available_dates.json) | 0 dates (site down) |
| DIBBS | `/api/scrape-nsns-by-date` | POST | [dibbs/nsns_by_date.json](dibbs/nsns_by_date.json) | 0 NSNs (site down) |
| SAM.gov | `/api/search-sam` | POST | [sam_gov/search_results.json](sam_gov/search_results.json) | 221,430 opportunities |
| Canada Buys | `/api/search-canada-buys` | POST | [canada_buys/search_results.json](canada_buys/search_results.json) | 90 tenders |
| Alberta | `/api/search-alberta-purchasing` | POST | [alberta_purchasing/search_results.json](alberta_purchasing/search_results.json) | 100 opportunities |
| LLM | `/api/classify-thread` | POST | [llm/classify_thread.json](llm/classify_thread.json) | "Quote Received" |
| LLM | `/api/extract-quote` | POST | [llm/extract_quote.json](llm/extract_quote.json) | Extracted pricing |
| LLM | `/api/draft-reply` | POST | [llm/draft_reply.json](llm/draft_reply.json) | Draft email |
| Documents | `/api/extract-document` | POST | [documents/extract_document.json](documents/extract_document.json) | HTTP 503 (DIBBS down) |
| Normalize | `/api/normalize-leads` | POST | `<source>/normalized_leads.json` | Scrape + normalize any source |
| Normalize | `/api/normalize-raw` | POST | — | Normalize pre-fetched raw data |

---

## Scraper Endpoints (Live Data)

### 1. DIBBS - Available Dates
```
GET /api/available-dates
```
- **Scrapes:** https://www.dibbs.bsm.dla.mil/Rfq/RfqDates.aspx?category=issue
- **Returns:** List of dates with active RFQs
- **Output:** [dibbs/available_dates.json](dibbs/available_dates.json)

### 2. DIBBS - NSNs by Date
```
POST /api/scrape-nsns-by-date
Body: {"date": "02-09-2026", "maxPages": 1}
```
- **Scrapes:** https://www.dibbs.bsm.dla.mil/RFQ/RfqRecs.aspx?category=issue&TypeSrch=dt&Value=02-09-2026
- **Returns:** NSNs with nomenclature, solicitation number, quantity, dates
- **Output:** [dibbs/nsns_by_date.json](dibbs/nsns_by_date.json)

### 3. SAM.gov - Opportunities
```
POST /api/search-sam
Body: {"daysBack": 7, "maxPages": 1}
```
- **Scrapes:** SAM.gov public API (api.sam.gov)
- **Verify:** https://sam.gov/search/?index=opp&sort=-modifiedDate
- **Returns:** Federal contract opportunities with contacts, deadlines, descriptions
- **Output:** [sam_gov/search_results.json](sam_gov/search_results.json)
- **Optional params:** `keyword`, `setAside`, `ptype`, `naicsCode`, `enrichContacts`

### 4. Canada Buys - Tenders
```
POST /api/search-canada-buys
Body: {"daysBack": 7}
```
- **Scrapes:** https://canadabuys.canada.ca/opendata/pub/openTenderNotice-ouvertAvisAppelOffres.csv
- **Verify:** https://canadabuys.canada.ca/en/tender-opportunities
- **Returns:** Canadian federal tenders with contacts, categories, closing dates
- **Output:** [canada_buys/search_results.json](canada_buys/search_results.json)
- **Optional params:** `keywords`, `maxResults`

### 5. Alberta Purchasing - Opportunities
```
POST /api/search-alberta-purchasing
Body: {"daysBack": 7}
```
- **Scrapes:** https://purchasing.alberta.ca/api/opportunity/search (JSON API)
- **Verify:** https://purchasing.alberta.ca/search
- **Returns:** Alberta provincial opportunities with organization, commodity codes
- **Output:** [alberta_purchasing/search_results.json](alberta_purchasing/search_results.json)
- **Optional params:** `keywords`, `statusFilter`, `solicitationType`, `category`

---

## LLM Endpoints (OpenRouter)

### 6. Classify Thread
```
POST /api/classify-thread
Body: {"thread": [{"from": "us", "body": "..."}, {"from": "supplier", "body": "..."}]}
```
- **Returns:** Procurement stage classification
- **Output:** [llm/classify_thread.json](llm/classify_thread.json)

### 7. Extract Quote
```
POST /api/extract-quote
Body: {"text": "email or document text with pricing info"}
```
- **Returns:** Structured pricing data (part number, unit price, quantity, lead time)
- **Output:** [llm/extract_quote.json](llm/extract_quote.json)

### 8. Draft Reply
```
POST /api/draft-reply
Body: {"thread": [...], "context": {"nsn": "...", "partNumber": "...", "quantity": 500}}
```
- **Returns:** Context-aware email draft with auto-classified stage
- **Output:** [llm/draft_reply.json](llm/draft_reply.json)

---

## Document Intelligence

### 9. Extract Document
```
POST /api/extract-document
Body: {"url": "https://example.com/document.pdf"}
```
- **Downloads:** PDF from URL, extracts text (OCR fallback for scanned docs)
- **Returns:** Raw text + parsed fields (eligibility, specs, quantity, delivery, deadlines)
- **Output:** [documents/extract_document.json](documents/extract_document.json)

---

## Normalize Endpoints (Unified Lead Schema)

### 10. Normalize Leads (Scrape + Normalize)
```
POST /api/normalize-leads
Body: {"source": "sam_gov", "daysBack": 7, "maxPages": 1}
```
- **Scrapes** the specified source, then maps results into the 26-column UnifiedLead schema
- **Sources:** `sam_gov`, `canada_buys`, `alberta_purchasing`, `dibbs`
- **Returns:** `{ "totalLeads": N, "leads": [ {...flat lead...} ] }`
- **Output:** `<source>/normalized_leads.json`

### 11. Normalize Raw (Pre-fetched Data)
```
POST /api/normalize-raw
Body: {"source": "sam_gov", "data": { ...raw scraper output... }}
```
- **Accepts** raw JSON from any scraper endpoint and normalizes it
- **Use case:** n8n workflows that already have raw data
- **Returns:** Same format as `/api/normalize-leads`

### UnifiedLead Schema (26 columns)
| Column | Description |
|--------|-------------|
| source | sam_gov, canada_buys, alberta_purchasing, dibbs |
| title | Opportunity/tender/NSN title |
| solicitationNumber | Solicitation/reference number |
| description | Full description (HTML stripped) |
| postedDate | YYYY-MM-DD |
| closingDate | YYYY-MM-DD |
| sourceUrl | Link to original posting |
| organization | Issuing organization |
| status | Open, Solicitation, etc. |
| category | NAICS code / category code |
| nsn | NSN (DIBBS only) |
| quantity | Quantity (DIBBS only) |
| contactName | Buyer point of contact name |
| contactEmail | Buyer POC email |
| contactPhone | Buyer POC phone |
| supplierName | From Firecrawl (future) |
| supplierEmail | Supplier email |
| supplierPhone | Supplier phone |
| supplierWebsite | Supplier website |
| cageCode | CAGE code |
| confidence | Contact confidence level |
| emailStatus | Pipeline stage (default: "New") |
| emailDraft | Draft email text |
| documentUrl | Associated document URL |
| dateAdded | YYYY-MM-DD (auto-set) |
| notes | Free-text notes |

---

## Additional Endpoints (Not Organized)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/health` | GET | Health check |
| `/` | GET | Root health check (Railway) |
| `/api/batch` | POST | Full pipeline: NSN list -> DIBBS + WBParts + Firecrawl contacts |
| `/api/scrape-nsn-suppliers` | POST | Single NSN -> full supplier contact discovery |

---

## Verification Guide

1. Open each "Verify at" link in your browser
2. Compare data on the website with the corresponding JSON file
3. Check: Do titles match? Do dates match? Do solicitation numbers match? Do contacts match?
4. For DIBBS: Site was down during this run; re-run when available
5. For LLM endpoints: No website to verify against; check if output is reasonable for the input
