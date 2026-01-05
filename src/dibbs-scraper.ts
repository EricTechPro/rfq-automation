/**
 * DIBBS RFQ Scraper
 *
 * Uses Playwright to navigate the Defense Logistics Agency Internet Bid Board System,
 * handle the DoD consent banner, and extract RFQ data.
 */

import { chromium, Page, Browser, BrowserContext } from "playwright";
import type {
  RFQData,
  ScrapeResult,
  ApprovedSource,
  Solicitation,
} from "./types.js";
import { config } from "./config.js";

/**
 * Format NSN by removing dashes for URL parameter
 */
function formatNSN(nsn: string): string {
  return nsn.replace(/-/g, "");
}

/**
 * Handle the DoD Notice and Consent Banner by clicking OK
 */
async function handleConsentBanner(page: Page): Promise<boolean> {
  try {
    // Look for the OK button on the consent banner
    // The button appears to be an input submit with value "OK"
    const okButton = page.locator('input[type="submit"][value="OK"]');

    // Check if visible with a short timeout (banner may not appear if cookies set)
    const isVisible = await okButton
      .isVisible({ timeout: 5000 })
      .catch(() => false);

    if (isVisible) {
      console.error("Consent banner detected, clicking OK...");
      await okButton.click();
      await page.waitForLoadState("networkidle");
      console.error("Consent accepted, page loaded.");
      return true;
    }

    console.error("No consent banner found (may already be accepted).");
    return false;
  } catch (error) {
    console.error("No consent banner interaction needed.");
    return false;
  }
}

/**
 * Extract header information (NSN, Nomenclature, AMSC)
 */
async function extractHeaderInfo(
  page: Page
): Promise<{ nsn: string; nomenclature: string; amsc: string }> {
  // The header info appears in a fieldset with format:
  // NSN: 4520-01-261-9675  Nomenclature: HEATER,VENTILATION,  AMSC: Z
  const headerText = await page
    .locator("fieldset")
    .first()
    .textContent()
    .catch(() => "");

  let nsn = "";
  let nomenclature = "";
  let amsc = "";

  if (headerText) {
    // Extract NSN
    const nsnMatch = headerText.match(/NSN:\s*([\d-]+)/);
    if (nsnMatch) nsn = nsnMatch[1].trim();

    // Extract Nomenclature (may contain commas, ends at AMSC)
    const nomenMatch = headerText.match(/Nomenclature:\s*(.+?)(?:\s*AMSC:|$)/);
    if (nomenMatch) nomenclature = nomenMatch[1].trim().replace(/,\s*$/, "");

    // Extract AMSC
    const amscMatch = headerText.match(/AMSC:\s*(\w+)/);
    if (amscMatch) amsc = amscMatch[1].trim();
  }

  return { nsn, nomenclature, amsc };
}

/**
 * Extract Approved Source Data (manufacturers)
 */
async function extractApprovedSources(page: Page): Promise<ApprovedSource[]> {
  const sources: ApprovedSource[] = [];

  try {
    // Look for the Approved Source Data fieldset specifically
    const sourceFieldset = page.locator('fieldset:has-text("Approved Source Data")').first();

    // Get the table inside this fieldset
    const sourceTable = sourceFieldset.locator("table").first();

    // Get all rows
    const rows = await sourceTable.locator("tr").all();

    for (let i = 1; i < rows.length; i++) {
      // Skip header row
      const cells = await rows[i].locator("td").all();

      // Approved Source table has exactly 3 columns: CAGE, Part Number, Company Name
      if (cells.length === 3) {
        const cageCode = (await cells[0].textContent()) || "";
        const partNumber = (await cells[1].textContent()) || "";
        const companyName = (await cells[2].textContent()) || "";

        // Validate: CAGE should be numeric/alphanumeric (5 chars), not look like a solicitation number
        const trimmedCage = cageCode.trim();
        if (trimmedCage && !trimmedCage.startsWith("SPE") && trimmedCage.length <= 10) {
          sources.push({
            cageCode: trimmedCage,
            partNumber: partNumber.trim(),
            companyName: companyName.trim(),
          });
        }
      }
    }
  } catch (error) {
    console.error("Could not extract approved sources:", error);
  }

  return sources;
}

/**
 * Extract Solicitations data
 */
