"""
DIBBS Date-Based Scraper

Scrapes ALL NSNs from DIBBS for a given date.
Returns NSN list with metadata (does NOT get supplier contacts).

Also scrapes available dates from DIBBS RfqDates page.
"""

import re
import time
import random
import asyncio
from datetime import datetime
from typing import List, Dict, Any, Optional
from playwright.async_api import async_playwright, Page, Browser, TimeoutError as PlaywrightTimeoutError

import sys
sys.path.insert(0, str(__file__).rsplit("/", 2)[0])

from config import config
from scrapers.dibbs import handle_consent_banner, wait_for_idle
from utils.logging import get_logger

logger = get_logger(__name__)


# URL for the dates listing page
DIBBS_DATES_URL = "https://www.dibbs.bsm.dla.mil/Rfq/RfqDates.aspx?category=issue"


async def _do_scrape_available_dates(page) -> List[str]:
    """Core logic: extract dates from an existing page."""
    dates: List[str] = []

    await page.goto(DIBBS_DATES_URL, timeout=config.SCRAPE_TIMEOUT, wait_until="domcontentloaded")
    await handle_consent_banner(page, DIBBS_DATES_URL)
    await wait_for_idle(page)

    date_links = page.locator('a[href*="RfqRecs.aspx"]')
    count = await date_links.count()

    for i in range(count):
        link = date_links.nth(i)
        text = await link.inner_text()
        text = text.strip()
        if re.match(r'\d{2}-\d{2}-\d{4}', text):
            dates.append(text)

    return dates


async def scrape_available_dates(browser_context=None) -> Dict[str, Any]:
    """
    Scrape available RFQ issue dates from DIBBS.

    Args:
        browser_context: Optional BrowserContext from the shared pool.

    Returns:
        Dictionary with dates list and metadata.
    """
    dates: List[str] = []

    # Pool path
    if browser_context is not None:
        page = await browser_context.new_page()
        try:
            dates = await _do_scrape_available_dates(page)
        except Exception as e:
            logger.error("Error scraping available dates: %s", e, exc_info=True)
        finally:
            try:
                await page.close()
            except Exception:
                pass

        return {
            "dates": dates,
            "totalDates": len(dates),
            "scrapedAt": datetime.utcnow().isoformat() + "Z"
        }

    # Standalone path
    browser: Optional[Browser] = None
    context = None

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=config.HEADLESS)
            context = await browser.new_context(user_agent=config.USER_AGENT)
            page = await context.new_page()
            dates = await _do_scrape_available_dates(page)

    except Exception as e:
        logger.error("Error scraping available dates: %s", e, exc_info=True)

    finally:
        if context:
            try:
                await context.close()
            except Exception:
                pass
        if browser:
            try:
                await browser.close()
            except Exception:
                pass

    return {
        "dates": dates,
        "totalDates": len(dates),
        "scrapedAt": datetime.utcnow().isoformat() + "Z"
    }


def scrape_available_dates_sync() -> Dict[str, Any]:
    """Synchronous wrapper for scrape_available_dates"""
    return asyncio.run(scrape_available_dates())


def build_date_url(date: str) -> str:
    """
    Build the DIBBS URL for a specific date.

    Args:
        date: Date in MM-DD-YYYY format

    Returns:
        Full DIBBS URL for that date

    Raises:
        ValueError: If date is not in MM-DD-YYYY format
    """
    if not re.match(r'^\d{2}-\d{2}-\d{4}$', date):
        raise ValueError(
            f"Invalid date format: '{date}'. Expected MM-DD-YYYY (e.g., '01-15-2026')"
        )
    return f"https://www.dibbs.bsm.dla.mil/RFQ/RfqRecs.aspx?category=issue&TypeSrch=dt&Value={date}"


