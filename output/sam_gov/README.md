# SAM.gov (System for Award Management)

## Source
U.S. federal government contract opportunities portal.

## Endpoint

### POST /api/search-sam
Search SAM.gov for contract opportunities using the public API.
- **Output:** `search_results.json`
- **Parameters:** `{"daysBack": 7, "maxPages": 1}`
- **Result:** 221,430 total opportunities (25 returned on page 1)
- **Verify at:** https://sam.gov/search/?index=opp&sort=-modifiedDate&page=1&pageSize=25

## Verification Checklist
- [ ] Open SAM.gov search, sort by "Modified Date" descending
- [ ] Compare first few opportunity titles with `search_results.json`
- [ ] Check solicitation numbers match
- [ ] Verify contact names/emails match point of contact data

## Notes
- Requires `SAM_GOV_API_KEY` env var (free API key from api.sam.gov)
- `enrichContacts` option fetches additional contact info from detail pages (slower)
- Results include `sourceUrl` linking directly to each opportunity
