"""
Canada Buys Scraper

Fetches tender opportunities from the Canadian government procurement portal.
Primary: Open Data CSV feed (100% date/contact coverage, updated every 2 hours).
Fallback: HTML table parsing via httpx.

CSV feeds: https://canadabuys.canada.ca/opendata/pub/
Web UI: https://canadabuys.canada.ca/en/tender-opportunities

CSV columns (67 total, key ones):
- title-titre-eng, referenceNumber-numeroReference, solicitationNumber-numeroSollicitation
- publicationDate-datePublication, tenderClosingDate-appelOffresDateCloture
- tenderStatus-appelOffresStatut-eng, procurementCategory-categorieApprovisionnement
- noticeType-avisType-eng, contractingEntityName-nomEntitContractante-eng
- contactInfoName-informationsContactNom, contactInfoEmail-informationsContactCourriel
- tenderDescription-descriptionAppelOffres-eng, attachment-piecesJointes-eng
- regionsOfDelivery-regionsLivraison-eng, regionsOfOpportunity-regionAppelOffres-eng

NOTE: CSV feeds only include federal government tenders. The HTML fallback
includes all levels of government (provincial, territorial, municipal).
"""

import asyncio
import csv
import io
import re
from datetime import datetime, timedelta
from typing import Optional, List

import httpx

import sys
sys.path.insert(0, str(__file__).rsplit("/", 2)[0])

from config import config
from utils.logging import get_logger

logger = get_logger(__name__)

CANADA_BUYS_BASE = "https://canadabuys.canada.ca"
SEARCH_URL = f"{CANADA_BUYS_BASE}/en/tender-opportunities"

# Open Data CSV feeds (no auth required, updated regularly)
CSV_OPEN_TENDERS = f"{CANADA_BUYS_BASE}/opendata/pub/openTenderNotice-ouvertAvisAppelOffres.csv"
CSV_NEW_TENDERS = f"{CANADA_BUYS_BASE}/opendata/pub/newTenderNotice-nouvelAvisAppelOffres.csv"


def _normalize_csv_tender(row: dict) -> dict:
    """Normalize a CSV row into our standard tender format."""
    # Parse closing date (ISO 8601 with time, e.g. 2026-02-20T14:00:00)
    closing_raw = row.get("tenderClosingDate-appelOffresDateCloture", "")
    closing_date = closing_raw[:10] if closing_raw else ""

    # Map procurement category codes to readable names
    cat_code = (row.get("procurementCategory-categorieApprovisionnement", "") or "").strip("* ")
    category_map = {"GD": "Goods", "SRV": "Services", "CNST": "Construction", "SVRTGD": "Services related to goods"}
    category = category_map.get(cat_code, cat_code)

    ref = row.get("referenceNumber-numeroReference", "")
    notice_url = row.get("noticeURL-URLavis-eng", "")
    source_url = notice_url if notice_url else (
        f"{CANADA_BUYS_BASE}/en/tender-opportunities/tender-notice/{ref}" if ref else ""
    )

    return {
        "title": row.get("title-titre-eng", ""),
        "solicitationNumber": row.get("solicitationNumber-numeroSollicitation", "") or ref,
        "status": row.get("tenderStatus-appelOffresStatut-eng", "Open"),
        "publishedDate": row.get("publicationDate-datePublication", ""),
        "closingDate": closing_date,
        "category": category,
        "region": (row.get("regionsOfDelivery-regionsLivraison-eng", "") or "").strip("* "),
        "organization": row.get("contractingEntityName-nomEntitContractante-eng", ""),
        "procurementType": row.get("noticeType-avisType-eng", ""),
        "contactName": row.get("contactInfoName-informationsContactNom", ""),
        "contactEmail": row.get("contactInfoEmail-informationsContactCourriel", ""),
        "description": (row.get("tenderDescription-descriptionAppelOffres-eng", "") or "")[:500],
        "sourceUrl": source_url,
        "source": "canada_buys",
    }


