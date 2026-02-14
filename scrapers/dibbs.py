"""
DIBBS Scraper

Scrapes RFQ data from the Defense Logistics Agency Internet Bid Board System (DIBBS).
"""

import re
import random
import asyncio
from datetime import datetime
from typing import Optional, Tuple, List
from playwright.async_api import async_playwright, Page, Browser, TimeoutError as PlaywrightTimeoutError

import sys
sys.path.insert(0, str(__file__).rsplit("/", 2)[0])

from config import config
from models import ApprovedSource, Solicitation, RFQData, ScrapeResult
from utils.helpers import format_nsn
from utils.logging import get_logger

logger = get_logger(__name__)


async def wait_for_idle(page: Page, timeout_ms: int = 15000) -> None:
    """Wait for networkidle with a timeout — logs warning and continues if it fires."""
    try:
        await page.wait_for_load_state("networkidle", timeout=timeout_ms)
    except PlaywrightTimeoutError:
        logger.warning("networkidle timed out after %dms, continuing", timeout_ms)


async def handle_consent_banner(page: Page, return_url: str) -> bool:
    """
    Handle the DoD Notice and Consent Banner.

    After clicking OK, the page redirects away from the search URL.
    We need to navigate back to our original search URL.

    Returns True if banner was handled, False otherwise.
    """
    try:
        # Look for the OK button on consent banner
        ok_button = page.locator('input[type="submit"][value="OK"], button:has-text("OK")')

        if await ok_button.count() > 0:
            logger.debug("DIBBS: Consent banner found, clicking OK")
            await ok_button.click()
            await wait_for_idle(page)
            logger.debug("DIBBS: Consent accepted, current URL: %s", page.url)

            # After consent, the page redirects to a generic URL
            # Navigate back to our specific search URL
            logger.debug("DIBBS: Navigating back to %s", return_url)
            await page.goto(return_url, timeout=config.SCRAPE_TIMEOUT, wait_until="domcontentloaded")
            await wait_for_idle(page)
            logger.debug("DIBBS: Now at URL: %s", page.url)
            return True

        logger.debug("DIBBS: No consent banner found")
        return False
    except Exception as e:
        logger.warning("DIBBS: Consent banner error: %s", e)
        return False


async def extract_header_info(page: Page) -> Tuple[str, str, str]:
    """
    Extract NSN, nomenclature, and AMSC from the page header.

    Returns (nsn, nomenclature, amsc)
    """
    nsn = ""
    nomenclature = ""
    amsc = ""

    try:
        # Get the first fieldset which contains header info
        fieldset = page.locator("fieldset").first
        text = await fieldset.inner_text()

        # Extract NSN
        nsn_match = re.search(r"NSN:\s*([\d-]+)", text)
        if nsn_match:
            nsn = nsn_match.group(1)

        # Extract Nomenclature (may contain commas)
        nom_match = re.search(r"Nomenclature:\s*(.+?)(?:\s*AMSC:|$)", text, re.DOTALL)
        if nom_match:
            nomenclature = nom_match.group(1).strip()

        # Extract AMSC
        amsc_match = re.search(r"AMSC:\s*(\w+)", text)
        if amsc_match:
            amsc = amsc_match.group(1)

    except Exception as e:
        logger.error("extract_header_info error: %s", e, exc_info=True)

    return nsn, nomenclature, amsc


async def extract_approved_sources(page: Page) -> List[ApprovedSource]:
    """
    Extract approved sources from the Approved Source Data table.

    Table structure:
    - Column 1: CAGE Code
    - Column 2: Part Number
    - Column 3: Company Name
    """
    sources = []

    try:
        # Find the Approved Source Data fieldset
        fieldset = page.locator('fieldset:has-text("Approved Source Data")')
        table = fieldset.locator("table").first

        if await table.count() > 0:
            rows = table.locator("tr")
            row_count = await rows.count()

            # Skip header row (start at 1)
            for i in range(1, row_count):
                row = rows.nth(i)
                cells = row.locator("td")
                cell_count = await cells.count()

                if cell_count >= 3:
                    cage_code = (await cells.nth(0).inner_text()).strip()
                    part_number = (await cells.nth(1).inner_text()).strip()
                    company_name = (await cells.nth(2).inner_text()).strip()

                    # Validate CAGE code (5 alphanumeric, not starting with SPE)
                    if cage_code and not cage_code.startswith("SPE") and len(cage_code) == 5:
                        sources.append(ApprovedSource(
                            cageCode=cage_code,
                            partNumber=part_number,
                            companyName=company_name
                        ))

    except Exception as e:
        logger.error("extract_approved_sources error: %s", e, exc_info=True)

    return sources


