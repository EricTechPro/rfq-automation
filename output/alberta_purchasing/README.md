# Alberta Purchasing Connection

## Source
Alberta provincial government procurement portal for goods, services, and construction.

## Endpoint

### POST /api/search-alberta-purchasing
Search Alberta Purchasing Connection for opportunities.
- **Output:** `search_results.json`
- **Parameters:** `{"daysBack": 7}`
- **Result:** 100 opportunities returned (1,551 total available)
- **Data source:** Direct JSON API at purchasing.alberta.ca/api/opportunity/search

## Verification Links
- **Browse opportunities:** https://purchasing.alberta.ca/search
- **Filter by status:** Add `?status=OPEN` to see open opportunities

## Verification Checklist
- [ ] Open Alberta Purchasing Connection search page
- [ ] Filter by open status and recent dates
- [ ] Compare opportunity titles and reference numbers with `search_results.json`
- [ ] Check organization names match
- [ ] Verify closing dates match

## Optional Filters
- `statusFilter`: OPEN, CLOSED, AWARD, CANCELLED, EVALUATION, EXPIRED
- `solicitationType`: RFQ, RFP, ITB, NRFP, RFEI
- `category`: GD (Goods), SRV (Services), CNST (Construction)

## Notes
- Uses direct JSON API (no browser scraping needed)
- Each opportunity includes `sourceUrl` linking to the posting page
- Includes commodity codes and region of delivery data
