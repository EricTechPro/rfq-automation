# Canada Buys (canadabuys.canada.ca)

## Source
Canadian federal government procurement portal for tender opportunities.

## Endpoint

### POST /api/search-canada-buys
Search Canada Buys for recent tender opportunities.
- **Output:** `search_results.json`
- **Parameters:** `{"daysBack": 7}`
- **Result:** 90 tenders from past 7 days
- **Data source:** Open Government CSV feed (primary), Playwright fallback

## Verification Links
- **Browse tenders:** https://canadabuys.canada.ca/en/tender-opportunities
- **Raw CSV data:** https://canadabuys.canada.ca/opendata/pub/openTenderNotice-ouvertAvisAppelOffres.csv

## Verification Checklist
- [ ] Open Canada Buys tender opportunities page
- [ ] Filter by last 7 days
- [ ] Compare tender titles and solicitation numbers with `search_results.json`
- [ ] Check contact names and emails match
- [ ] Verify closing dates match

## Notes
- Uses the open data CSV feed for reliability (no browser needed)
- Each tender includes `sourceUrl` linking to the specific tender page
- Contact info (name + email) is included directly from the CSV
