# n8n Workflow Setup Guide

## Google Sheets Setup

Suggested Google Sheet name: **RFQ Automation**

CSV templates with pre-built headers are in `n8n/sheets/`. Import one per tab:

| File | Sheet Tab | Columns |
|------|-----------|---------|
| `sheets/all-opportunities.csv` | All Opportunities | 28 columns — NSN, supplier, contact, outreach fields |
| `sheets/documents.csv` | Documents | 10 columns — extracted document intelligence |
| `sheets/email-monitor.csv` | Email Monitor | 7 columns — email classification + draft replies |

**To import:** In Google Sheets, create a tab, then File > Import > Upload > select the CSV > "Replace current sheet".

## Prerequisites

Before importing workflows, set up these in n8n:

1. **Have n8n running** (self-hosted or n8n cloud)
2. **Create a Google Sheets OAuth credential** in n8n:
   - Settings > Credentials > Add Credential > Google Sheets OAuth2
   - Follow the Google Cloud Console OAuth setup flow
3. **Create a Google Sheet** named "RFQ Automation" with 3 tabs (import CSV templates above):
   - `All Opportunities` — scraped leads from all sources (DIBBS, SAM.gov, Canada Buys, Alberta)
   - `Documents` — extracted document intelligence
   - `Email Monitor` — classified emails + draft replies
4. **Copy the Google Sheet document ID** from its URL: `https://docs.google.com/spreadsheets/d/{THIS_PART}/edit`
5. **Set n8n environment variable:** `EMAIL_ADDRESS` = your email address (Settings > Variables)

## Import Order & Configuration

Import workflows in this order — earlier workflows are dependencies for later ones.

### Step 1a: `workflow-dibbs-daily.json` (DIBBS Scraper)

**Import:**
1. Import `n8n/workflow-dibbs-daily.json`
2. Open the **"Get Existing Rows"** and **"Append to Sheets"** nodes:
   - Select your Google Sheets OAuth credential on each

**API endpoints:** `POST /api/scrape-nsns-by-date`, `POST /api/scrape-nsn-suppliers` (rate-limited 1 per 5 sec)

**Test:** Execute manually, wait 5-10 minutes (DIBBS is slow), check "All Opportunities" sheet. Run again — should add 0 rows.

---

### Step 1b: `workflow-sam-daily.json` (SAM.gov Scraper)

**Import:**
1. Import `n8n/workflow-sam-daily.json`
2. Open the **"Get Existing Rows"** and **"Append to Sheets"** nodes:
   - Select your Google Sheets OAuth credential on each

**API endpoint:** `POST /api/search-sam`

**Test:** Execute manually, check "All Opportunities" sheet for SAM.gov rows.

---

### Step 1c: `workflow-canada-buys-daily.json` (Canada Buys Scraper)

**Import:**
1. Import `n8n/workflow-canada-buys-daily.json`
2. Open the **"Get Existing Rows"** and **"Append to Sheets"** nodes:
   - Select your Google Sheets OAuth credential on each

**API endpoint:** `POST /api/search-canada-buys`

**Test:** Execute manually, check "All Opportunities" sheet for Canada Buys rows.

---

### Step 1d: `workflow-alberta-daily.json` (Alberta Purchasing Scraper)

**Import:**
1. Import `n8n/workflow-alberta-daily.json`
2. Open the **"Get Existing Rows"** and **"Append to Sheets"** nodes:
   - Select your Google Sheets OAuth credential on each

**API endpoint:** `POST /api/search-alberta-purchasing`

**Test:** Execute manually, check "All Opportunities" sheet for Alberta rows.

**Activate** all 4 daily schedules when satisfied. Each runs independently — if one source fails, the others are unaffected.

---

### Step 2: `workflow-email-monitor.json` (Independent)

**Why second:** This is independent of the scraper but needs the LLM endpoints. Good to verify those work.

**Prerequisites:** IMAP credential (Gmail: use App Password, not regular password)

**Import:**
1. Import `n8n/workflow-email-monitor.json`
2. Open **"Read New Emails"** node > set IMAP credential
3. Open **"Google Sheets"** node > select your Sheet + "Email Monitor" tab
4. Verify `EMAIL_ADDRESS` env var is set in n8n