async def extract_solicitations(page: Page) -> List[Solicitation]:
    """
    Extract solicitation data from the RFQ search results table.

    Table structure on RFQRecs.aspx (9 columns):
    - # (row number)
    - NSN/Part Number
    - Nomenclature
    - Technical Documents
    - Solicitation (with link)
    - RFQ/Quote Status (Open, Removed, Cancelled) <-- KEY COLUMN
    - Purchase Request (PR # and QTY)
    - Issued
    - Return By
    """
    solicitations = []

    try:
        # Find the main data table - it contains NSN/Part Number header
        tables = page.locator("table")
        table_count = await tables.count()

        for t in range(table_count):
            table = tables.nth(t)
            text = await table.inner_text()

            # Check if this is the RFQ results table (has NSN/Part Number column)
            if "NSN/Part Number" in text or "RFQ/Quote" in text:
                rows = table.locator("tr")
                row_count = await rows.count()

                # Skip header row (start at 1)
                for i in range(1, row_count):
                    row = rows.nth(i)
                    cells = row.locator("td")
                    cell_count = await cells.count()

                    # Need at least 8 columns for the full table
                    if cell_count >= 8:
                        # Column 3: Technical Documents (text + download URLs)
                        tech_docs_cell = cells.nth(3)
                        tech_docs = (await tech_docs_cell.inner_text()).strip()

                        # Extract document download URLs from links
                        doc_urls = []
                        doc_links = tech_docs_cell.locator("a")
                        doc_link_count = await doc_links.count()
                        for dl in range(doc_link_count):
                            href = await doc_links.nth(dl).get_attribute("href")
                            if href:
                                if not href.startswith("http"):
                                    href = f"https://www.dibbs.bsm.dla.mil{href}"
                                doc_urls.append(href)

                        # Column 4: Solicitation (with link)
                        sol_cell = cells.nth(4)
                        sol_number = (await sol_cell.inner_text()).strip()
                        # Clean up - remove "Package View" and other extra text
                        sol_number = sol_number.split('\n')[0].strip()

                        sol_url = None
                        link = sol_cell.locator("a").first
                        if await link.count() > 0:
                            sol_url = await link.get_attribute("href")

                        # Column 5: RFQ/Quote Status - THIS IS THE KEY COLUMN
                        status_cell = cells.nth(5)
                        status_text = (await status_cell.inner_text()).strip()
                        # Clean up status - extract just the status word
                        # Status can be: "Open", "Removed", "Cancelled"
                        status = status_text.split('\n')[0].strip()
                        # Remove any extra characters like vote icons
                        if 'Open' in status:
                            status = 'Open'
                        elif 'Removed' in status:
                            status = 'Removed'
                        elif 'Cancel' in status:
                            status = 'Cancelled'

                        # Column 6: Purchase Request (contains PR # and QTY on separate lines)
                        pr_cell = cells.nth(6)
                        pr_text = (await pr_cell.inner_text()).strip()
                        pr_lines = pr_text.split('\n')
                        pr_number = pr_lines[0].strip() if pr_lines else ""

                        # Parse quantity from "QTY: XXX" line
                        quantity = 0
                        for line in pr_lines:
                            if 'QTY' in line.upper():
                                qty_match = re.search(r'(\d[\d,]*)', line)
                                if qty_match:
                                    try:
                                        quantity = int(qty_match.group(1).replace(",", ""))
                                    except ValueError:
                                        quantity = 0

                        # Column 7: Issued date
                        issue_date = (await cells.nth(7).inner_text()).strip()

                        # Column 8: Return By date
                        return_by_date = (await cells.nth(8).inner_text()).strip()

                        if sol_number:
                            solicitations.append(Solicitation(
                                solicitationNumber=sol_number,
                                solicitationUrl=sol_url,
                                technicalDocuments=tech_docs or "None",
                                documentUrls=doc_urls,
                                status=status,
                                prNumber=pr_number,
                                quantity=quantity,
                                issueDate=issue_date,
                                returnByDate=return_by_date
                            ))

    except Exception as e:
        logger.error("Error extracting solicitations: %s", e, exc_info=True)

    return solicitations


def has_open_rfqs(solicitations: List[Solicitation]) -> bool:
    """
    Check if any solicitation has an open RFQ.

    RFQ is open if the status field is "Open".
    Status values from DIBBS: Open, Removed, Cancelled
    """
    for sol in solicitations:
        # Check the actual status from the RFQ/Quote Status column
        if sol.status.lower() == "open":
            return True

    return False


