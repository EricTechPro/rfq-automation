/**
 * WBParts RFQ Scraper
 *
 * Scrapes NSN data from WBParts.com as a secondary data source.
 * WBParts provides clearer NSN context and manufacturer details.
 * No login required.
 */

import { chromium, Page, Browser, BrowserContext } from "playwright";
import type {
  WBPartsData,
  WBPartsScrapeResult,
  WBPartsManufacturer,
  WBPartsTechSpec,
  WBPartsDemand,
} from "./types.js";

const WBPARTS_BASE_URL = "https://www.wbparts.com/rfq";
const DEFAULT_TIMEOUT = 30000;

/**
 * Format NSN with dashes for WBParts URL
 * Input: "4520012619675" or "4520-01-261-9675"
 * Output: "4520-01-261-9675"
 */
function formatNSNWithDashes(nsn: string): string {
  // Remove any existing dashes
  const clean = nsn.replace(/-/g, "");

  // Format as XXXX-XX-XXX-XXXX
  if (clean.length === 13) {
    return `${clean.slice(0, 4)}-${clean.slice(4, 6)}-${clean.slice(6, 9)}-${clean.slice(9)}`;
  }

  // If already has dashes or different format, return as-is
  return nsn;
}

/**
 * Extract item name and basic info from page
 */
