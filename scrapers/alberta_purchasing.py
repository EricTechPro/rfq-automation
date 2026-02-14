"""
Alberta Purchasing Connection (APC) Scraper

Searches for opportunities via the APC JSON API at purchasing.alberta.ca.
Primary: Direct API calls to POST /api/opportunity/search (no auth required).
Fallback: Playwright browser scraping for the web UI.

Target: https://purchasing.alberta.ca/
"""

import asyncio
import re
from datetime import datetime, timedelta
from typing import Optional, List

import httpx

import sys
sys.path.insert(0, str(__file__).rsplit("/", 2)[0])

from config import config
from utils.logging import get_logger

logger = get_logger(__name__)

APC_BASE_URL = "https://purchasing.alberta.ca"
APC_API_URL = f"{APC_BASE_URL}/api/opportunity/search"
APC_DETAIL_API_URL = f"{APC_BASE_URL}/api/opportunity/public"
APC_POSTING_URL = f"{APC_BASE_URL}/posting"


def _build_search_payload(
    keywords: str = "",
    days_back: int = 7,
    max_results: int = 100,
    offset: int = 0,
    status_filter: str = "OPEN",
    solicitation_type: Optional[str] = None,
    category: Optional[str] = None,
) -> dict:
    """
    Build the API search payload.

    The API uses a 'Selectable' type for filter arrays.
    CRITICAL: 'selected': True MUST be included for filtering to work.
    """
    # Determine date range filter based on days_back
    if days_back <= 1:
        post_date_range = "$$last24Hours"
    elif days_back <= 7:
        post_date_range = "$$last7Days"
    elif days_back <= 30:
        post_date_range = "$$last30Days"
    elif days_back <= 365:
        post_date_range = "$$lastYear"
    else:
        post_date_range = "$$custom"

    statuses = []
    if status_filter:
        statuses = [{"value": status_filter, "selected": True}]

    solicitation_types = []
    if solicitation_type:
        solicitation_types = [{"value": solicitation_type, "selected": True}]

    categories = []
    if category:
        categories = [{"value": category, "selected": True}]

    return {
        "query": keywords or "",
        "queryMode": "standard",
        "filter": {
            "solicitationNumber": "",
            "categories": categories,
            "statuses": statuses,
            "agreementTypes": [],
            "solicitationTypes": solicitation_types,
            "opportunityTypes": [],
            "deliveryRegions": [],
            "deliveryRegion": "",
            "organizations": [],
            "unspsc": [],
            "postDateRange": post_date_range,
            "closeDateRange": "$$custom",
            "onlyBookmarked": False,
            "onlyInterestExpressed": False,
        },
        "limit": min(max_results, 200),
        "offset": offset,
        "sortOptions": [
            {"field": "PostDateTime", "direction": "desc"}
        ],
    }


def _parse_opportunity(raw: dict) -> dict:
    """Parse an API opportunity object into our normalized format."""
    ref = raw.get("referenceNumber", "")
    source_url = f"{APC_POSTING_URL}/{ref}" if ref else ""

    # Parse dates
    post_dt = raw.get("postDateTime", "")
    close_dt = raw.get("closeDateTime", "")
    published_date = post_dt[:10] if post_dt else ""
    closing_date = close_dt[:10] if close_dt else ""

    # Map status codes to readable names
    status_code = raw.get("statusCode", "")
    status_map = {
        "OPEN": "Open",
        "CLOSED": "Closed",
        "AWARD": "Awarded",
        "CANCELLED": "Cancelled",
        "EVALUATION": "Under Evaluation",
        "SELECTION": "Selection",
        "EXPIRED": "Expired",
    }
    status = status_map.get(status_code, status_code)

    return {
        "title": raw.get("shortTitle") or raw.get("title", ""),
        "referenceNumber": ref,
        "solicitationNumber": raw.get("solicitationNumber", ""),
        "status": status,
        "publishedDate": published_date,
        "closingDate": closing_date,
        "organization": raw.get("contractingOrganization", ""),
        "categoryCode": raw.get("categoryCode", ""),
        "solicitationTypeCode": raw.get("solicitationTypeCode", ""),
        "opportunityTypeCode": raw.get("opportunityTypeCode", ""),
        "description": (raw.get("projectDescription") or "")[:500],
        "commodityCodes": raw.get("commodityCodes", []),
        "regionOfDelivery": raw.get("regionOfDelivery", []),
        "sourceUrl": source_url,
        "source": "alberta_purchasing",
    }


