"""
WBParts Scraper

Scrapes manufacturer and technical data from WBParts.com.
"""

import re
import asyncio
from datetime import datetime
from typing import Optional, List, Tuple
from playwright.async_api import async_playwright, Page, Browser

import sys
sys.path.insert(0, str(__file__).rsplit("/", 2)[0])

from config import config
from models import WBPartsManufacturer, WBPartsTechSpec, WBPartsDemand, WBPartsData, WBPartsScrapeResult


def format_nsn_with_dashes(nsn: str) -> str:
    """
    Format NSN with dashes.

    Input: "4520012619675" or "4520-01-261-9675"
    Output: "4520-01-261-9675"
    """
    clean = nsn.replace("-", "")
    if len(clean) != 13:
        return nsn
    return f"{clean[:4]}-{clean[4:6]}-{clean[6:9]}-{clean[9:13]}"


async def extract_basic_info(page: Page) -> Tuple[str, str, str]:
    """
    Extract item name, INC code, and assignment date.

    Returns (item_name, inc_code, assignment_date)
    """
    item_name = ""
    inc_code = ""
    assignment_date = ""

    try:
        html = await page.content()

        # Extract item name
        item_match = re.search(r"Item Name[:\s]*([^<]+)", html, re.IGNORECASE)
        if item_match:
            item_name = item_match.group(1).strip()

        # Extract INC code
        inc_match = re.search(r"INC[:\s]*(\d+)", html, re.IGNORECASE)
        if inc_match:
            inc_code = inc_match.group(1).strip()

        # Extract assignment date
        date_match = re.search(r"Assignment Date[:\s]*([^<\n]+)", html, re.IGNORECASE)
        if date_match:
            assignment_date = date_match.group(1).strip()

    except Exception:
        pass

    return item_name, inc_code, assignment_date


async def extract_part_alternates(page: Page) -> List[str]:
    """Extract part alternates list"""
    alternates = []

    try:
        html = await page.content()
        match = re.search(r"Part Alternates?[:\s]*([^<]+?)(?:<|$)", html, re.IGNORECASE)

        if match:
            parts_text = match.group(1).strip()
            # Split by commas and/or whitespace
            parts = re.split(r"[,\s]+", parts_text)
            alternates = [p.strip() for p in parts if p.strip()]

    except Exception:
        pass

    return alternates


async def extract_manufacturers(page: Page) -> List[WBPartsManufacturer]:
    """
    Extract manufacturer data from tables.

    Table structure:
    - Part Number
    - CAGE Code
    - Company Name
    """
    manufacturers = []

    try:
        tables = page.locator("table")
        table_count = await tables.count()

        for t in range(table_count):
            table = tables.nth(t)
            text = await table.inner_text()

            # Check if this is a manufacturer table
            if "CAGE" in text.upper() or "Manufacturer" in text or "Part Number" in text:
                rows = table.locator("tr")
                row_count = await rows.count()

                # Skip header row
                for i in range(1, row_count):
                    row = rows.nth(i)
                    cells = row.locator("td")
                    cell_count = await cells.count()

                    if cell_count >= 3:
                        part_number = (await cells.nth(0).inner_text()).strip()
                        cage_code = (await cells.nth(1).inner_text()).strip()
                        company_name = (await cells.nth(2).inner_text()).strip()

                        # Validate CAGE code (5 alphanumeric characters)
                        if cage_code and re.match(r"^[A-Z0-9]{5}$", cage_code, re.IGNORECASE):
                            manufacturers.append(WBPartsManufacturer(
                                partNumber=part_number,
                                cageCode=cage_code,
                                companyName=company_name
                            ))

    except Exception:
        pass

    return manufacturers


