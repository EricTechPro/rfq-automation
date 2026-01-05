#!/usr/bin/env node
/**
 * RFQ Automation CLI
 *
 * Multi-source NSN/RFQ scraper supporting DIBBS, WBParts, and Firecrawl contact discovery.
 *
 * Usage:
 *   npx tsx src/index.ts <NSN>                         # DIBBS only (default)
 *   npx tsx src/index.ts <NSN> --wbparts               # Both DIBBS and WBParts
 *   npx tsx src/index.ts <NSN> --wbparts-only          # WBParts only
 *   npx tsx src/index.ts <NSN> --contacts              # Include primary supplier contact
 *   npx tsx src/index.ts <NSN> --contacts --all        # Include all suppliers' contacts
 *   npx tsx src/index.ts <NSN1>,<NSN2>                 # Batch mode
 */

import { scrapeDIBBS } from "./dibbs-scraper.js";
import { scrapeWBParts } from "./wbparts-scraper.js";
import { findSupplierContact } from "./firecrawl-client.js";
import { config } from "./config.js";
import type {
  CombinedRFQData,
  CombinedScrapeResult,
  EnhancedRFQResult,
  SupplierWithContact,
  ApprovedSource,
  WBPartsManufacturer,
} from "./types.js";

interface CLIOptions {
  nsns: string[];
  wbparts: boolean;
  wbpartsOnly: boolean;
  contacts: boolean;
  allContacts: boolean;
  help: boolean;
}

function parseArgs(args: string[]): CLIOptions {
  const options: CLIOptions = {
    nsns: [],
    wbparts: false,
    wbpartsOnly: false,
    contacts: false,
    allContacts: false,
    help: false,
  };

  for (const arg of args) {
    if (arg === "--help" || arg === "-h") {
      options.help = true;
    } else if (arg === "--wbparts" || arg === "-w") {
      options.wbparts = true;
    } else if (arg === "--wbparts-only" || arg === "-W") {
      options.wbpartsOnly = true;
    } else if (arg === "--contacts" || arg === "-c") {
      options.contacts = true;
    } else if (arg === "--all" || arg === "-a") {
      options.allContacts = true;
    } else if (!arg.startsWith("-")) {
      // NSN input (could be comma-separated)
      const nsns = arg.split(",").map((n) => n.trim()).filter(Boolean);
      options.nsns.push(...nsns);
    }
  }

  return options;
}

function showHelp(): void {
  console.log(`
RFQ Automation Scraper
======================

Scrapes NSN/RFQ data from DIBBS (primary), WBParts (secondary),
and discovers supplier contacts via Firecrawl.

Usage:
  npx tsx src/index.ts <NSN>                    Scrape from DIBBS only
  npx tsx src/index.ts <NSN> --wbparts          Scrape from both sources
  npx tsx src/index.ts <NSN> --wbparts-only     Scrape from WBParts only
  npx tsx src/index.ts <NSN> --contacts         Include primary supplier contact
  npx tsx src/index.ts <NSN> --contacts --all   Include all suppliers' contacts
  npx tsx src/index.ts <NSN1>,<NSN2>            Batch mode (comma-separated)
  npx tsx src/index.ts --help                   Show this help

Options:
  -w, --wbparts       Include WBParts data (combined output)
  -W, --wbparts-only  Only scrape from WBParts
  -c, --contacts      Discover supplier contact info via Firecrawl
  -a, --all           With --contacts: look up all suppliers (not just primary)
  -h, --help          Show help

Data Sources:
  DIBBS      https://www.dibbs.bsm.dla.mil  (OPEN status, solicitations)
  WBParts    https://www.wbparts.com        (manufacturer details, specs)
  Firecrawl  https://firecrawl.dev          (supplier website & contacts)

Examples:
  npx tsx src/index.ts 4520-01-261-9675
  npx tsx src/index.ts 4520-01-261-9675 --wbparts
  npx tsx src/index.ts 4520-01-261-9675 --contacts
  npx tsx src/index.ts 4520-01-261-9675 --wbparts --contacts --all

Output:
  JSON to stdout with:
  - NSN, Nomenclature, Item Name
  - Approved Sources / Manufacturers
  - CAGE Codes, Part Numbers
  - Solicitations (DIBBS)
  - Technical Specs (WBParts)
  - hasOpenRFQ status
  - Supplier contact info (with --contacts)

Environment Variables:
  FIRECRAWL_API_KEY   Required for --contacts flag
  See .env.example for all options
`);
}

/**
 * Combine data from DIBBS and WBParts into a unified result
 */
