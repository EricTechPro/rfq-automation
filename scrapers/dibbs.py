"""
DIBBS Scraper

Scrapes RFQ data from the Defense Logistics Agency Internet Bid Board System (DIBBS).
"""

import re
import asyncio
from datetime import datetime
from typing import Optional, Tuple, List
from playwright.async_api import async_playwright, Page, Browser

import sys
sys.path.insert(0, str(__file__).rsplit("/", 2)[0])

from config import config
from models import ApprovedSource, Solicitation, RFQData, ScrapeResult


def format_nsn(nsn: str) -> str:
    """Remove dashes from NSN"""
    return nsn.replace("-", "")


async def handle_consent_banner(page: Page) -> bool:
    """
    Handle the DoD Notice and Consent Banner.

    Returns True if banner was clicked, False otherwise.
    """
    try:
        # Look for the OK button on consent banner
        ok_button = page.locator('input[type="submit"][value="OK"]')

        if await ok_button.count() > 0:
            await ok_button.click()
            await page.wait_for_load_state("networkidle")
            return True

        return False
    except Exception:
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

    except Exception:
        pass

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

    except Exception:
        pass

    return sources


async def extract_solicitations(page: Page) -> List[Solicitation]:
    """
    Extract solicitation data from tables.

    Table structure (6+ columns):
    - Solicitation Number (may have link)
    - Technical Documents
    - PR Number
    - Quantity
    - Issue Date
    - Return By Date
    """
    solicitations = []

    try:
        # Find tables with solicitation data
        tables = page.locator("table")
        table_count = await tables.count()

        for t in range(table_count):
            table = tables.nth(t)
            text = await table.inner_text()

            # Check if this is a solicitation table
            if "Solicitation #" in text or "PR #" in text:
                rows = table.locator("tr")
                row_count = await rows.count()

                # Skip header row
                for i in range(1, row_count):
                    row = rows.nth(i)
                    cells = row.locator("td")
                    cell_count = await cells.count()

                    if cell_count >= 6:
                        # Get solicitation number and URL
                        sol_cell = cells.nth(0)
                        sol_number = (await sol_cell.inner_text()).strip()

                        sol_url = None
                        link = sol_cell.locator("a")
                        if await link.count() > 0:
                            sol_url = await link.get_attribute("href")

                        tech_docs = (await cells.nth(1).inner_text()).strip()
                        pr_number = (await cells.nth(2).inner_text()).strip()

                        # Parse quantity
                        qty_text = (await cells.nth(3).inner_text()).strip()
                        try:
                            quantity = int(qty_text.replace(",", ""))
                        except ValueError:
                            quantity = 0

                        issue_date = (await cells.nth(4).inner_text()).strip()
                        return_by_date = (await cells.nth(5).inner_text()).strip()

                        if sol_number:
                            solicitations.append(Solicitation(
                                solicitationNumber=sol_number,
                                solicitationUrl=sol_url,
                                technicalDocuments=tech_docs or "None",
                                prNumber=pr_number,
                                quantity=quantity,
                                issueDate=issue_date,
                                returnByDate=return_by_date
                            ))

    except Exception:
        pass

    return solicitations


def has_open_rfqs(solicitations: List[Solicitation]) -> bool:
    """
    Check if any solicitation has an open RFQ.

    RFQ is open if return_by_date >= today.
    Date format: MM-DD-YYYY
    """
    today = datetime.now().date()

    for sol in solicitations:
        try:
            # Parse MM-DD-YYYY format
            return_date = datetime.strptime(sol.return_by_date, "%m-%d-%Y").date()
            if return_date >= today:
                return True
        except ValueError:
            continue

    return False


async def scrape_dibbs(nsn: str) -> ScrapeResult:
    """
    Main function to scrape DIBBS for an NSN.

    Returns ScrapeResult with success status and data.
    """
    browser: Optional[Browser] = None
    clean_nsn = format_nsn(nsn)
    source_url = f"{config.DIBBS_BASE_URL}?value={clean_nsn}"

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=config.HEADLESS)
            context = await browser.new_context(user_agent=config.USER_AGENT)
            page = await context.new_page()

            # Navigate to DIBBS
            await page.goto(source_url, timeout=config.SCRAPE_TIMEOUT)

            # Handle consent banner
            await handle_consent_banner(page)

            # Wait for page to stabilize
            await page.wait_for_load_state("networkidle")

            # Retry logic for data extraction
            rfq_data = None
            for attempt in range(config.MAX_RETRIES):
                # Extract data
                nsn_found, nomenclature, amsc = await extract_header_info(page)
                approved_sources = await extract_approved_sources(page)
                solicitations = await extract_solicitations(page)

                # Check if we got data
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

                # Wait and retry
                if attempt < config.MAX_RETRIES - 1:
                    await asyncio.sleep(config.RETRY_DELAY / 1000)
                    await page.reload()
                    await page.wait_for_load_state("networkidle")

            await context.close()

            if rfq_data:
                return ScrapeResult(success=True, data=rfq_data)
            else:
                return ScrapeResult(
                    success=False,
                    error="No data found after retries"
                )

    except Exception as e:
        return ScrapeResult(success=False, error=str(e))

    finally:
        if browser:
            await browser.close()


# Synchronous wrapper for non-async contexts
def scrape_dibbs_sync(nsn: str) -> ScrapeResult:
    """Synchronous wrapper for scrape_dibbs"""
    return asyncio.run(scrape_dibbs(nsn))