async def check_dibbs_health(page: Page) -> bool:
    """Fast health check — can DIBBS respond within 10s?"""
    try:
        await page.goto(
            "https://www.dibbs.bsm.dla.mil/rfq/",
            timeout=10000,
            wait_until="domcontentloaded",
        )
        return True
    except Exception as e:
        logger.warning("DIBBS health check failed: %s", e)
        return False


async def _do_scrape_dibbs(page: Page, nsn: str, source_url: str) -> ScrapeResult:
    """
    Core DIBBS scraping logic operating on an existing page.

    Handles consent banner, retries, and data extraction.
    """
    try:
        # Quick health check before committing to expensive retries
        if not await check_dibbs_health(page):
            return ScrapeResult(
                success=False,
                error="DIBBS unreachable (health check failed)"
            )

        # Retry logic for initial navigation (handles IP throttling / timeouts)
        for attempt in range(config.MAX_RETRIES):
            try:
                logger.debug("DIBBS: Navigating to %s", source_url)
                await page.goto(source_url, timeout=config.SCRAPE_TIMEOUT, wait_until="domcontentloaded")

                # Handle consent banner (pass source_url so we can return to it after consent)
                await handle_consent_banner(page, source_url)

                # Wait for page to stabilize
                await wait_for_idle(page)
                break
            except PlaywrightTimeoutError:
                if attempt == config.MAX_RETRIES - 1:
                    raise
                delay = (config.RETRY_DELAY / 1000) * (2 ** attempt) + random.uniform(0, 1)
                logger.warning(
                    "DIBBS page.goto timeout for NSN %s, retrying in %.1fs (attempt %d/%d)",
                    nsn, delay, attempt + 1, config.MAX_RETRIES
                )
                await asyncio.sleep(delay)

        # Retry logic for data extraction
        rfq_data = None
        for attempt in range(config.MAX_RETRIES):
            logger.debug("DIBBS: Extraction attempt %d/%d", attempt + 1, config.MAX_RETRIES)
            nsn_found, nomenclature, amsc = await extract_header_info(page)
            approved_sources = await extract_approved_sources(page)
            solicitations = await extract_solicitations(page)

            logger.debug("DIBBS: Found NSN=%s, sources=%d, solicitations=%d", nsn_found, len(approved_sources), len(solicitations))

            if nsn_found or approved_sources or solicitations:
                rfq_data = RFQData(
                    nsn=nsn_found or nsn,
                    nomenclature=nomenclature,
                    amsc=amsc,
                    approvedSources=approved_sources,
                    solicitations=solicitations,
                    hasOpenRFQs=has_open_rfqs(solicitations),
                    scrapedAt=datetime.utcnow().isoformat() + "Z",
                    sourceUrl=source_url
                )
                break

            if attempt < config.MAX_RETRIES - 1:
                delay = (config.RETRY_DELAY / 1000) * (2 ** attempt) + random.uniform(0, 0.5)
                logger.warning("DIBBS: No data found, retrying in %.1fs (attempt %d/%d)",
                              delay, attempt + 1, config.MAX_RETRIES)
                await asyncio.sleep(delay)
                await page.reload()
                await wait_for_idle(page)

        if rfq_data:
            return ScrapeResult(success=True, data=rfq_data)
        else:
            return ScrapeResult(success=False, error="No data found after retries")

    except Exception as e:
        logger.error("_do_scrape_dibbs failed for NSN %s: %s", nsn, e, exc_info=True)
        return ScrapeResult(success=False, error=str(e))


async def scrape_dibbs(nsn: str, browser_context=None) -> ScrapeResult:
    """
    Main function to scrape DIBBS for an NSN.

    Args:
        nsn: The NSN to scrape
        browser_context: Optional BrowserContext from the shared pool.
            If provided, creates a page from it (FastAPI path).
            If None, launches a standalone browser (CLI/Streamlit path).

    Returns ScrapeResult with success status and data.
    """
    clean_nsn = format_nsn(nsn)
    source_url = f"https://www.dibbs.bsm.dla.mil/rfq/rfqnsn.aspx?snsn={clean_nsn}"

    # Pool path: use provided context
    if browser_context is not None:
        page = await browser_context.new_page()
        try:
            return await _do_scrape_dibbs(page, nsn, source_url)
        finally:
            try:
                await page.close()
            except Exception:
                pass

    # Standalone path: launch own browser
    browser: Optional[Browser] = None
    context = None
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=config.HEADLESS)
            context = await browser.new_context(user_agent=config.USER_AGENT)
            page = await context.new_page()
            return await _do_scrape_dibbs(page, nsn, source_url)

    except Exception as e:
        logger.error("scrape_dibbs standalone failed for NSN %s: %s", nsn, e, exc_info=True)
        return ScrapeResult(success=False, error=str(e))

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