async function extractSolicitations(page: Page): Promise<Solicitation[]> {
  const solicitations: Solicitation[] = [];

  try {
    // Look for the Solicitations table
    const solTable = page.locator('table:near(:text("Solicitations"))').first();

    // Alternative: look for table with solicitation headers
    const tables = await page.locator("table").all();

    for (const table of tables) {
      const tableText = await table.textContent();
      if (tableText?.includes("Solicitation #") || tableText?.includes("PR #")) {
        const rows = await table.locator("tr").all();

        for (let i = 1; i < rows.length; i++) {
          // Skip header row
          const cells = await rows[i].locator("td").all();

          if (cells.length >= 6) {
            // Get solicitation number and URL if it's a link
            const solCell = cells[0];
            const solLink = await solCell.locator("a").first();
            const solNumber = (await solCell.textContent()) || "";
            let solUrl: string | null = null;

            try {
              solUrl = await solLink.getAttribute("href");
            } catch {
              // No link found
            }

            const techDocs = (await cells[1].textContent()) || "";
            const prNumber = (await cells[2].textContent()) || "";
            const qtyText = (await cells[3].textContent()) || "0";
            const issueDate = (await cells[4].textContent()) || "";
            const returnByDate = (await cells[5].textContent()) || "";

            solicitations.push({
              solicitationNumber: solNumber.trim(),
              solicitationUrl: solUrl,
              technicalDocuments: techDocs.trim(),
              prNumber: prNumber.trim(),
              quantity: parseInt(qtyText.trim(), 10) || 0,
              issueDate: issueDate.trim(),
              returnByDate: returnByDate.trim(),
            });
          }
        }
        break; // Found the solicitations table
      }
    }
  } catch (error) {
    console.error("Could not extract solicitations:", error);
  }

  return solicitations;
}

/**
 * Check if there are any open RFQs (not awarded or cancelled)
 */
function hasOpenRFQs(solicitations: Solicitation[]): boolean {
  // If we have solicitations with future return dates, they're likely open
  const today = new Date();

  return solicitations.some((sol) => {
    if (sol.returnByDate) {
      // Parse date format MM-DD-YYYY
      const [month, day, year] = sol.returnByDate.split("-").map(Number);
      const returnDate = new Date(year, month - 1, day);
      return returnDate >= today;
    }
    return false;
  });
}

/**
 * Extract all RFQ data from the page
 */
async function extractRFQData(page: Page, sourceUrl: string): Promise<RFQData> {
  const { nsn, nomenclature, amsc } = await extractHeaderInfo(page);
  const approvedSources = await extractApprovedSources(page);
  const solicitations = await extractSolicitations(page);

  return {
    nsn,
    nomenclature,
    amsc,
    approvedSources,
    solicitations,
    hasOpenRFQs: hasOpenRFQs(solicitations),
    scrapedAt: new Date().toISOString(),
    sourceUrl,
  };
}

/**
 * Main scraper function
 *
 * @param nsn - National Stock Number (with or without dashes)
 * @returns ScrapeResult with data or error
 */
export async function scrapeDIBBS(nsn: string): Promise<ScrapeResult> {
  const formattedNSN = formatNSN(nsn);
  const url = `${config.urls.dibbs}?value=${formattedNSN}`;

  console.error(`Scraping DIBBS for NSN: ${nsn}`);
  console.error(`URL: ${url}`);

  let browser: Browser | null = null;
  let context: BrowserContext | null = null;

  try {
    // Launch browser in headless mode
    browser = await chromium.launch({
      headless: config.browser.headless,
    });

    context = await browser.newContext({
      userAgent: config.browser.userAgent,
    });

    const page = await context.newPage();

    // Navigate to DIBBS
    console.error("Navigating to DIBBS...");
    await page.goto(url, {
      waitUntil: "networkidle",
      timeout: config.timeouts.scrape,
    });

    // Handle consent banner
    await handleConsentBanner(page);

    // Retry logic for pages that need refresh
    let data: RFQData | null = null;

    for (let attempt = 1; attempt <= config.retry.maxRetries; attempt++) {
      console.error(`Extraction attempt ${attempt}/${config.retry.maxRetries}...`);

      data = await extractRFQData(page, url);

      // Check if we got meaningful data
      if (data.nsn || data.approvedSources.length > 0 || data.solicitations.length > 0) {
        console.error("Data extracted successfully.");
        break;
      }

      // If no data, try refreshing (DIBBS sometimes needs this)
      if (attempt < config.retry.maxRetries) {
        console.error("No data found, refreshing page...");
        await page.reload();
        await page.waitForLoadState("networkidle");
        await handleConsentBanner(page);
      }
    }

    return {
      success: true,
      data,
      error: null,
    };
  } catch (error) {
    const errorMessage =
      error instanceof Error ? error.message : String(error);
    console.error(`Scraping failed: ${errorMessage}`);

    return {
      success: false,
      data: null,
      error: errorMessage,
    };
  } finally {
    if (context) await context.close();
    if (browser) await browser.close();
  }
}

/**
 * Scrape multiple NSNs
 *
 * @param nsns - Array of National Stock Numbers
 * @returns Array of ScrapeResults
 */
export async function scrapeDIBBSBatch(nsns: string[]): Promise<ScrapeResult[]> {
  const results: ScrapeResult[] = [];

  for (const nsn of nsns) {
    const result = await scrapeDIBBS(nsn);
    results.push(result);

    // Small delay between requests to be respectful
    await new Promise((resolve) => setTimeout(resolve, config.rateLimit.batchDelay * 2));
  }

  return results;
}