function combineResults(
  dibbsResult: Awaited<ReturnType<typeof scrapeDIBBS>>,
  wbpartsResult: Awaited<ReturnType<typeof scrapeWBParts>>
): CombinedScrapeResult {
  const dibbs = dibbsResult.data;
  const wbparts = wbpartsResult.data;

  // Determine primary company
  let primaryCompany: string | null = null;
  let primaryCageCode: string | null = null;

  if (dibbs?.approvedSources?.[0]) {
    primaryCompany = dibbs.approvedSources[0].companyName;
    primaryCageCode = dibbs.approvedSources[0].cageCode;
  } else if (wbparts?.manufacturers?.[0]) {
    primaryCompany = wbparts.manufacturers[0].companyName;
    primaryCageCode = wbparts.manufacturers[0].cageCode;
  }

  // Collect all company names and CAGE codes
  const companyNames: Set<string> = new Set();
  const cageCodes: Set<string> = new Set();
  const partNumbers: Set<string> = new Set();

  if (dibbs) {
    for (const source of dibbs.approvedSources) {
      if (source.companyName) companyNames.add(source.companyName);
      if (source.cageCode) cageCodes.add(source.cageCode);
      if (source.partNumber) partNumbers.add(source.partNumber);
    }
  }

  if (wbparts) {
    for (const mfr of wbparts.manufacturers) {
      if (mfr.companyName) companyNames.add(mfr.companyName);
      if (mfr.cageCode) cageCodes.add(mfr.cageCode);
      if (mfr.partNumber) partNumbers.add(mfr.partNumber);
    }
    for (const alt of wbparts.partAlternates) {
      partNumbers.add(alt);
    }
  }

  const data: CombinedRFQData = {
    dibbs,
    wbparts,
    hasOpenRFQ: dibbs?.hasOpenRFQs ?? false,
    primaryCompany,
    primaryCageCode,
    summary: {
      nsn: dibbs?.nsn || wbparts?.nsn || "",
      itemName: wbparts?.itemName || dibbs?.nomenclature || "",
      companyNames: Array.from(companyNames),
      cageCodes: Array.from(cageCodes),
      partNumbers: Array.from(partNumbers),
    },
  };

  return {
    success: dibbsResult.success || wbpartsResult.success,
    data,
    dibbsError: dibbsResult.error,
    wbpartsError: wbpartsResult.error,
  };
}

/**
 * Get unique suppliers from DIBBS and WBParts data
 */
function getUniqueSuppliers(
  dibbsSources: ApprovedSource[],
  wbpartsMfrs: WBPartsManufacturer[]
): Array<{ companyName: string; cageCode: string; partNumber: string }> {
  const seen = new Set<string>();
  const suppliers: Array<{
    companyName: string;
    cageCode: string;
    partNumber: string;
  }> = [];

  // Add from DIBBS first (primary source)
  for (const source of dibbsSources) {
    const key = `${source.companyName}|${source.cageCode}`;
    if (!seen.has(key) && source.companyName) {
      seen.add(key);
      suppliers.push({
        companyName: source.companyName,
        cageCode: source.cageCode,
        partNumber: source.partNumber,
      });
    }
  }

  // Add from WBParts
  for (const mfr of wbpartsMfrs) {
    const key = `${mfr.companyName}|${mfr.cageCode}`;
    if (!seen.has(key) && mfr.companyName) {
      seen.add(key);
      suppliers.push({
        companyName: mfr.companyName,
        cageCode: mfr.cageCode,
        partNumber: mfr.partNumber,
      });
    }
  }

  return suppliers;
}

/**
 * Scrape single NSN with optional contact discovery
 */
