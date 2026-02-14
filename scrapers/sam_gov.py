"""
SAM.gov Scraper

Searches for contract opportunities on SAM.gov using the public API.
Falls back to Playwright-based scraping if no API key is configured.

API docs: https://open.gsa.gov/api/get-opportunities-public-api/
"""

import asyncio
import json
import re
import requests
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from urllib.parse import urlencode, quote

import sys
sys.path.insert(0, str(__file__).rsplit("/", 2)[0])

from config import config
from models import SAMOpportunity, SAMPointOfContact, SAMSearchResult
from utils.logging import get_logger

logger = get_logger(__name__)


# Valid set-aside codes for the API
VALID_SET_ASIDES = {
    "SBA": "Total Small Business Set-Aside",
    "SBP": "Partial Small Business Set-Aside",
    "8A": "8(a) Set-Aside",
    "8AN": "8(a) Sole Source",
    "HZC": "HUBZone Set-Aside",
    "HZS": "HUBZone Sole Source",
    "SDVOSBC": "Service-Disabled Veteran-Owned Small Business Set-Aside",
    "SDVOSBS": "SDVOSB Sole Source",
    "WOSB": "Women-Owned Small Business Program Set-Aside",
    "WOSBSS": "WOSB Program Sole Source",
    "EDWOSB": "Economically Disadvantaged WOSB Set-Aside",
    "EDWOSBSS": "EDWOSB Sole Source",
}

# Valid procurement types
VALID_PTYPES = {
    "o": "Solicitation",
    "k": "Combined Synopsis/Solicitation",
    "p": "Pre-solicitation",
    "r": "Sources Sought",
    "s": "Special Notice",
    "a": "Award Notice",
    "u": "Justification (J&A)",
    "g": "Sale of Surplus Property",
    "i": "Intent to Bundle Requirements (DoD-Funded)",
}

# SAM.gov notice type codes used in the SPA URL filters
_SAM_PTYPE_TO_NOTICE_TYPE = {
    "o": "o",
    "k": "k",
    "p": "p",
    "r": "r",
    "s": "s",
    "a": "a",
    "u": "u",
    "g": "g",
    "i": "i",
}

# Concurrency guard — one Playwright browser at a time for SAM.gov
# Lazy-initialized to avoid binding to wrong event loop at import time
_sam_scrape_semaphore: Optional[asyncio.Semaphore] = None


def _get_sam_semaphore() -> asyncio.Semaphore:
    """Get or create the SAM.gov scrape semaphore for the current event loop."""
    global _sam_scrape_semaphore
    if _sam_scrape_semaphore is None:
        _sam_scrape_semaphore = asyncio.Semaphore(1)
    return _sam_scrape_semaphore


