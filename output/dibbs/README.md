# DIBBS (Defense Logistics Agency Internet Bid Board System)

## Source
DLA's DIBBS portal for military/government RFQs and solicitations.

## Endpoints

### GET /api/available-dates
Returns all available RFQ issue dates from DIBBS.
- **Output:** `available_dates.json`
- **Verify at:** https://www.dibbs.bsm.dla.mil/Rfq/RfqDates.aspx?category=issue

### POST /api/scrape-nsns-by-date
Scrapes all NSNs posted on a specific date.
- **Output:** `nsns_by_date.json`
- **Parameters:** `{"date": "02-09-2026", "maxPages": 1}`
- **Verify at:** https://www.dibbs.bsm.dla.mil/RFQ/RfqRecs.aspx?category=issue&TypeSrch=dt&Value=02-09-2026

## Notes
- DIBBS returned empty results during this run (2026-02-10 00:35 UTC) — the site may have been undergoing maintenance.
- Earlier same-day run (2026-02-09 20:20 UTC) returned 25 dates and NSN data successfully.
- The DIBBS consent banner must be clicked before data access (handled automatically by the scraper).