async function extractBasicInfo(
  page: Page
): Promise<{ itemName: string; incCode: string; assignmentDate: string }> {
  let itemName = "";
  let incCode = "";
  let assignmentDate = "";

  try {
    // Get all text content and parse
    const pageText = await page.content();

    // Extract item name (usually in a heading or prominent text)
    const itemNameMatch = pageText.match(/Item Name[:\s]*([^<]+)/i);
    if (itemNameMatch) {
      itemName = itemNameMatch[1].trim().replace(/"/g, "");
    }

    // Extract INC code
    const incMatch = pageText.match(/INC[:\s]*(\d+)/i);
    if (incMatch) {
      incCode = incMatch[1].trim();
    }

    // Extract assignment date
    const dateMatch = pageText.match(/Assignment Date[:\s]*([^<\n]+)/i);
    if (dateMatch) {
      assignmentDate = dateMatch[1].trim();
    }
  } catch (error) {
    console.log("Could not extract basic info:", error);
  }

  return { itemName, incCode, assignmentDate };
}

/**
 * Extract part alternates
 */
async function extractPartAlternates(page: Page): Promise<string[]> {
  const alternates: string[] = [];

  try {
    const pageText = await page.content();

    // Look for part alternates section
    const alternatesMatch = pageText.match(
      /Part Alternates?[:\s]*([^<]+?)(?:<|$)/i
    );
    if (alternatesMatch) {
      const parts = alternatesMatch[1].split(/[,\s]+/).filter((p) => p.trim());
      alternates.push(...parts.map((p) => p.trim()));
    }
  } catch (error) {
    console.log("Could not extract part alternates:", error);
  }

  return alternates;
}

/**
 * Extract manufacturer data from tables
 */
async function extractManufacturers(page: Page): Promise<WBPartsManufacturer[]> {
  const manufacturers: WBPartsManufacturer[] = [];

  try {
    // Look for tables containing manufacturer data
    const tables = await page.locator("table").all();

    for (const table of tables) {
      const tableText = await table.textContent();

      // Check if this table contains manufacturer data
      if (
        tableText?.includes("CAGE") ||
        tableText?.includes("Manufacturer") ||
        tableText?.includes("Part Number")
      ) {
        const rows = await table.locator("tr").all();

        for (let i = 1; i < rows.length; i++) {
          const cells = await rows[i].locator("td, th").all();

          if (cells.length >= 3) {
            const partNumber = ((await cells[0].textContent()) || "").trim();
            const cageCode = ((await cells[1].textContent()) || "").trim();
            const companyName = ((await cells[2].textContent()) || "").trim();

            // Validate CAGE code format (5 alphanumeric chars)
            if (cageCode && /^[A-Z0-9]{5}$/i.test(cageCode)) {
              manufacturers.push({
                partNumber,
                cageCode,
                companyName,
              });
            }
          }
        }
      }
    }
  } catch (error) {
    console.log("Could not extract manufacturers:", error);
  }

  return manufacturers;
}

/**
 * Extract technical specifications
 */
async function extractTechSpecs(page: Page): Promise<WBPartsTechSpec[]> {
  const specs: WBPartsTechSpec[] = [];

  try {
    const pageText = await page.content();

    // Common spec patterns
    const specPatterns = [
      /Heating Element Type[:\s]*([^<\n]+)/i,
      /Heat Medium[:\s]*([^<\n]+)/i,
      /Material[:\s]*([^<\n]+)/i,
      /Dimensions?[:\s]*([^<\n]+)/i,
      /Special Feature[:\s]*([^<\n]+)/i,
      /Weight[:\s]*([^<\n]+)/i,
    ];

    for (const pattern of specPatterns) {
      const match = pageText.match(pattern);
      if (match) {
        const name = pattern.source
          .split("[")[0]
          .replace(/\\/g, "")
          .replace(/\?/g, "");
        specs.push({
          name,
          value: match[1].trim(),
        });
      }
    }
  } catch (error) {
    console.log("Could not extract tech specs:", error);
  }

  return specs;
}

/**
 * Extract demand history
 */
async function extractDemandHistory(page: Page): Promise<WBPartsDemand[]> {
  const demands: WBPartsDemand[] = [];

  try {
    // Look for demand history table
    const tables = await page.locator("table").all();

    for (const table of tables) {
      const tableText = await table.textContent();

      if (
        tableText?.includes("Request Date") ||
        tableText?.includes("Demand") ||
        tableText?.includes("QTY")
      ) {
        const rows = await table.locator("tr").all();

        for (let i = 1; i < Math.min(rows.length, 11); i++) {
          // Limit to 10 most recent
          const cells = await rows[i].locator("td").all();

          if (cells.length >= 4) {
            const partNumber = ((await cells[0].textContent()) || "").trim();
            const requestDate = ((await cells[1].textContent()) || "").trim();
            const qtyText = ((await cells[2].textContent()) || "0").trim();
            const origin = ((await cells[3].textContent()) || "").trim();

            const quantity = parseInt(qtyText, 10) || 0;

            if (requestDate && quantity > 0) {
              demands.push({
                partNumber,
                requestDate,
                quantity,
                origin,
              });
            }
          }
        }
        break;
      }
    }
  } catch (error) {
    console.log("Could not extract demand history:", error);
  }

  return demands;
}

/**
 * Main WBParts scraper function
 */
export async function scrapeWBParts(nsn: string): Promise<WBPartsScrapeResult> {
  const formattedNSN = formatNSNWithDashes(nsn);
  const url = `${WBPARTS_BASE_URL}/${formattedNSN}.html`;

  console.log(`Scraping WBParts for NSN: ${nsn}`);
  console.log(`URL: ${url}`);

  let browser: Browser | null = null;
  let context: BrowserContext | null = null;

  try {
    browser = await chromium.launch({
      headless: true,
    });

    context = await browser.newContext({
      userAgent:
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    });

    const page = await context.newPage();

    console.log("Navigating to WBParts...");
    const response = await page.goto(url, {
      waitUntil: "domcontentloaded",
      timeout: DEFAULT_TIMEOUT,
    });

    // Check for 404 or other errors
    if (!response || response.status() >= 400) {
      return {
        success: false,
        data: null,
        error: `Page not found or error: ${response?.status() || "no response"}`,
      };
    }

    // Wait for content to load
    await page.waitForLoadState("networkidle");

    console.log("Extracting WBParts data...");

    // Extract all data
    const { itemName, incCode, assignmentDate } = await extractBasicInfo(page);
    const partAlternates = await extractPartAlternates(page);
    const manufacturers = await extractManufacturers(page);
    const techSpecs = await extractTechSpecs(page);
    const demandHistory = await extractDemandHistory(page);

    const data: WBPartsData = {
      nsn: formattedNSN,
      itemName,
      incCode,
      partAlternates,
      manufacturers,
      techSpecs,
      demandHistory,
      assignmentDate,
      sourceUrl: url,
      scrapedAt: new Date().toISOString(),
    };

    console.log("WBParts data extracted successfully.");

    return {
      success: true,
      data,
      error: null,
    };
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error);
    console.error(`WBParts scraping failed: ${errorMessage}`);

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
 * Scrape multiple NSNs from WBParts
 */
export async function scrapeWBPartsBatch(
  nsns: string[]
): Promise<WBPartsScrapeResult[]> {
  const results: WBPartsScrapeResult[] = [];

  for (const nsn of nsns) {
    const result = await scrapeWBParts(nsn);
    results.push(result);

    // Small delay between requests
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }

  return results;
}