def _build_search_params(
    days_back: int = 7,
    set_aside: Optional[str] = None,
    ptype: Optional[str] = None,
    naics_code: Optional[str] = None,
    keyword: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> Dict[str, str]:
    """
    Build query parameters for the SAM.gov API search.

    Args:
        days_back: Number of days to look back for posted opportunities
        set_aside: Set-aside type code (e.g., "SBA", "8A", "HZC")
        ptype: Procurement type code (e.g., "o" for Solicitation)
        naics_code: NAICS code filter (max 6 digits)
        keyword: Keyword to search in titles
        limit: Results per page (max 1000)
        offset: Page offset for pagination

    Returns:
        Dictionary of query parameters
    """
    now = datetime.utcnow()
    posted_from = (now - timedelta(days=days_back)).strftime("%m/%d/%Y")
    posted_to = now.strftime("%m/%d/%Y")

    params = {
        "api_key": config.SAM_GOV_API_KEY,
        "postedFrom": posted_from,
        "postedTo": posted_to,
        "limit": str(min(limit, 1000)),
        "offset": str(offset),
    }

    if set_aside and set_aside in VALID_SET_ASIDES:
        params["typeOfSetAside"] = set_aside

    if ptype and ptype in VALID_PTYPES:
        params["ptype"] = ptype

    if naics_code:
        params["ncode"] = naics_code[:6]

    if keyword:
        params["title"] = keyword

    return params


def _build_search_url(
    page_num: int = 1,
    set_aside: Optional[str] = None,
    ptype: Optional[str] = None,
    naics_code: Optional[str] = None,
    keyword: Optional[str] = None,
) -> str:
    """
    Build the SAM.gov SPA search URL with filter parameters.

    SAM.gov uses a complex query string format with nested bracket notation
    for its Angular frontend. This constructs a URL that will trigger the
    internal search API when loaded.

    Args:
        page_num: Page number (1-based)
        set_aside: Set-aside type code
        ptype: Procurement type code
        naics_code: NAICS code filter
        keyword: Keyword search term

    Returns:
        Full SAM.gov search URL string
    """
    page_size = config.SAM_GOV_PAGE_SIZE

    # Base query params (these are always present)
    parts = [
        f"page={page_num}",
        f"pageSize={page_size}",
        "sort=-modifiedDate",
        "sfm[status][is_active]=true",
    ]

    # Add keyword search
    if keyword:
        parts.append(f"sfm[simpleSearch][keywordRadio]=EXACT")
        parts.append(f"sfm[simpleSearch][keywordTags][0][key]={quote(keyword)}")
        parts.append(f"sfm[simpleSearch][keywordTags][0][value]={quote(keyword)}")
    else:
        parts.append("sfm[simpleSearch][keywordRadio]=EXACT")

    # Add notice type filter
    if ptype and ptype in _SAM_PTYPE_TO_NOTICE_TYPE:
        parts.append(f"sfm[dateFilter][startDate]=")
        parts.append(f"sfm[dateFilter][endDate]=")

    # Add set-aside filter
    if set_aside and set_aside in VALID_SET_ASIDES:
        parts.append(f"sfm[typeOfSetAside]={set_aside}")

    # Add NAICS code filter
    if naics_code:
        parts.append(f"sfm[naicsCode]={naics_code[:6]}")

    query = "&".join(parts)
    return f"https://sam.gov/search/?{query}"


async def _handle_sam_consent(page) -> bool:
    """
    Dismiss SAM.gov disclaimer/consent banner if present.

    SAM.gov may show a disclaimer modal on first visit. This tries multiple
    selectors to find and dismiss it.

    Returns True if a banner was dismissed, False otherwise.
    """
    try:
        # Common SAM.gov disclaimer selectors
        selectors = [
            'button:has-text("Accept")',
            'button:has-text("I Accept")',
            'button:has-text("OK")',
            'button:has-text("Agree")',
            '[class*="accept"]',
            '[class*="disclaimer"] button',
            '.usa-modal button.usa-button',
        ]

        for selector in selectors:
            try:
                btn = page.locator(selector).first
                if await btn.count() > 0 and await btn.is_visible():
                    await btn.click()
                    logger.info("Dismissed SAM.gov consent/disclaimer banner")
                    await asyncio.sleep(1)
                    return True
            except Exception:
                continue

        return False
    except Exception as e:
        logger.debug("Consent banner check error: %s", e)
        return False


async def _wait_for_sam_render(page, timeout_ms: int = 15000) -> bool:
    """
    Wait for SAM.gov Angular SPA to finish rendering search results.

    Waits for network to settle and checks for known result indicators
    discovered from live site analysis:
    - app-opportunity-result: Angular component wrapping each result card
    - sds-search-result-list: container for all results
    - div.sds-pagination: shows "Showing 1 - 25 of X results"
    - a.usa-link[href*="/opp/"]: links to opportunity detail pages

    Returns True if results appear rendered, False on timeout.
    """
    try:
        await page.wait_for_load_state("networkidle", timeout=timeout_ms)
    except Exception:
        pass  # networkidle may not trigger on SPAs, continue anyway

    # Known SAM.gov result selectors (from live site analysis)
    result_selectors = [
        'app-opportunity-result',
        'sds-search-result-list',
        'a.usa-link[href*="/opp/"]',
        'div.sds-pagination',
    ]

    for selector in result_selectors:
        try:
            await page.wait_for_selector(selector, timeout=5000)
            return True
        except Exception:
            continue

    # Final fallback: wait a bit for any dynamic content
    await asyncio.sleep(3)
    return False


def _parse_intercepted_opportunity(opp: Dict[str, Any]) -> Optional[SAMOpportunity]:
    """
    Parse an opportunity from intercepted SAM.gov internal API response.

    The internal API at /api/prod/sgs/v1/search/ returns results with:
    - _id: opportunity ID (hex string)
    - title, solicitationNumber: strings
    - publishDate, responseDate, modifiedDate: ISO timestamps
    - type: {code: "o", value: "Solicitation"} (object, not string)
    - organizationHierarchy: [{name, type, level}, ...] (array, not dot string)
    - descriptions: [{content: "html..."}]

    Also handles public API format and DOM-extracted dicts as fallback.
    """
    if not opp or not isinstance(opp, dict):
        return None

    try:
        # Extract contacts (public API has pointOfContact; internal may not)
        contacts = []
        for poc in opp.get("pointOfContact", opp.get("pointsOfContact", [])) or []:
            contacts.append(SAMPointOfContact(
                name=poc.get("fullName") or poc.get("name"),
                email=poc.get("email"),
                phone=poc.get("phone") or poc.get("fax"),
                type=poc.get("type"),
            ))

        # Extract organization — internal API uses array, public API uses dot string
        department = None
        agency = None
        org_hierarchy = opp.get("organizationHierarchy")
        if isinstance(org_hierarchy, list) and org_hierarchy:
            # Internal API format: [{name, type, level}, ...]
            for org in org_hierarchy:
                org_type = org.get("type", "")
                if org_type == "DEPARTMENT" or org.get("level") == 1:
                    department = org.get("name")
                elif org_type == "AGENCY" or org.get("level") == 2:
                    agency = org.get("name")
        elif isinstance(org_hierarchy, str):
            # Fallback: dot-separated string
            org_parts = [p.strip() for p in org_hierarchy.split(".")]
            department = org_parts[0] if org_parts else None
            agency = org_parts[1] if len(org_parts) > 1 else None
        else:
            # Public API format
            org_path = opp.get("fullParentPathName", "")
            if org_path:
                org_parts = [p.strip() for p in org_path.split(".")]
                department = org_parts[0] if org_parts else None
                agency = org_parts[1] if len(org_parts) > 1 else None

        if not department:
            department = opp.get("department")
        if not agency:
            agency = opp.get("agency") or opp.get("subtierAgency")

        # Extract place of performance
        pop = opp.get("placeOfPerformance", {}) or {}
        pop_parts = []
        if isinstance(pop, dict):
            city_info = pop.get("city", {}) or {}
            state_info = pop.get("state", {}) or {}
            country_info = pop.get("country", {}) or {}
            if isinstance(city_info, dict) and city_info.get("name"):
                pop_parts.append(city_info["name"])
            elif isinstance(city_info, str):
                pop_parts.append(city_info)
            if isinstance(state_info, dict) and state_info.get("name"):
                pop_parts.append(state_info["name"])
            elif isinstance(state_info, str):
                pop_parts.append(state_info)
            if isinstance(country_info, dict) and country_info.get("name"):
                pop_parts.append(country_info["name"])
        elif isinstance(pop, str):
            pop_parts.append(pop)
        place_of_performance = ", ".join(pop_parts) if pop_parts else None

        # Extract description — internal API uses descriptions[].content
        description = opp.get("description")
        if not description:
            descriptions = opp.get("descriptions", [])
            if descriptions and isinstance(descriptions, list):
                description = descriptions[0].get("content", "")

        # Build UI link — internal API links use /workspace/contract/opp/{id}/view
        notice_id = opp.get("noticeId") or opp.get("_id", "")
        ui_link = opp.get("uiLink", "")
        if not ui_link and notice_id:
            ui_link = f"https://sam.gov/workspace/contract/opp/{notice_id}/view"

        # Extract notice type — internal API has type as {code, value} object
        notice_type = opp.get("noticeType")
        if not notice_type:
            type_field = opp.get("type")
            if isinstance(type_field, dict):
                notice_type = type_field.get("value") or type_field.get("code")
            elif isinstance(type_field, str):
                notice_type = type_field

        return SAMOpportunity(
            title=opp.get("title", ""),
            solicitationNumber=opp.get("solicitationNumber"),
            noticeId=notice_id,
            department=department,
            agency=agency,
            postedDate=opp.get("postedDate") or opp.get("publishDate"),
            responseDeadline=opp.get("responseDeadLine") or opp.get("responseDeadline") or opp.get("responseDate"),
            setAside=opp.get("typeOfSetAsideDescription") or opp.get("typeOfSetAside") or opp.get("setAside"),
            naicsCode=opp.get("naicsCode"),
            classificationCode=opp.get("classificationCode") or opp.get("psc"),
            description=description,
            placeOfPerformance=place_of_performance,
            pointOfContact=contacts,
            attachmentLinks=opp.get("resourceLinks", []) or [],
            sourceUrl=ui_link,
            noticeType=notice_type,
        )
    except Exception as e:
        logger.error("Error parsing opportunity: %s", e, exc_info=True)
        return None


async def _extract_opportunities_from_dom(page) -> List[Dict[str, Any]]:
    """
    DOM-based fallback: extract opportunity data from rendered SAM.gov page.

    Uses selectors discovered from live site analysis:
    - app-opportunity-result: Angular component for each result card
    - h3.margin-y-0 > a.usa-link: title link with href /workspace/contract/opp/{id}/view
    - .sds-field__name / .sds-field__value: labeled fields (Department, Notice Type, etc.)
    - Notice ID shown as "Notice ID: XXXXX" in h3.font-sans-xs
    """
    opportunities = []

    try:
        # Primary: find result cards by Angular component
        cards = page.locator('app-opportunity-result')
        count = await cards.count()

        if count == 0:
            # Fallback: look for opportunity links directly
            links = page.locator('a.usa-link[href*="/opp/"]')
            link_count = await links.count()
            if link_count > 0:
                logger.debug("DOM fallback: found %d opportunity links", link_count)
                seen_ids = set()
                for i in range(link_count):
                    try:
                        link = links.nth(i)
                        href = await link.get_attribute("href") or ""
                        title = (await link.inner_text()).strip()

                        notice_id_match = re.search(r'/opp/([a-f0-9]+)', href)
                        notice_id = notice_id_match.group(1) if notice_id_match else ""

                        # Skip duplicate links (each card has title + modification count links)
                        if notice_id in seen_ids or not title or len(title) < 5:
                            continue
                        seen_ids.add(notice_id)

                        opportunities.append({
                            "title": title,
                            "_id": notice_id,
                            "uiLink": f"https://sam.gov{href}" if href.startswith("/") else href,
                        })
                    except Exception as e:
                        logger.debug("DOM link extraction error: %s", e)
                        continue
            return opportunities

        logger.debug("DOM fallback: found %d result cards (app-opportunity-result)", count)

        for i in range(count):
            try:
                card = cards.nth(i)

                opp_data: Dict[str, Any] = {}

                # Title from h3 > a.usa-link link
                title_link = card.locator('h3.margin-y-0 a.usa-link').first
                if await title_link.count() > 0:
                    opp_data["title"] = (await title_link.inner_text()).strip()
                    href = await title_link.get_attribute("href") or ""
                    notice_match = re.search(r'/opp/([a-f0-9]+)', href)
                    if notice_match:
                        opp_data["_id"] = notice_match.group(1)
                    opp_data["uiLink"] = f"https://sam.gov{href}" if href.startswith("/") else href

                # Notice ID / solicitation number from "Notice ID: XXXXX"
                notice_h3 = card.locator('h3.font-sans-xs')
                if await notice_h3.count() > 0:
                    notice_text = (await notice_h3.inner_text()).strip()
                    notice_match = re.match(r'Notice ID:\s*(.+)', notice_text)
                    if notice_match:
                        opp_data["solicitationNumber"] = notice_match.group(1).strip()

                # Extract labeled fields (sds-field__name / sds-field__value pairs)
                fields = card.locator('.sds-field.sds-field--stacked')
                field_count = await fields.count()
                for f_idx in range(field_count):
                    try:
                        field = fields.nth(f_idx)
                        name_el = field.locator('.sds-field__name')
                        value_el = field.locator('.sds-field__value')
                        if await name_el.count() > 0 and await value_el.count() > 0:
                            fname = (await name_el.inner_text()).strip()
                            fvalue = (await value_el.inner_text()).strip()
                            if "Department" in fname:
                                opp_data["department"] = fvalue
                            elif "Subtier" in fname:
                                opp_data["agency"] = fvalue
                            elif "Notice Type" in fname:
                                opp_data["noticeType"] = fvalue
                            elif "Offers Due" in fname or "Response" in fname:
                                opp_data["responseDate"] = fvalue
                            elif "Published" in fname:
                                opp_data["publishDate"] = fvalue
                    except Exception as e:
                        logger.debug("DOM field extraction error: %s", e)
                        continue

                if opp_data.get("title"):
                    opportunities.append(opp_data)
            except Exception as e:
                logger.debug("DOM card extraction error: %s", e)
                continue

    except Exception as e:
        logger.error("DOM extraction error: %s", e, exc_info=True)

    return opportunities


async def _scrape_detail_contacts(page, notice_id: str, timeout_ms: int = 15000) -> List[SAMPointOfContact]:
    """
    Scrape contact information from a SAM.gov opportunity detail page.

    Uses network interception to capture the detail API response, which
    includes pointOfContact data not available in search results.

    Falls back to DOM extraction if network interception fails.

    Args:
        page: Playwright page instance
        notice_id: The opportunity ID (hex string from _id field)
        timeout_ms: Navigation timeout in milliseconds

    Returns:
        List of SAMPointOfContact (may be empty on failure)
    """
    contacts: List[SAMPointOfContact] = []
    captured_detail: List[Dict[str, Any]] = []

    async def handle_detail_response(response):
        """Capture the opportunity detail API response.

        The detail page fires: /api/prod/opps/v2/opportunities/{id}?api_key=null&random=...
        Response structure: {data2: {pointOfContact: [...]}, ...}
        We exclude /history, /related, /resources sub-endpoints.
        """
        if response.status != 200:
            return
        try:
            content_type = response.headers.get("content-type", "")
            if "json" not in content_type:
                return
            url = response.url
            if "/api/prod/opps/v2/opportunities/" not in url:
                return
            # Skip sub-endpoints (history, related, resources)
            path_after_id = url.split("/opportunities/")[-1]
            if "/" in path_after_id.split("?")[0].strip("/"):
                return
            body = await response.json()
            if isinstance(body, dict):
                captured_detail.append(body)
        except Exception as e:
            logger.debug("Detail XHR handler error: %s", e)

    try:
        # SAM.gov detail pages use /workspace/contract/opp/{id}/view
        detail_url = f"https://sam.gov/workspace/contract/opp/{notice_id}/view"
        page.on("response", handle_detail_response)

        await page.goto(detail_url, timeout=timeout_ms, wait_until="domcontentloaded")

        # Wait for network to settle and API calls to complete
        try:
            await page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass
        await asyncio.sleep(2)

        page.remove_listener("response", handle_detail_response)

        # Parse contacts from intercepted detail API response
        for detail_data in captured_detail:
            # Contacts are in data2.pointOfContact
            data2 = detail_data.get("data2") or detail_data.get("data") or detail_data
            poc_list = data2.get("pointOfContact") or data2.get("pointsOfContact") or []
            for poc in poc_list:
                if isinstance(poc, dict):
                    contact = SAMPointOfContact(
                        name=poc.get("fullName") or poc.get("name"),
                        email=poc.get("email"),
                        phone=poc.get("phone") or poc.get("fax"),
                        type=poc.get("type"),
                    )
                    # Only add if we got at least a name or email
                    if contact.name or contact.email:
                        contacts.append(contact)
            if contacts:
                break  # Got contacts from first valid response

        # DOM fallback: extract contacts from rendered page text
        if not contacts:
            try:
                body_text = await page.inner_text("body")
                lines = [l.strip() for l in body_text.split("\n") if l.strip()]

                # Find "Primary Point of Contact" or "Contact Information" section
                for i, line in enumerate(lines):
                    if "Point of Contact" in line or "Contact Information" in line:
                        # Scan nearby lines for email/phone/name
                        nearby = lines[i:min(len(lines), i + 15)]
                        nearby_text = "\n".join(nearby)
                        email_match = re.search(r'[\w.+-]+@[\w-]+\.[\w.-]+', nearby_text)
                        phone_match = re.search(r'\d{3}[-.\s]?\d{3}[-.\s]?\d{4}', nearby_text)
                        # Name is typically the line right after "Primary Point of Contact"
                        _NAME_BLOCKLIST = {
                            "Attachments/Links", "Attachments", "Links",
                            "N/A", "TBD", "None", "Not Available",
                            "Description", "Type", "Email", "Phone Number",
                        }
                        name = None
                        for n_line in nearby[1:4]:
                            if n_line and n_line not in _NAME_BLOCKLIST and "@" not in n_line and not re.match(r'^[\d\-()\s.]+$', n_line):
                                name = n_line
                                break
                        if email_match or phone_match or name:
                            contacts.append(SAMPointOfContact(
                                name=name,
                                email=email_match.group(0) if email_match else None,
                                phone=phone_match.group(0).strip() if phone_match else None,
                                type="primary",
                            ))
                        break
            except Exception as e:
                logger.debug("DOM contact fallback error: %s", e)

    except Exception as e:
        logger.error("Error scraping detail page for %s: %s", notice_id, e, exc_info=True)
        # Remove listener on error to avoid leaks
        try:
            page.remove_listener("response", handle_detail_response)
        except Exception:
            pass

    return contacts


async def _enrich_opportunities_with_contacts(
    context,
    opportunities: List[SAMOpportunity],
    max_details: int = 10,
    timeout_ms: int = 15000,
) -> List[SAMOpportunity]:
    """
    Enrich opportunities with contact info from their detail pages.

    Opens a new page from the existing browser context and visits each
    opportunity's detail page to extract point of contact data.

    Args:
        context: Playwright browser context
        opportunities: List of SAMOpportunity objects to enrich
        max_details: Maximum number of detail pages to visit (0 = all)
        timeout_ms: Timeout per detail page navigation

    Returns:
        The same list of opportunities, mutated with contact data
    """
    detail_page = await context.new_page()
    limit = min(len(opportunities), max_details) if max_details > 0 else len(opportunities)
    enriched_count = 0

    for i in range(limit):
        opp = opportunities[i]
        notice_id = opp.notice_id
        if not notice_id:
            continue

        # Skip if already has contacts
        if opp.point_of_contact:
            continue

        try:
            logger.info("Enriching %d/%d: %s...", i + 1, limit, opp.title[:60])
            contacts = await _scrape_detail_contacts(detail_page, notice_id, timeout_ms)
            if contacts:
                opp.point_of_contact = contacts
                enriched_count += 1
                logger.info("  -> Found %d contact(s)", len(contacts))
            else:
                logger.info("  -> No contacts found")
        except Exception as e:
            logger.error("  -> Error: %s", e)

        # Rate limit between detail pages
        if i < limit - 1:
            await asyncio.sleep(1.5)

    try:
        await detail_page.close()
    except Exception:
        pass

    logger.info("Enrichment complete: %d/%d opportunities got contacts", enriched_count, limit)
    return opportunities


async def _do_scrape_sam_pages(
    context,
    page,
    page_num: int,
    set_aside: Optional[str],
    ptype: Optional[str],
    naics_code: Optional[str],
    keyword: Optional[str],
    max_pages: int,
    enrich_contacts: Optional[bool],
) -> Dict[str, Any]:
    """
    Core SAM.gov scraping logic using an existing browser context and page.

    Returns SAMSearchResult-compatible dict.
    """
    all_opportunities: List[SAMOpportunity] = []
    pages_scraped = 0
    total_records = 0
    data_source = "none"

    for current_page in range(page_num, page_num + max_pages):
        search_url = _build_search_url(
            page_num=current_page,
            set_aside=set_aside,
            ptype=ptype,
            naics_code=naics_code,
            keyword=keyword,
        )
        logger.info("Scraping page %d: %s", current_page, search_url)

        captured_responses: List[Dict[str, Any]] = []

        async def handle_response(response):
            url = response.url
            if response.status != 200:
                return
            try:
                content_type = response.headers.get("content-type", "")
                if "json" not in content_type:
                    return
                if "/sgs/v1/search" in url or "/api/prod/" in url:
                    body = await response.json()
                    if isinstance(body, dict) and "_embedded" in body:
                        captured_responses.append(body)
                        return
                if "search" in url or "opportunities" in url:
                    body = await response.json()
                    if isinstance(body, dict):
                        if "opportunitiesData" in body or "_embedded" in body:
                            captured_responses.append(body)
            except Exception as e:
                logger.debug("Search XHR handler error: %s", e)

        page.on("response", handle_response)

        try:
            await page.goto(search_url, timeout=config.SCRAPE_TIMEOUT, wait_until="domcontentloaded")
        except Exception as e:
            logger.error("Navigation timeout on page %d: %s", current_page, e)
            page.remove_listener("response", handle_response)
            if pages_scraped == 0:
                raise RuntimeError(f"SAM.gov navigation timeout: {e}") from e
            break

        if current_page == page_num:
            await _handle_sam_consent(page)

        await _wait_for_sam_render(page, config.SAM_GOV_DETAIL_TIMEOUT)
        await asyncio.sleep(2)

        page.remove_listener("response", handle_response)

        # Strategy 1: Parse intercepted API data
        page_opportunities = []
        if captured_responses:
            logger.debug("Captured %d API response(s)", len(captured_responses))
            for resp_data in captured_responses:
                opps_list = (
                    resp_data.get("_embedded", {}).get("results")
                    or resp_data.get("opportunitiesData")
                    or []
                )

                if total_records == 0:
                    page_meta = resp_data.get("page", {})
                    total_records = (
                        page_meta.get("totalElements")
                        or resp_data.get("totalRecords")
                        or 0
                    )

                for opp_data in opps_list:
                    parsed = _parse_intercepted_opportunity(opp_data)
                    if parsed:
                        page_opportunities.append(parsed)
                if page_opportunities:
                    data_source = "xhr_interception"
                    break

        # Strategy 2: DOM fallback
        if not page_opportunities:
            logger.debug("No intercepted data, trying DOM extraction...")
            dom_opps = await _extract_opportunities_from_dom(page)
            for opp_data in dom_opps:
                parsed = _parse_intercepted_opportunity(opp_data)
                if parsed:
                    page_opportunities.append(parsed)
            if page_opportunities:
                data_source = "dom_fallback"

        if page_opportunities:
            all_opportunities.extend(page_opportunities)
            pages_scraped += 1
            logger.info("Page %d: found %d opportunities", current_page, len(page_opportunities))
        else:
            logger.info("Page %d: no opportunities found, stopping pagination", current_page)
            break

        if total_records > 0:
            total_pages_available = (total_records + config.SAM_GOV_PAGE_SIZE - 1) // config.SAM_GOV_PAGE_SIZE
            if current_page >= total_pages_available:
                break

        if current_page < page_num + max_pages - 1:
            await asyncio.sleep(1)

    # Enrich opportunities with contact info from detail pages
    should_enrich = enrich_contacts if enrich_contacts is not None else config.SAM_GOV_ENRICH_CONTACTS
    if all_opportunities and should_enrich:
        logger.info("Enriching contacts for up to %d opportunities...", config.SAM_GOV_MAX_DETAIL_PAGES)
        all_opportunities = await _enrich_opportunities_with_contacts(
            context=context,
            opportunities=all_opportunities,
            max_details=config.SAM_GOV_MAX_DETAIL_PAGES,
            timeout_ms=config.SAM_GOV_DETAIL_TIMEOUT,
        )

    # Calculate total pages
    if total_records > 0:
        total_pages = (total_records + config.SAM_GOV_PAGE_SIZE - 1) // config.SAM_GOV_PAGE_SIZE
    else:
        total_pages = pages_scraped
        total_records = len(all_opportunities)

    opps_serialized = [
        opp.model_dump(by_alias=True, exclude_none=True)
        for opp in all_opportunities
    ]

    return {
        "source": "sam_gov",
        "dataSource": data_source,
        "totalPages": total_pages,
        "pagesScraped": pages_scraped,
        "totalOpportunities": total_records,
        "opportunities": opps_serialized,
        "scrapedAt": datetime.utcnow().isoformat() + "Z",
    }


async def _scrape_with_playwright(
    page_num: int = 1,
    set_aside: Optional[str] = None,
    ptype: Optional[str] = None,
    naics_code: Optional[str] = None,
    keyword: Optional[str] = None,
    max_pages: int = 5,
    enrich_contacts: Optional[bool] = None,
    browser_context=None,
) -> Dict[str, Any]:
    """
    Scrape SAM.gov using Playwright browser automation.

    Args:
        page_num: Starting page number (1-based)
        set_aside: Set-aside type code
        ptype: Procurement type code
        naics_code: NAICS code filter
        keyword: Keyword search term
        max_pages: Maximum pages to scrape
        enrich_contacts: Fetch contacts from detail pages
        browser_context: Optional BrowserContext from the shared pool.

    Returns:
        SAMSearchResult-compatible dict
    """
    # Pool path: use provided context, skip standalone semaphore
    if browser_context is not None:
        page = await browser_context.new_page()
        try:
            return await _do_scrape_sam_pages(
                context=browser_context,
                page=page,
                page_num=page_num,
                set_aside=set_aside,
                ptype=ptype,
                naics_code=naics_code,
                keyword=keyword,
                max_pages=max_pages,
                enrich_contacts=enrich_contacts,
            )
        except Exception as e:
            logger.error("SAM.gov pool scrape failed: %s", e, exc_info=True)
            error_msg = str(e)
            return {
                "source": "sam_gov",
                "totalPages": 0,
                "pagesScraped": 0,
                "totalOpportunities": 0,
                "opportunities": [],
                "scrapedAt": datetime.utcnow().isoformat() + "Z",
                "error": f"SAM.gov scraping failed: {error_msg}",
            }
        finally:
            try:
                await page.close()
            except Exception:
                pass

    # Standalone path: launch own browser with semaphore guard
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return {
            "source": "sam_gov",
            "totalPages": 0,
            "pagesScraped": 0,
            "totalOpportunities": 0,
            "opportunities": [],
            "scrapedAt": datetime.utcnow().isoformat() + "Z",
            "error": "Playwright not installed. Run: pip install playwright && python3 -m playwright install chromium",
        }

    browser = None

    async with _get_sam_semaphore():
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=config.HEADLESS)
                context = await browser.new_context(user_agent=config.USER_AGENT)
                page = await context.new_page()

                result = await _do_scrape_sam_pages(
                    context=context,
                    page=page,
                    page_num=page_num,
                    set_aside=set_aside,
                    ptype=ptype,
                    naics_code=naics_code,
                    keyword=keyword,
                    max_pages=max_pages,
                    enrich_contacts=enrich_contacts,
                )

                await context.close()
                return result

        except Exception as e:
            logger.error("SAM.gov standalone scrape failed: %s", e, exc_info=True)
            error_msg = str(e)
            if "Executable doesn't exist" in error_msg or "browserType.launch" in error_msg:
                error_msg = "Chromium not installed. Run: python3 -m playwright install chromium"
            return {
                "source": "sam_gov",
                "totalPages": 0,
                "pagesScraped": 0,
                "totalOpportunities": 0,
                "opportunities": [],
                "scrapedAt": datetime.utcnow().isoformat() + "Z",
                "error": f"SAM.gov scraping failed: {error_msg}",
            }
        finally:
            if browser:
                try:
                    await browser.close()
                except Exception:
                    pass