def _normalize_html_tender(raw: dict) -> dict:
    """Normalize an HTML-parsed tender into our standard format."""
    return {
        "title": raw.get("title", ""),
        "solicitationNumber": raw.get("solicitationNumber", ""),
        "status": raw.get("status", "Open"),
        "publishedDate": raw.get("publishedDate", ""),
        "closingDate": raw.get("closingDate", ""),
        "category": raw.get("category", ""),
        "region": raw.get("region", ""),
        "organization": raw.get("organization", ""),
        "procurementType": raw.get("procurementType", ""),
        "contactName": "",
        "contactEmail": "",
        "description": "",
        "sourceUrl": raw.get("sourceUrl", ""),
        "source": "canada_buys",
    }


def _parse_html_date(date_str: str) -> str:
    """Parse a Canada Buys HTML date string (YYYY/MM/DD) to ISO format."""
    date_str = date_str.strip()
    if not date_str or date_str == "9999/12/31":
        return ""
    try:
        dt = datetime.strptime(date_str[:10], "%Y/%m/%d")
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        return date_str


async def search_tenders(
    keywords: Optional[str] = None,
    days_back: int = 7,
    max_results: int = 200,
) -> dict:
    """
    Search Canada Buys for tender opportunities.

    Primary: Open Data CSV feed (complete data with dates and contacts).
    Fallback: HTML table parsing via httpx.

    Args:
        keywords: Optional keyword filter for titles/descriptions
        days_back: Number of days to look back
        max_results: Maximum results to return

    Returns:
        Dict with source, tenders list, metadata
    """
    # Try CSV feed first (richest data, 100% date coverage)
    try:
        tenders = await _fetch_csv(keywords, days_back, max_results)
        if tenders:
            return {
                "source": "canada_buys_csv",
                "totalTenders": len(tenders),
                "tenders": tenders,
                "scrapedAt": datetime.utcnow().isoformat() + "Z",
            }
    except Exception as e:
        logger.warning("CSV feed failed, falling back to HTML parsing: %s", e)

    # Fallback to HTML table parsing
    try:
        tenders = await _fetch_html(keywords, days_back, max_results)
        if tenders:
            return {
                "source": "canada_buys_html",
                "totalTenders": len(tenders),
                "tenders": tenders,
                "scrapedAt": datetime.utcnow().isoformat() + "Z",
            }
    except Exception as e:
        logger.error("HTML parsing failed: %s", e, exc_info=True)

    return {
        "source": "canada_buys",
        "totalTenders": 0,
        "tenders": [],
        "scrapedAt": datetime.utcnow().isoformat() + "Z",
    }


async def _fetch_csv(
    keywords: Optional[str],
    days_back: int,
    max_results: int,
) -> list:
    """
    Fetch tender data from the Canada Buys Open Data CSV feed.

    Uses the "open tender notices" file which contains all currently open
    federal tenders with 100% date coverage and contact information.
    Updated daily at 7:00-8:30 AM ET.
    """
    cutoff = datetime.utcnow() - timedelta(days=days_back)
    keyword_pattern = re.compile(re.escape(keywords), re.IGNORECASE) if keywords else None
    tenders: List[dict] = []

    headers = {
        "User-Agent": config.USER_AGENT,
        "Accept": "text/csv,text/plain,*/*",
    }

    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=60,
        headers=headers,
    ) as client:
        response = await client.get(CSV_OPEN_TENDERS)
        response.raise_for_status()

        # Parse CSV (UTF-8 with BOM)
        text = response.text.lstrip("\ufeff")
        reader = csv.DictReader(io.StringIO(text))

        for row in reader:
            if len(tenders) >= max_results:
                break

            # Filter by publication date
            pub_date = row.get("publicationDate-datePublication", "")
            if pub_date:
                try:
                    pub_dt = datetime.strptime(pub_date, "%Y-%m-%d")
                    if pub_dt < cutoff:
                        continue
                except ValueError:
                    pass

            # Filter by keywords (search title and description)
            if keyword_pattern:
                title = row.get("title-titre-eng", "")
                desc = row.get("tenderDescription-descriptionAppelOffres-eng", "")
                if not keyword_pattern.search(title) and not keyword_pattern.search(desc):
                    continue

            tenders.append(_normalize_csv_tender(row))

    logger.info("CSV feed returned %d tenders", len(tenders))
    return tenders