async def get_total_pages(page: Page) -> int:
    """
    Extract total number of pages from pagination.

    Returns:
        Total page count, or 1 if no pagination found
    """
    try:
        # Look for pagination text like "Page 1 of 5"
        pagination_text = await page.locator("text=/Page \\d+ of \\d+/").first.inner_text()
        match = re.search(r"Page \d+ of (\d+)", pagination_text)
        if match:
            return int(match.group(1))
    except Exception as e:
        logger.debug("get_total_pages pagination text error: %s", e)

    # Try alternative: look for page number links
    try:
        page_links = page.locator('a[href*="javascript:__doPostBack"]')
        count = await page_links.count()
        if count > 0:
            # Find highest page number
            max_page = 1
            for i in range(count):
                text = await page_links.nth(i).inner_text()
                if text.isdigit():
                    max_page = max(max_page, int(text))
            return max_page
    except Exception as e:
        logger.debug("get_total_pages page links error: %s", e)

    return 1


async def click_next_page(page: Page, current_page: int) -> bool:
    """
    Navigate to the next page using pagination.

    Args:
        page: Playwright page object
        current_page: Current page number (1-indexed)

    Returns:
        True if navigation successful, False otherwise
    """
    try:
        next_page = current_page + 1

        # Try clicking the next page number link
        next_link = page.locator(f'a:has-text("{next_page}")').first
        if await next_link.count() > 0:
            await next_link.click()
            await wait_for_idle(page)
            return True

        # Try clicking "Next" or ">" button
        next_button = page.locator('a:has-text("Next"), a:has-text(">"), input[value="Next"]').first
        if await next_button.count() > 0:
            await next_button.click()
            await wait_for_idle(page)
            return True

    except Exception as e:
        logger.error("click_next_page error: %s", e, exc_info=True)

    return False