def _parse_opportunity(opp: Dict[str, Any]) -> SAMOpportunity:
    """
    Parse a single opportunity from the API response into a SAMOpportunity model.

    Args:
        opp: Raw opportunity dict from the API

    Returns:
        SAMOpportunity model
    """
    # Extract point of contact
    contacts = []
    for poc in opp.get("pointOfContact", []):
        contacts.append(SAMPointOfContact(
            name=poc.get("fullName"),
            email=poc.get("email"),
            phone=poc.get("phone"),
            type=poc.get("type"),
        ))

    # Extract organization info
    org_path = opp.get("fullParentPathName", "")
    org_parts = [p.strip() for p in org_path.split(".")] if org_path else []
    department = org_parts[0] if org_parts else None
    agency = org_parts[1] if len(org_parts) > 1 else None

    # Extract place of performance
    pop = opp.get("placeOfPerformance", {})
    pop_parts = []
    if pop:
        city_info = pop.get("city", {})
        state_info = pop.get("state", {})
        country_info = pop.get("country", {})
        if city_info and city_info.get("name"):
            pop_parts.append(city_info["name"])
        if state_info and state_info.get("name"):
            pop_parts.append(state_info["name"])
        if country_info and country_info.get("name"):
            pop_parts.append(country_info["name"])
    place_of_performance = ", ".join(pop_parts) if pop_parts else None

    # Extract attachment/resource links
    attachment_links = opp.get("resourceLinks", []) or []

    # Build UI link
    notice_id = opp.get("noticeId", "")
    ui_link = opp.get("uiLink", "")
    if not ui_link and notice_id:
        ui_link = f"https://sam.gov/workspace/contract/opp/{notice_id}/view"

    return SAMOpportunity(
        title=opp.get("title", ""),
        solicitationNumber=opp.get("solicitationNumber"),
        noticeId=notice_id,
        department=department,
        agency=agency,
        postedDate=opp.get("postedDate"),
        responseDeadline=opp.get("responseDeadLine"),
        setAside=opp.get("typeOfSetAsideDescription") or opp.get("typeOfSetAside"),
        naicsCode=opp.get("naicsCode"),
        classificationCode=opp.get("classificationCode"),
        description=opp.get("description"),
        placeOfPerformance=place_of_performance,
        pointOfContact=contacts,
        attachmentLinks=attachment_links,
        sourceUrl=ui_link,
        noticeType=opp.get("type"),
    )