**API endpoints this calls:**
- `POST /api/classify-thread` (LLM classification — needs `OPENROUTER_API_KEY` on Railway)
- `POST /api/draft-reply` (LLM draft — needs `OPENROUTER_API_KEY` on Railway)

**Test:** Send yourself a test email, then execute the workflow manually. Check the "Email Monitor" tab.

---

### Step 3: `workflow-document-pipeline.json` (Independent)

**Import:**
1. Import `n8n/workflow-document-pipeline.json`
2. Open **"Google Sheets"** node > select your Sheet + "Documents" tab

**API endpoints this calls:**
- `POST /api/extract-document` (rate-limited 1 per 3 sec)

**Test:** After activating, POST to the webhook URL that n8n generates:
```bash
curl -X POST https://your-n8n-url/webhook/document-trigger \
  -H "Content-Type: application/json" \
  -d '{"nsn": "5306003733291", "solicitationNumber": "TEST-001", "documentUrls": ["https://example.com/test.pdf"]}'
```

---

### Step 4: `workflow-email-outreach.json` (Depends on Step 1)

**Why last:** This watches the "All Opportunities" sheet for new rows — it needs Step 1 to be producing data first.

**Prerequisites:** SMTP credential configured in n8n

**Import:**
1. Import `n8n/workflow-email-outreach.json`
2. Open **"New Row Trigger"** > select your Sheet + the "All Opportunities" tab
3. Open **"Update Sheet Status"** > select the same Sheet + tab
4. Open **"Send Outreach Email"** > set SMTP credential
5. Verify `EMAIL_ADDRESS` env var is set

**How it works:**
- Polls sheet every 5 seconds for new rows
- Filters: must have `Email` field + `Status` = "New"
- Sends email using `Email Draft` column as body
- Updates `Status` to "Outreach Sent" + stamps `Email Sent Date`

**WARNING:** Activate this only when you're ready — it will immediately send emails to any row with Status="New" and an Email address. Test with a dummy row first.

## Verification Checklist

| Step | What to verify |
|------|---------------|
| After Step 1a-1d | Each scraper populates "All Opportunities" sheet independently. Second run of each adds 0 rows. |
| After Step 2 | Test email appears in "Email Monitor" tab with Stage + Draft Reply |
| After Step 3 | Webhook POST creates row in "Documents" tab |
| After Step 4 | Test row with Status="New" + Email triggers an outreach email |

## Daily Scraper Schedule

All daily scrapers use cron expressions and run staggered during the low-traffic window. **Set n8n timezone to `America/Los_Angeles`** (Settings > General > Timezone).

| Workflow | Time (PT) | UTC | Cron | Est. Duration |
|----------|-----------|-----|------|---------------|
| SAM.gov | 1:00 AM | 9:00 AM | `0 1 * * *` | ~2-5 min |
| Canada Buys | 2:00 AM | 10:00 AM | `0 2 * * *` | ~1-3 min |
| Alberta | 3:00 AM | 11:00 AM | `0 3 * * *` | ~1-2 min |
| DIBBS | 4:00 AM | 12:00 PM | `0 4 * * *` | ~30-60 min |

Each workflow runs independently with 1-hour gaps. Even DIBBS (the longest) should finish well before business hours.

## API Configuration

All workflows call the Railway-deployed API at:
- **Base URL:** `https://web-production-d9a0e.up.railway.app`
- **Auth Header:** `X-API-Key: <your RFQ_API_KEY>`

These are hardcoded in the workflow HTTP Request nodes. Update them if your Railway URL changes.

## Troubleshooting

- **HTTP 401/403 from API:** Check that `X-API-Key` in workflow nodes matches your Railway `RFQ_API_KEY` env var
- **Empty results from DIBBS:** DLA site may be down — check `/health` endpoint
- **LLM endpoints fail (classify/draft):** Ensure `OPENROUTER_API_KEY` is set on Railway
- **Google Sheets "permission denied":** Re-authorize the OAuth credential in n8n
- **Railway URL changed:** Update the base URL in all HTTP Request nodes across all workflows