async function scrapeSingle(
  nsn: string,
  options: CLIOptions
): Promise<unknown> {
  // Determine which scrapers to run
  const runDibbs = !options.wbpartsOnly;
  const runWbparts = options.wbparts || options.wbpartsOnly;

  let dibbsResult: Awaited<ReturnType<typeof scrapeDIBBS>> = {
    success: false,
    data: null,
    error: "Skipped",
  };
  let wbpartsResult: Awaited<ReturnType<typeof scrapeWBParts>> = {
    success: false,
    data: null,
    error: "Skipped",
  };

  // Run scrapers
  if (runDibbs && runWbparts) {
    console.error(`Scraping DIBBS + WBParts for NSN: ${nsn}...`);
    [dibbsResult, wbpartsResult] = await Promise.all([
      scrapeDIBBS(nsn),
      scrapeWBParts(nsn),
    ]);
  } else if (runDibbs) {
    console.error(`Scraping DIBBS for NSN: ${nsn}...`);
    dibbsResult = await scrapeDIBBS(nsn);
  } else if (runWbparts) {
    console.error(`Scraping WBParts for NSN: ${nsn}...`);
    wbpartsResult = await scrapeWBParts(nsn);
  }

  // If no contacts requested, return basic result
  if (!options.contacts) {
    if (options.wbpartsOnly) {
      return wbpartsResult;
    } else if (options.wbparts) {
      return combineResults(dibbsResult, wbpartsResult);
    } else {
      return dibbsResult;
    }
  }

  // === Contact Discovery Flow ===
  console.error("Starting supplier contact discovery...");

  // Get all suppliers
  const dibbsSources = dibbsResult.data?.approvedSources || [];
  const wbpartsMfrs = wbpartsResult.data?.manufacturers || [];
  const allSuppliers = getUniqueSuppliers(dibbsSources, wbpartsMfrs);

  // Determine which suppliers to look up
  const suppliersToLookup = options.allContacts
    ? allSuppliers
    : allSuppliers.slice(0, 1); // Primary only

  console.error(
    `Looking up contacts for ${suppliersToLookup.length} supplier(s)...`
  );

  // Look up contacts
  const suppliersWithContacts: SupplierWithContact[] = [];
  let firecrawlStatus: "success" | "error" | "skipped" | "partial" = "skipped";
  let successCount = 0;

  for (const supplier of suppliersToLookup) {
    try {
      const contact = await findSupplierContact(
        supplier.companyName,
        supplier.cageCode
      );

      suppliersWithContacts.push({
        companyName: supplier.companyName,
        cageCode: supplier.cageCode,
        partNumber: supplier.partNumber,
        contact,
      });

      if (contact.confidence !== "low") {
        successCount++;
      }

      // Rate limiting
      await new Promise((resolve) =>
        setTimeout(resolve, config.rateLimit.batchDelay)
      );
    } catch (error) {
      console.error(
        `Failed to get contact for ${supplier.companyName}:`,
        error
      );
      suppliersWithContacts.push({
        companyName: supplier.companyName,
        cageCode: supplier.cageCode,
        partNumber: supplier.partNumber,
        contact: null,
      });
    }
  }

  // Determine firecrawl status
  if (suppliersToLookup.length === 0) {
    firecrawlStatus = "skipped";
  } else if (successCount === suppliersToLookup.length) {
    firecrawlStatus = "success";
  } else if (successCount > 0) {
    firecrawlStatus = "partial";
  } else {
    firecrawlStatus = "error";
  }

  // Build enhanced result
  const enhancedResult: EnhancedRFQResult = {
    nsn: dibbsResult.data?.nsn || wbpartsResult.data?.nsn || nsn,
    itemName:
      wbpartsResult.data?.itemName || dibbsResult.data?.nomenclature || "",
    hasOpenRFQ: dibbsResult.data?.hasOpenRFQs ?? false,
    suppliers: suppliersWithContacts,
    rawData: {
      dibbs: dibbsResult.data,
      wbparts: wbpartsResult.data,
    },
    workflow: {
      dibbsStatus: runDibbs
        ? dibbsResult.success
          ? "success"
          : "error"
        : "skipped",
      wbpartsStatus: runWbparts
        ? wbpartsResult.success
          ? "success"
          : "error"
        : "skipped",
      firecrawlStatus,
    },
    scrapedAt: new Date().toISOString(),
  };

  return enhancedResult;
}

async function scrapeBatch(
  nsns: string[],
  options: CLIOptions
): Promise<unknown[]> {
  console.error(`Batch mode: Scraping ${nsns.length} NSNs...`);
  const results: unknown[] = [];

  for (const nsn of nsns) {
    const result = await scrapeSingle(nsn, options);
    results.push(result);

    // Small delay between requests
    await new Promise((resolve) =>
      setTimeout(resolve, config.rateLimit.batchDelay)
    );
  }

  return results;
}

async function main(): Promise<void> {
  const args = process.argv.slice(2);
  const options = parseArgs(args);

  if (options.help || options.nsns.length === 0) {
    showHelp();
    process.exit(options.help ? 0 : 1);
  }

  let result: unknown;

  if (options.nsns.length === 1) {
    result = await scrapeSingle(options.nsns[0], options);
  } else {
    result = await scrapeBatch(options.nsns, options);
  }

  // Output JSON to stdout
  console.log(JSON.stringify(result, null, 2));
}

// Run main
main().catch((error) => {
  console.error("Fatal error:", error);
  process.exit(1);
});