async def search_opportunities(
    days_back: int = 7,
    set_aside: Optional[str] = None,
    ptype: Optional[str] = None,
    naics_code: Optional[str] = None,
    keyword: Optional[str] = None,
    max_pages: int = 5,
    limit_per_page: int = 100,
    enrich_contacts: Optional[bool] = None,
    browser_context=None,
) -> Dict[str, Any]:
    """
    Search for contract opportunities on SAM.gov.

    If SAM_GOV_API_KEY is set, uses the public API at api.sam.gov.
    Otherwise, falls back to Playwright-based browser scraping.

    Args:
        days_back: Number of days to look back (default 7)
        set_aside: Set-aside type code (e.g., "SBA")
        ptype: Procurement type code (e.g., "o" for solicitations)
        naics_code: NAICS code filter
        keyword: Keyword to search in titles
        max_pages: Maximum number of pages to fetch (default 5)
        limit_per_page: Results per page (default 100, max 1000)
        enrich_contacts: Fetch contacts from detail pages (None = use config default)
        browser_context: Optional BrowserContext from the shared pool.

    Returns:
        SAMSearchResult-compatible dict with opportunities
    """
    # --- Playwright path (no API key) ---
    if not config.SAM_GOV_API_KEY:
        logger.info("No API key configured, using Playwright scraper")
        return await _scrape_with_playwright(
            page_num=1,
            set_aside=set_aside,
            ptype=ptype,
            naics_code=naics_code,
            keyword=keyword,
            max_pages=max_pages,
            enrich_contacts=enrich_contacts,
            browser_context=browser_context,
        )

    # --- API path (has API key) ---
    all_opportunities: List[SAMOpportunity] = []
    total_records = 0
    pages_scraped = 0

    for page in range(max_pages):
        offset = page * limit_per_page
        params = _build_search_params(
            days_back=days_back,
            set_aside=set_aside,
            ptype=ptype,
            naics_code=naics_code,
            keyword=keyword,
            limit=limit_per_page,
            offset=offset,
        )

        try:
            response = await asyncio.to_thread(
                lambda: requests.get(
                    config.SAM_GOV_API_URL,
                    params=params,
                    timeout=60,
                )
            )
            response.raise_for_status()
            data = response.json()

            total_records = data.get("totalRecords", 0)
            opps_data = data.get("opportunitiesData", [])

            for opp in opps_data:
                parsed = _parse_opportunity(opp)
                all_opportunities.append(parsed)

            pages_scraped += 1

            # Stop if we've fetched all records
            if offset + limit_per_page >= total_records:
                break

            # Rate limit: small delay between pages
            if page < max_pages - 1:
                await asyncio.sleep(0.5)

        except requests.exceptions.HTTPError as e:
            logger.error("API error on page %d: %s", page + 1, e)
            if e.response is not None and e.response.status_code == 401:
                return {
                    "source": "sam_gov",
                    "totalPages": 0,
                    "pagesScraped": 0,
                    "totalOpportunities": 0,
                    "opportunities": [],
                    "scrapedAt": datetime.utcnow().isoformat() + "Z",
                    "error": "Invalid SAM_GOV_API_KEY. Check your key at sam.gov > Account > API Key."
                }
            break
        except Exception as e:
            logger.error("Error on page %d: %s", page + 1, e)
            break

    total_pages = (total_records + limit_per_page - 1) // limit_per_page if total_records > 0 else 0

    # Serialize opportunities
    opps_serialized = [
        opp.model_dump(by_alias=True, exclude_none=True)
        for opp in all_opportunities
    ]

    return {
        "source": "sam_gov",
        "dataSource": "public_api",
        "totalPages": total_pages,
        "pagesScraped": pages_scraped,
        "totalOpportunities": total_records,
        "opportunities": opps_serialized,
        "scrapedAt": datetime.utcnow().isoformat() + "Z",
    }