def _parse_reference_number(ref: str) -> Optional[tuple]:
    """
    Parse 'AB-2026-01310' into ('2026', '1310') for the detail API URL.

    Returns None if the reference number doesn't match the expected format.
    """
    m = re.match(r"^AB-(\d{4})-0*(\d+)$", ref)
    if not m:
        return None
    return (m.group(1), m.group(2))


async def _fetch_detail_contacts(
    client: httpx.AsyncClient,
    reference_number: str,
) -> dict:
    """
    Fetch contact information from the detail API for a single opportunity.

    GET https://purchasing.alberta.ca/api/opportunity/public/{year}/{id}
    Returns dict with contactName, contactTitle, contactEmail, contactPhone, contactAddress.
    """
    parsed = _parse_reference_number(reference_number)
    if not parsed:
        return {}

    year, opp_id = parsed
    url = f"{APC_DETAIL_API_URL}/{year}/{opp_id}"

    try:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()

        opp = data.get("opportunity") or data
        contact = opp.get("contactInformation") or {}

        # Build full name from firstName + lastName
        first = (contact.get("firstName") or "").strip()
        last = (contact.get("lastName") or "").strip()
        full_name = f"{first} {last}".strip()

        # Build address from available fields
        addr_parts = [
            (contact.get("addressLine1") or "").strip(),
            (contact.get("addressLine2") or "").strip(),
            (contact.get("city") or "").strip(),
            (contact.get("province") or "").strip(),
            (contact.get("postalCode") or "").strip(),
        ]
        address = ", ".join(p for p in addr_parts if p)

        return {
            "contactName": full_name,
            "contactTitle": (contact.get("title") or "").strip(),
            "contactEmail": (contact.get("emailAddress") or "").strip(),
            "contactPhone": (contact.get("phoneNumber") or "").strip(),
            "contactAddress": address,
        }
    except httpx.HTTPStatusError as e:
        logger.debug("Detail API %d for %s", e.response.status_code, reference_number)
        return {}
    except Exception as e:
        logger.debug("Detail API error for %s: %s", reference_number, e)
        return {}


async def _enrich_with_contacts(
    opportunities: List[dict],
    max_concurrent: int = 5,
) -> List[dict]:
    """
    Batch-enrich opportunities with contact info from the detail API.

    Uses asyncio.Semaphore for concurrency control and 0.2s delay between requests.
    """
    sem = asyncio.Semaphore(max_concurrent)

    async def _enrich_one(client: httpx.AsyncClient, opp: dict) -> None:
        ref = opp.get("referenceNumber", "")
        if not ref:
            return
        async with sem:
            contacts = await _fetch_detail_contacts(client, ref)
            opp.update(contacts)
            await asyncio.sleep(0.2)

    headers = {"User-Agent": config.USER_AGENT, "Accept": "application/json"}
    async with httpx.AsyncClient(timeout=15, headers=headers) as client:
        await asyncio.gather(*[_enrich_one(client, opp) for opp in opportunities])

    return opportunities