async def extract_nsns_from_page(page: Page) -> List[Dict[str, Any]]:
    """
    Extract all NSN data from the current page.

    Table structure (RfqRecs.aspx - 9 columns):
    - Col 0: # (row number)
    - Col 1: NSN/Part Number
    - Col 2: Nomenclature (DESCRIPTION)
    - Col 3: Technical Documents
    - Col 4: Solicitation
    - Col 5: RFQ/Quote Status (Open, Removed, Cancelled)
    - Col 6: Purchase Request (PR # and QTY)
    - Col 7: Issued
    - Col 8: Return By

    Returns:
        List of NSN data dictionaries (only "Open" status)
    """
    nsns = []

    # Step 1: Find the data table — prefer direct ID, fall back to keyword search
    table = None
    table_selector = "#ctl00_cph1_grdRfqSearch"

    try:
        await page.wait_for_selector(table_selector, timeout=10000)
        table = page.locator(table_selector)
        if await table.count() > 0:
            logger.debug("extract_nsns: found data table by ID selector")
        else:
            table = None
    except Exception as e:
        logger.debug("extract_nsns: ID selector not found (%s), trying fallback", e)
        table = None

    if table is None:
        try:
            tables = page.locator("table")
            table_count = await tables.count()
            logger.debug("extract_nsns: fallback — scanning %d tables", table_count)
            for t in range(table_count):
                candidate = tables.nth(t)
                # Check header row only instead of full inner_text()
                header_row = candidate.locator("tr").first
                header_text = await header_row.inner_text()
                if "NSN/Part Number" in header_text or "RFQ/Quote" in header_text:
                    table = candidate
                    logger.debug("extract_nsns: found data table via fallback at index %d", t)
                    break
        except Exception as e:
            logger.error("extract_nsns: fallback table search failed: %s", e, exc_info=True)

    if table is None:
        logger.warning("extract_nsns: no data table found on page")
        return nsns

    # Step 2: Get direct-child rows to avoid nested pagination table rows
    try:
        rows = table.locator(":scope > tbody > tr")
        row_count = await rows.count()
        logger.debug("extract_nsns: found %d direct rows in table", row_count)
    except Exception as e:
        logger.error("extract_nsns: failed to locate rows: %s", e, exc_info=True)
        return nsns

    # Step 3: Extract data from each row
    # Row 0 = pagination, Row 1 = header, Row 2+ = data
    skipped_status = 0
    skipped_cells = 0
    extracted = 0

    for i in range(2, row_count):
        try:
            row = rows.nth(i)
            cells = row.locator("td")
            cell_count = await cells.count()

            if cell_count < 9:
                skipped_cells += 1
                logger.debug("extract_nsns: row %d has %d cells (need 9), skipping", i, cell_count)
                continue

            # Column 5: Status — only process "Open"
            status_text = (await cells.nth(5).inner_text()).strip()
            status = status_text.split('\n')[0].strip()

            if 'Open' not in status:
                skipped_status += 1
                continue

            # Column 1: NSN
            nsn_text = (await cells.nth(1).inner_text()).strip()
            nsn = nsn_text.split('\n')[0].strip()

            # Column 2: Nomenclature (Description)
            nomenclature = (await cells.nth(2).inner_text()).strip()

            # Column 4: Solicitation
            sol_text = (await cells.nth(4).inner_text()).strip()
            solicitation = sol_text.split('\n')[0].strip()

            # Column 6: Purchase Request (contains QTY)
            pr_text = (await cells.nth(6).inner_text()).strip()
            quantity = 0
            for line in pr_text.split('\n'):
                if 'QTY' in line.upper():
                    qty_match = re.search(r'(\d[\d,]*)', line)
                    if qty_match:
                        try:
                            quantity = int(qty_match.group(1).replace(",", ""))
                        except ValueError:
                            quantity = 0

            # Column 7: Issue Date
            issue_date = (await cells.nth(7).inner_text()).strip()

            # Column 8: Return By Date
            return_by_date = (await cells.nth(8).inner_text()).strip()

            if nsn:
                nsns.append({
                    "nsn": nsn,
                    "nomenclature": nomenclature,
                    "solicitation": solicitation,
                    "quantity": quantity,
                    "issueDate": issue_date,
                    "returnByDate": return_by_date
                })
                extracted += 1

        except Exception as e:
            logger.warning("extract_nsns: error processing row %d: %s", i, e)
            continue

    logger.info(
        "extract_nsns: extracted=%d, skipped_status=%d, skipped_cells=%d, total_rows=%d",
        extracted, skipped_status, skipped_cells, row_count
    )

    return nsns


async def _do_scrape_nsns_by_date(page, date: str, source_url: str, max_pages: int) -> Dict[str, Any]:
    """Core logic: scrape NSNs by date using an existing page."""
    all_nsns: List[Dict[str, Any]] = []
    total_pages = 0
    pages_scraped = 0
    error_msg = None

    start_time = time.monotonic()

    try:
        for attempt in range(config.MAX_RETRIES):
            try:
                await page.goto(source_url, timeout=config.SCRAPE_TIMEOUT, wait_until="domcontentloaded")
                logger.info("DIBBS date scraper: page loaded, URL=%s title=%s", page.url, await page.title())
                await handle_consent_banner(page, source_url)
                await wait_for_idle(page)
                logger.info("DIBBS date scraper: after consent, URL=%s title=%s", page.url, await page.title())
                break
            except PlaywrightTimeoutError:
                if attempt == config.MAX_RETRIES - 1:
                    raise
                delay = (config.RETRY_DELAY / 1000) * (2 ** attempt) + random.uniform(0, 1)
                logger.warning(
                    "DIBBS date page.goto timeout, retrying in %.1fs (attempt %d/%d)",
                    delay, attempt + 1, config.MAX_RETRIES
                )
                await asyncio.sleep(delay)

        total_pages = await get_total_pages(page)

        pages_to_scrape = total_pages
        if max_pages > 0:
            pages_to_scrape = min(max_pages, total_pages)

        logger.info(
            "DIBBS date scraper: pagination resolved, scraping %d of %d total pages",
            pages_to_scrape, total_pages,
            date=date,
        )

        for page_num in range(1, pages_to_scrape + 1):
            if time.monotonic() - start_time > 240:
                logger.warning("Pagination wall-clock limit (240s) hit at page %d/%d", page_num, pages_to_scrape)
                break

            page_nsns = await extract_nsns_from_page(page)
            all_nsns.extend(page_nsns)
            pages_scraped += 1

            logger.info(
                "DIBBS date scraper: page %d/%d extracted %d NSNs (%d cumulative)",
                page_num, pages_to_scrape, len(page_nsns), len(all_nsns),
            )

            if page_num < pages_to_scrape:
                success = await click_next_page(page, page_num)
                if not success:
                    break
                await asyncio.sleep(config.BATCH_DELAY / 1000)

    except ValueError:
        raise
    except Exception as e:
        error_msg = str(e)
        logger.error("Error scraping by date: %s", e, exc_info=True)

    elapsed = time.monotonic() - start_time
    logger.info(
        "DIBBS date scraper: finished in %.1fs, %d NSNs from %d pages",
        elapsed, len(all_nsns), pages_scraped,
        date=date,
        error=error_msg,
    )

    result = {
        "date": date,
        "totalPages": total_pages,
        "pagesScraped": pages_scraped,
        "totalNsns": len(all_nsns),
        "nsns": all_nsns,
        "scrapedAt": datetime.utcnow().isoformat() + "Z"
    }
    if error_msg:
        result["error"] = error_msg
    return result