async def _fetch_html(
    keywords: Optional[str],
    days_back: int,
    max_results: int,
) -> list:
    """
    Fetch and parse tender data from the Canada Buys HTML page.

    Fallback for when CSV feed is unavailable. Includes all levels of
    government (not just federal). 50 items per page.
    """
    cutoff = datetime.utcnow() - timedelta(days=days_back)
    keyword_pattern = re.compile(re.escape(keywords), re.IGNORECASE) if keywords else None
    tenders: List[dict] = []

    headers = {
        "User-Agent": config.USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }

    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=30,
        headers=headers,
    ) as client:
        page_num = 0
        max_pages = (max_results // 50) + 2

        while page_num < max_pages and len(tenders) < max_results:
            params = {}
            if keywords:
                params["search_api_fulltext"] = keywords
            if page_num > 0:
                params["page"] = str(page_num)

            response = await client.get(SEARCH_URL, params=params)
            response.raise_for_status()

            page_tenders = _parse_table_html(response.text, cutoff, keyword_pattern)
            if not page_tenders:
                break

            tenders.extend(page_tenders)
            page_num += 1

            if page_num < max_pages and len(tenders) < max_results:
                await asyncio.sleep(0.5)

    logger.info("HTML parsed %d tenders from %d page(s)", len(tenders), page_num)
    return tenders[:max_results]


def _parse_table_html(html: str, cutoff: datetime, keyword_pattern) -> list:
    """
    Parse tender table rows from the HTML.

    Each table row has 5 cells:
    0: Title (with link to /tender-notice/{uuid})
    1: Category (Goods, Services, Construction)
    2: Open/amendment date (YYYY/MM/DD)
    3: Closing date (YYYY/MM/DD or 9999/12/31 for none)
    4: Organization
    """
    tenders = []
    row_pattern = re.compile(r'<tr[^>]*>(.*?)</tr>', re.DOTALL)

    for row_match in row_pattern.finditer(html):
        row_html = row_match.group(1)

        link_match = re.search(
            r'<a[^>]*href="(/en/tender-opportunities/tender-notice/([^"]+))"[^>]*>([^<]+)</a>',
            row_html
        )
        if not link_match:
            continue

        href = link_match.group(1)
        tender_id = link_match.group(2)
        title = link_match.group(3).strip()

        if not title or len(title) < 3:
            continue

        if keyword_pattern and not keyword_pattern.search(title):
            continue

        cells = re.findall(r'<td[^>]*>(.*?)</td>', row_html, re.DOTALL)
        clean_cells = [re.sub(r'<[^>]+>', ' ', c).strip() for c in cells]

        category = clean_cells[1] if len(clean_cells) > 1 else ""
        open_date_str = clean_cells[2] if len(clean_cells) > 2 else ""
        close_date_str = clean_cells[3] if len(clean_cells) > 3 else ""
        organization = clean_cells[4] if len(clean_cells) > 4 else ""

        published_date = _parse_html_date(open_date_str)
        closing_date = _parse_html_date(close_date_str)

        if published_date:
            try:
                pub_dt = datetime.strptime(published_date, "%Y-%m-%d")
                if pub_dt < cutoff:
                    continue
            except ValueError:
                pass

        source_url = f"{CANADA_BUYS_BASE}{href}"

        tenders.append(_normalize_html_tender({
            "title": title,
            "solicitationNumber": tender_id,
            "status": "Open",
            "publishedDate": published_date,
            "closingDate": closing_date,
            "category": category,
            "organization": organization,
            "sourceUrl": source_url,
        }))

    return tenders


def search_tenders_sync(keywords=None, days_back=7) -> dict:
    """Synchronous wrapper."""
    return asyncio.run(search_tenders(keywords=keywords, days_back=days_back))
