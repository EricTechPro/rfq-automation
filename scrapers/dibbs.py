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


async def handle_consent_banner(page: Page, return_url: str) -> bool:
    """
    Handle the DoD Notice and Consent Banner.

    After clicking OK, the page redirects away from the search URL.
    We need to navigate back to our original search URL.

    Returns True if banner was handled, False otherwise.
    """
    try:
        # Look for the OK button on consent banner
        ok_button = page.locator('input[type="submit"][value="OK"]')

        if await ok_button.count() > 0:
            print(f"[DEBUG] DIBBS: Consent banner found, clicking OK")
            await ok_button.click()
            await page.wait_for_load_state("networkidle")
            print(f"[DEBUG] DIBBS: Consent accepted, current URL: {page.url}")

            # After consent, the page redirects to a generic URL
            # Navigate back to our specific search URL
            print(f"[DEBUG] DIBBS: Navigating back to {return_url}")
            await page.goto(return_url, timeout=30000)
            await page.wait_for_load_state("networkidle")
            print(f"[DEBUG] DIBBS: Now at URL: {page.url}")
            return True

        print(f"[DEBUG] DIBBS: No consent banner found")
        return False
    except Exception as e:
        print(f"[DEBUG] DIBBS: Consent banner error: {e}")
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
                        # Column 3: Technical Documents
                        tech_docs = (await cells.nth(3).inner_text()).strip()

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
                                status=status,
                                prNumber=pr_number,
                                quantity=quantity,
                                issueDate=issue_date,
                                returnByDate=return_by_date
                            ))

    except Exception as e:
        # Log the error for debugging
        print(f"Error extracting solicitations: {e}")

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


async def scrape_dibbs(nsn: str) -> ScrapeResult:
    """
    Main function to scrape DIBBS for an NSN.

    Returns ScrapeResult with success status and data.
    """
    browser: Optional[Browser] = None
    clean_nsn = format_nsn(nsn)
    # Use rfqnsn.aspx for NSN detail page which has "Approved Source Data" table
    source_url = f"https://www.dibbs.bsm.dla.mil/rfq/rfqnsn.aspx?snsn={clean_nsn}"

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=config.HEADLESS)
            context = await browser.new_context(user_agent=config.USER_AGENT)
            page = await context.new_page()

            print(f"[DEBUG] DIBBS: Navigating to {source_url}")
            # Navigate to DIBBS
            await page.goto(source_url, timeout=config.SCRAPE_TIMEOUT)

            # Handle consent banner (pass source_url so we can return to it after consent)
            await handle_consent_banner(page, source_url)

            # Wait for page to stabilize
            await page.wait_for_load_state("networkidle")

            # Retry logic for data extraction
            rfq_data = None
            for attempt in range(config.MAX_RETRIES):
                print(f"[DEBUG] DIBBS: Extraction attempt {attempt + 1}/{config.MAX_RETRIES}")
                # Extract data
                nsn_found, nomenclature, amsc = await extract_header_info(page)
                approved_sources = await extract_approved_sources(page)
                solicitations = await extract_solicitations(page)

                print(f"[DEBUG] DIBBS: Found NSN={nsn_found}, sources={len(approved_sources)}, solicitations={len(solicitations)}")

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