async def scrape_nsns_by_date(
    date: str,
    max_pages: int = 0,
    browser_context=None,
) -> Dict[str, Any]:
    """
    Main function to scrape all NSNs from DIBBS for a given date.

    Args:
        date: Date in MM-DD-YYYY format (e.g., "01-12-2026")
        max_pages: Maximum pages to scrape (0 = all pages)
        browser_context: Optional BrowserContext from the shared pool.

    Returns:
        Dictionary with date, total pages, NSN list, and metadata
    """
    source_url = build_date_url(date)
    logger.info("scrape_nsns_by_date: starting", date=date, max_pages=max_pages, url=source_url)

    # Pool path
    if browser_context is not None:
        page = await browser_context.new_page()
        try:
            return await _do_scrape_nsns_by_date(page, date, source_url, max_pages)
        finally:
            try:
                await page.close()
            except Exception:
                pass

    # Standalone path
    browser: Optional[Browser] = None
    context = None

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=config.HEADLESS)
            context = await browser.new_context(user_agent=config.USER_AGENT)
            page = await context.new_page()
            return await _do_scrape_nsns_by_date(page, date, source_url, max_pages)

    except ValueError:
        raise
    except Exception as e:
        logger.error("Error scraping by date: %s", e, exc_info=True)
        result = {
            "date": date,
            "totalPages": 0,
            "pagesScraped": 0,
            "totalNsns": 0,
            "nsns": [],
            "scrapedAt": datetime.utcnow().isoformat() + "Z",
            "error": str(e),
        }
        return result

    finally:
        if context:
            try:
                await context.close()
            except Exception:
                pass
        if browser:
            try:
                await browser.close()
            except Exception:
                pass


# Synchronous wrapper for non-async contexts
def scrape_nsns_by_date_sync(date: str, max_pages: int = 0) -> Dict[str, Any]:
    """Synchronous wrapper for scrape_nsns_by_date"""
    return asyncio.run(scrape_nsns_by_date(date, max_pages))


if __name__ == "__main__":
    # Test with today's date
    from datetime import date as dt
    today = dt.today().strftime("%m-%d-%Y")
    print(f"Testing with date: {today}")
    result = scrape_nsns_by_date_sync(today, max_pages=1)
    print(f"Found {result['totalNsns']} NSNs on page 1")
    for nsn in result['nsns'][:5]:
        print(f"  - {nsn['nsn']}: {nsn['nomenclature']}")