def search_opportunities_sync(
    days_back: int = 7,
    set_aside: Optional[str] = None,
    ptype: Optional[str] = None,
    naics_code: Optional[str] = None,
    keyword: Optional[str] = None,
    max_pages: int = 5,
    enrich_contacts: Optional[bool] = None,
) -> Dict[str, Any]:
    """Synchronous wrapper for search_opportunities"""
    return asyncio.run(search_opportunities(
        days_back=days_back,
        set_aside=set_aside,
        ptype=ptype,
        naics_code=naics_code,
        keyword=keyword,
        max_pages=max_pages,
        enrich_contacts=enrich_contacts,
    ))


if __name__ == "__main__":
    print("Testing SAM.gov search...")
    if config.SAM_GOV_API_KEY:
        print(f"Using API key: {config.SAM_GOV_API_KEY[:8]}...")
    else:
        print("No API key — using Playwright scraper")
    result = search_opportunities_sync(days_back=7, set_aside="SBA", max_pages=1)
    print(f"Source: {result.get('source')}")
    print(f"Total opportunities: {result['totalOpportunities']}")
    print(f"Pages scraped: {result['pagesScraped']}")
    if result.get("error"):
        print(f"Error: {result['error']}")
    for opp in result["opportunities"][:3]:
        print(f"  - {opp.get('title', 'N/A')}")
        print(f"    Solicitation: {opp.get('solicitationNumber', 'N/A')}")
        print(f"    Deadline: {opp.get('responseDeadline', 'N/A')}")