async def search_opportunities(
    keywords: str = "",
    days_back: int = 7,
    max_results: int = 100,
    status_filter: str = "OPEN",
    solicitation_type: Optional[str] = None,
    category: Optional[str] = None,
    enrich_contacts: bool = False,
    browser_context=None,
) -> dict:
    """
    Search Alberta Purchasing Connection for opportunities.

    Uses the direct JSON API (no browser/Playwright needed).

    Args:
        keywords: Optional keyword search
        days_back: Number of days to look back
        max_results: Maximum results to return
        status_filter: Status filter (OPEN, CLOSED, AWARD, etc.). Empty = all.
        solicitation_type: Filter by type (RFQ, RFP, ITB, etc.). None = all.
        category: Filter by category (GD=Goods, SRV=Services, CNST=Construction). None = all.

    Returns:
        Dict with source, opportunities list, metadata
    """
    opportunities: List[dict] = []
    total_count = 0
    error_msg = None

    try:
        # Paginate through results
        offset = 0
        page_size = min(max_results, 200)

        async with httpx.AsyncClient(timeout=30) as client:
            while offset < max_results:
                payload = _build_search_payload(
                    keywords=keywords,
                    days_back=days_back,
                    max_results=page_size,
                    offset=offset,
                    status_filter=status_filter,
                    solicitation_type=solicitation_type,
                    category=category,
                )

                response = await client.post(
                    APC_API_URL,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
                response.raise_for_status()
                data = response.json()

                total_count = data.get("totalCount", 0)
                values = data.get("values", [])

                if not values:
                    break

                for raw in values:
                    opportunities.append(_parse_opportunity(raw))
                    if len(opportunities) >= max_results:
                        break

                if len(opportunities) >= max_results:
                    break

                offset += page_size
                if offset >= total_count:
                    break

                # Rate limit between pages
                await asyncio.sleep(0.3)

        logger.info("API returned %d of %d total opportunities", len(opportunities), total_count)

        if enrich_contacts and opportunities:
            concurrency = int(getattr(config, "APC_DETAIL_CONCURRENCY", 5))
            logger.info("Enriching %d opportunities with contacts (concurrency=%d)", len(opportunities), concurrency)
            await _enrich_with_contacts(opportunities, max_concurrent=concurrency)
            enriched = sum(1 for o in opportunities if o.get("contactEmail"))
            logger.info("Contact enrichment complete: %d/%d have email", enriched, len(opportunities))

    except httpx.HTTPStatusError as e:
        error_msg = f"API error: HTTP {e.response.status_code}"
        logger.warning("API error: HTTP %d", e.response.status_code)
        # Fall back to Playwright if API fails
        opportunities = await _scrape_fallback(keywords, days_back, max_results, browser_context=browser_context)
    except Exception as e:
        error_msg = str(e)
        logger.warning("API error: %s, falling back to Playwright", e)
        opportunities = await _scrape_fallback(keywords, days_back, max_results, browser_context=browser_context)

    result = {
        "source": "alberta_purchasing",
        "totalOpportunities": len(opportunities),
        "totalAvailable": total_count,
        "opportunities": opportunities,
        "scrapedAt": datetime.utcnow().isoformat() + "Z",
    }
    if error_msg:
        result["error"] = error_msg

    return result


async def _do_scrape_fallback(page, keywords: str, max_results: int) -> list:
    """Core Playwright fallback logic operating on an existing page."""
    opportunities = []

    url = f"{APC_BASE_URL}/search"
    if keywords:
        url += f"?keywords={keywords.replace(' ', '+')}"

    await page.goto(url, timeout=30000)
    await page.wait_for_load_state("networkidle")
    await asyncio.sleep(3)

    links = page.locator("a[href*='/posting/']")
    count = await links.count()

    seen_refs = set()
    for i in range(count):
        if len(opportunities) >= max_results:
            break
        try:
            link = links.nth(i)
            title = (await link.inner_text()).strip()
            href = await link.get_attribute("href") or ""

            if not title or len(title) < 5:
                continue

            ref_match = re.search(r'/posting/(AB-\d{4}-\d+)', href)
            ref = ref_match.group(1) if ref_match else ""

            if ref in seen_refs:
                continue
            seen_refs.add(ref)

            source_url = href if href.startswith("http") else f"{APC_BASE_URL}{href}"

            opportunities.append({
                "title": title,
                "referenceNumber": ref,
                "status": "Open",
                "publishedDate": "",
                "closingDate": "",
                "organization": "",
                "sourceUrl": source_url,
                "source": "alberta_purchasing",
            })
        except Exception:
            continue

    return opportunities


async def _scrape_fallback(
    keywords: str,
    days_back: int,
    max_results: int,
    browser_context=None,
) -> list:
    """
    Playwright fallback for when the API is unavailable.
    Extracts opportunity links from the search page.

    Args:
        browser_context: Optional BrowserContext from the shared pool.
    """
    # Pool path
    if browser_context is not None:
        page = await browser_context.new_page()
        try:
            return await _do_scrape_fallback(page, keywords, max_results)
        except Exception as e:
            logger.error("Playwright fallback error: %s", e, exc_info=True)
            return []
        finally:
            try:
                await page.close()
            except Exception:
                pass

    # Standalone path
    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=getattr(config, "HEADLESS", True))
            context = await browser.new_context(user_agent=config.USER_AGENT)
            page = await context.new_page()

            opportunities = await _do_scrape_fallback(page, keywords, max_results)

            await context.close()
            await browser.close()
            return opportunities

    except Exception as e:
        logger.error("Playwright fallback error: %s", e, exc_info=True)
        return []


def search_opportunities_sync(keywords="", days_back=7) -> dict:
    """Synchronous wrapper."""
    return asyncio.run(search_opportunities(keywords=keywords, days_back=days_back))
