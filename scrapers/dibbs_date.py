"""
DIBBS Date-Based Scraper

Scrapes ALL NSNs from DIBBS for a given date.
Returns NSN list with metadata (does NOT get supplier contacts).

Also scrapes available dates from DIBBS RfqDates page.
"""

import re
import asyncio
from datetime import datetime
from typing import List, Dict, Any, Optional
from playwright.async_api import async_playwright, Page, Browser

import sys
sys.path.insert(0, str(__file__).rsplit("/", 2)[0])

from config import config
from scrapers.dibbs import handle_consent_banner


# URL for the dates listing page
DIBBS_DATES_URL = "https://www.dibbs.bsm.dla.mil/Rfq/RfqDates.aspx?category=issue"


async def scrape_available_dates() -> Dict[str, Any]:
    """
    Scrape available RFQ issue dates from DIBBS.

    Fetches the list of dates from the RfqDates.aspx page.

    Returns:
        Dictionary with:
        - dates: List of date strings in MM-DD-YYYY format
        - scrapedAt: Timestamp of scrape
    """
    browser: Optional[Browser] = None
    dates: List[str] = []

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=config.HEADLESS)
            context = await browser.new_context(user_agent=config.USER_AGENT)
            page = await context.new_page()

            # Navigate to dates page
            await page.goto(DIBBS_DATES_URL, timeout=config.SCRAPE_TIMEOUT)

            # Handle consent banner
            await handle_consent_banner(page, DIBBS_DATES_URL)

            # Wait for page to load
            await page.wait_for_load_state("networkidle")

            # Find all date links in the table
            # Dates are in format MM-DD-YYYY and are clickable links
            date_links = page.locator('a[href*="RfqRecs.aspx"]')
            count = await date_links.count()

            for i in range(count):
                link = date_links.nth(i)
                text = await link.inner_text()
                text = text.strip()

                # Validate date format (MM-DD-YYYY)
                if re.match(r'\d{2}-\d{2}-\d{4}', text):
                    dates.append(text)

            await context.close()

    except Exception as e:
        print(f"Error scraping available dates: {e}")

    finally:
        if browser:
            await browser.close()

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
    """
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
    except Exception:
        pass

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
    except Exception:
        pass

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
            await page.wait_for_load_state("networkidle")
            return True

        # Try clicking "Next" or ">" button
        next_button = page.locator('a:has-text("Next"), a:has-text(">"), input[value="Next"]').first
        if await next_button.count() > 0:
            await next_button.click()
            await page.wait_for_load_state("networkidle")
            return True

    except Exception:
        pass

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

    try:
        # Find the main data table
        tables = page.locator("table")
        table_count = await tables.count()

        for t in range(table_count):
            table = tables.nth(t)
            text = await table.inner_text()

            # Check if this is the RFQ results table
            if "NSN/Part Number" in text or "RFQ/Quote" in text:
                rows = table.locator("tr")
                row_count = await rows.count()

                # Skip header row (start at 1)
                for i in range(1, row_count):
                    row = rows.nth(i)
                    cells = row.locator("td")
                    cell_count = await cells.count()

                    # Need at least 9 columns
                    if cell_count >= 9:
                        # Column 5: Status - only process "Open"
                        status_text = (await cells.nth(5).inner_text()).strip()
                        status = status_text.split('\n')[0].strip()

                        if 'Open' not in status:
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

                break  # Found the table, stop searching

    except Exception as e:
        print(f"Error extracting NSNs from page: {e}")

    return nsns


async def scrape_nsns_by_date(
    date: str,
    max_pages: int = 0
) -> Dict[str, Any]:
    """
    Main function to scrape all NSNs from DIBBS for a given date.

    Args:
        date: Date in MM-DD-YYYY format (e.g., "01-12-2026")
        max_pages: Maximum pages to scrape (0 = all pages)

    Returns:
        Dictionary with date, total pages, NSN list, and metadata
    """
    browser: Optional[Browser] = None
    source_url = build_date_url(date)
    all_nsns: List[Dict[str, Any]] = []
    total_pages = 0
    pages_scraped = 0

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=config.HEADLESS)
            context = await browser.new_context(user_agent=config.USER_AGENT)
            page = await context.new_page()

            # Navigate to DIBBS date-filtered page
            await page.goto(source_url, timeout=config.SCRAPE_TIMEOUT)

            # Handle consent banner
            await handle_consent_banner(page, source_url)

            # Wait for page to stabilize
            await page.wait_for_load_state("networkidle")

            # Get total pages
            total_pages = await get_total_pages(page)

            # Determine pages to scrape
            pages_to_scrape = total_pages
            if max_pages > 0:
                pages_to_scrape = min(max_pages, total_pages)

            # Scrape each page
            for page_num in range(1, pages_to_scrape + 1):
                # Extract NSNs from current page
                page_nsns = await extract_nsns_from_page(page)
                all_nsns.extend(page_nsns)
                pages_scraped += 1

                # Navigate to next page if not the last
                if page_num < pages_to_scrape:
                    success = await click_next_page(page, page_num)
                    if not success:
                        break  # Can't navigate further

                    # Small delay between pages
                    await asyncio.sleep(0.5)

            await context.close()

    except Exception as e:
        print(f"Error scraping DIBBS by date: {e}")

    finally:
        if browser:
            await browser.close()

    return {
        "date": date,
        "totalPages": total_pages,
        "pagesScraped": pages_scraped,
        "totalNsns": len(all_nsns),
        "nsns": all_nsns,
        "scrapedAt": datetime.utcnow().isoformat() + "Z"
    }


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