async def extract_tech_specs(page: Page) -> List[WBPartsTechSpec]:
    """Extract technical specifications"""
    specs = []

    try:
        html = await page.content()

        # Common specification patterns
        spec_patterns = [
            ("Heating Element Type", r"Heating Element Type[:\s]*([^<\n]+)"),
            ("Heat Medium", r"Heat Medium[:\s]*([^<\n]+)"),
            ("Material", r"Material[:\s]*([^<\n]+)"),
            ("Dimensions", r"Dimensions?[:\s]*([^<\n]+)"),
            ("Special Feature", r"Special Feature[:\s]*([^<\n]+)"),
            ("Weight", r"Weight[:\s]*([^<\n]+)"),
        ]

        for name, pattern in spec_patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                value = match.group(1).strip()
                if value:
                    specs.append(WBPartsTechSpec(name=name, value=value))

    except Exception:
        pass

    return specs


async def extract_demand_history(page: Page) -> List[WBPartsDemand]:
    """
    Extract demand history from tables.

    Table structure:
    - Part Number
    - Request Date
    - Quantity
    - Origin
    """
    demands = []

    try:
        tables = page.locator("table")
        table_count = await tables.count()

        for t in range(table_count):
            table = tables.nth(t)
            text = await table.inner_text()

            # Check if this is a demand table
            if "Request Date" in text or "Demand" in text or "QTY" in text.upper():
                rows = table.locator("tr")
                row_count = await rows.count()

                # Skip header row, limit to 10 entries
                for i in range(1, min(row_count, 11)):
                    row = rows.nth(i)
                    cells = row.locator("td")
                    cell_count = await cells.count()

                    if cell_count >= 4:
                        part_number = (await cells.nth(0).inner_text()).strip()
                        request_date = (await cells.nth(1).inner_text()).strip()

                        qty_text = (await cells.nth(2).inner_text()).strip()
                        try:
                            quantity = int(qty_text.replace(",", ""))
                        except ValueError:
                            quantity = 0

                        origin = (await cells.nth(3).inner_text()).strip()

                        if request_date and quantity > 0:
                            demands.append(WBPartsDemand(
                                partNumber=part_number,
                                requestDate=request_date,
                                quantity=quantity,
                                origin=origin
                            ))

    except Exception:
        pass

    return demands


async def scrape_wbparts(nsn: str) -> WBPartsScrapeResult:
    """
    Main function to scrape WBParts for an NSN.

    Returns WBPartsScrapeResult with success status and data.
    """
    browser: Optional[Browser] = None
    formatted_nsn = format_nsn_with_dashes(nsn)
    source_url = f"{config.WBPARTS_BASE_URL}/{formatted_nsn}.html"

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=config.HEADLESS)
            context = await browser.new_context(user_agent=config.USER_AGENT)
            page = await context.new_page()

            # Navigate to WBParts
            response = await page.goto(source_url, timeout=config.SCRAPE_TIMEOUT)

            # Check for 404
            if response and response.status >= 400:
                await context.close()
                return WBPartsScrapeResult(
                    success=False,
                    error=f"HTTP {response.status}: Page not found"
                )

            # Wait for page to load
            await page.wait_for_load_state("domcontentloaded")
            await page.wait_for_load_state("networkidle")

            # Extract data
            item_name, inc_code, assignment_date = await extract_basic_info(page)
            part_alternates = await extract_part_alternates(page)
            manufacturers = await extract_manufacturers(page)
            tech_specs = await extract_tech_specs(page)
            demand_history = await extract_demand_history(page)

            await context.close()

            wbparts_data = WBPartsData(
                nsn=formatted_nsn,
                itemName=item_name,
                incCode=inc_code,
                partAlternates=part_alternates,
                manufacturers=manufacturers,
                techSpecs=tech_specs,
                demandHistory=demand_history,
                assignmentDate=assignment_date,
                sourceUrl=source_url,
                scrapedAt=datetime.utcnow().isoformat() + "Z"
            )

            return WBPartsScrapeResult(success=True, data=wbparts_data)

    except Exception as e:
        return WBPartsScrapeResult(success=False, error=str(e))

    finally:
        if browser:
            await browser.close()


# Synchronous wrapper for non-async contexts
def scrape_wbparts_sync(nsn: str) -> WBPartsScrapeResult:
    """Synchronous wrapper for scrape_wbparts"""
    return asyncio.run(scrape_wbparts(nsn))
