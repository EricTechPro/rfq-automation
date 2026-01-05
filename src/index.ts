#!/usr/bin/env node
/**
 * RFQ Automation CLI
 *
 * Multi-source NSN/RFQ scraper with automatic contact discovery for OPEN RFQs.
 * Results are saved to JSON files in the results/ directory.
 *
 * Usage:
 *   npx tsx src/index.ts <NSN>                    # Auto-discovers contacts if OPEN
 *   npx tsx src/index.ts <NSN> --no-contacts      # Skip contact discovery
 *   npx tsx src/index.ts <NSN> --wbparts          # Include WBParts data
 *   npx tsx src/index.ts <NSN1>,<NSN2>            # Batch mode
 */

import { writeFile, mkdir } from "fs/promises";
import { existsSync } from "fs";
import { join } from "path";
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
  noContacts: boolean;
  forceContacts: boolean;
  allContacts: boolean;
  outputDir: string;
  help: boolean;
}

function parseArgs(args: string[]): CLIOptions {
  const options: CLIOptions = {
    nsns: [],
    wbparts: false,
    wbpartsOnly: false,
    noContacts: false,
    forceContacts: false,
    allContacts: false,
    outputDir: "./results",
    help: false,
  };

  for (let i = 0; i < args.length; i++) {
    const arg = args[i];
    if (arg === "--help" || arg === "-h") {
      options.help = true;
    } else if (arg === "--wbparts" || arg === "-w") {
      options.wbparts = true;
    } else if (arg === "--wbparts-only" || arg === "-W") {
      options.wbpartsOnly = true;
    } else if (arg === "--no-contacts") {
      options.noContacts = true;
    } else if (arg === "--contacts" || arg === "-c") {
      options.forceContacts = true;
    } else if (arg === "--all" || arg === "-a") {
      options.allContacts = true;
    } else if (arg === "--output" || arg === "-o") {
      options.outputDir = args[++i] || "./results";
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

Scrapes NSN/RFQ data from DIBBS and automatically discovers supplier contacts
when an OPEN RFQ is found. Results are saved to JSON files.

Usage:
  npx tsx src/index.ts <NSN>                    Scrape and auto-discover contacts if OPEN
  npx tsx src/index.ts <NSN> --no-contacts      Skip contact discovery
  npx tsx src/index.ts <NSN> --contacts         Force contact discovery even if NOT OPEN
  npx tsx src/index.ts <NSN> --wbparts          Include WBParts data
  npx tsx src/index.ts <NSN1>,<NSN2>            Batch mode (comma-separated)
  npx tsx src/index.ts --help                   Show this help

Options:
  -w, --wbparts       Include WBParts data (manufacturer details, specs)
  -W, --wbparts-only  Only scrape from WBParts (skip DIBBS)
  --no-contacts       Skip contact discovery even if RFQ is OPEN
  -c, --contacts      Force contact discovery even if RFQ is NOT OPEN
  -a, --all           Look up all suppliers (not just primary)
  -o, --output <dir>  Output directory (default: ./results)
  -h, --help          Show help

Automatic Behavior:
  - When RFQ is OPEN: Automatically searches for supplier contacts via Firecrawl
  - When RFQ is NOT OPEN: Skips contact discovery (use --contacts to override)
  - Results saved to: ./results/<NSN>.json

Data Sources:
  DIBBS      https://www.dibbs.bsm.dla.mil  (OPEN status, solicitations)
  WBParts    https://www.wbparts.com        (manufacturer details, specs)
  Firecrawl  https://firecrawl.dev          (supplier website & contacts)

Examples:
  npx tsx src/index.ts 4520-01-261-9675
  npx tsx src/index.ts 4520-01-261-9675 --wbparts
  npx tsx src/index.ts 4520-01-261-9675 --no-contacts
  npx tsx src/index.ts 4520-01-261-9675 --contacts --all

Environment Variables:
  FIRECRAWL_API_KEY   Required for contact discovery
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

  let primaryCompany: string | null = null;
  let primaryCageCode: string | null = null;

  if (dibbs?.approvedSources?.[0]) {
    primaryCompany = dibbs.approvedSources[0].companyName;
    primaryCageCode = dibbs.approvedSources[0].cageCode;
  } else if (wbparts?.manufacturers?.[0]) {
    primaryCompany = wbparts.manufacturers[0].companyName;
    primaryCageCode = wbparts.manufacturers[0].cageCode;
  }

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
 * Save result to JSON file
 */
async function saveResult(
  nsn: string,
  result: unknown,
  outputDir: string
): Promise<string> {
  // Create output directory if it doesn't exist
  if (!existsSync(outputDir)) {
    await mkdir(outputDir, { recursive: true });
  }

  const filename = `${nsn}.json`;
  const filepath = join(outputDir, filename);

  await writeFile(filepath, JSON.stringify(result, null, 2), "utf-8");

  return filepath;
}

/**
 * Scrape single NSN with automatic contact discovery for OPEN RFQs
 */
async function scrapeSingle(
  nsn: string,
  options: CLIOptions
): Promise<{ result: EnhancedRFQResult; filepath: string }> {
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

  // Determine if we should run contact discovery
  const hasOpenRFQ = dibbsResult.data?.hasOpenRFQs ?? false;
  const shouldRunContacts =
    !options.noContacts && (hasOpenRFQ || options.forceContacts);

  // Get all suppliers
  const dibbsSources = dibbsResult.data?.approvedSources || [];
  const wbpartsMfrs = wbpartsResult.data?.manufacturers || [];
  const allSuppliers = getUniqueSuppliers(dibbsSources, wbpartsMfrs);

  // Contact discovery
  const suppliersWithContacts: SupplierWithContact[] = [];
  let firecrawlStatus: "success" | "error" | "skipped" | "partial" = "skipped";

  if (shouldRunContacts && allSuppliers.length > 0) {
    console.error(
      `RFQ is ${hasOpenRFQ ? "OPEN" : "NOT OPEN (forced)"} - Starting contact discovery...`
    );

    const suppliersToLookup = options.allContacts
      ? allSuppliers
      : allSuppliers.slice(0, 1);

    console.error(
      `Looking up contacts for ${suppliersToLookup.length} supplier(s)...`
    );

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

    if (suppliersToLookup.length === 0) {
      firecrawlStatus = "skipped";
    } else if (successCount === suppliersToLookup.length) {
      firecrawlStatus = "success";
    } else if (successCount > 0) {
      firecrawlStatus = "partial";
    } else {
      firecrawlStatus = "error";
    }
  } else {
    // No contact discovery - just list suppliers without contact info
    console.error(
      hasOpenRFQ
        ? "Contact discovery skipped (--no-contacts flag)"
        : "RFQ is NOT OPEN - Skipping contact discovery"
    );

    for (const supplier of allSuppliers) {
      suppliersWithContacts.push({
        companyName: supplier.companyName,
        cageCode: supplier.cageCode,
        partNumber: supplier.partNumber,
        contact: null,
      });
    }
  }

  // Build result
  const result: EnhancedRFQResult = {
    nsn: dibbsResult.data?.nsn || wbpartsResult.data?.nsn || nsn,
    itemName:
      wbpartsResult.data?.itemName || dibbsResult.data?.nomenclature || "",
    hasOpenRFQ,
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

  // Save to file
  const filepath = await saveResult(nsn, result, options.outputDir);
  console.error(`Result saved to: ${filepath}`);

  return { result, filepath };
}

async function scrapeBatch(
  nsns: string[],
  options: CLIOptions
): Promise<Array<{ nsn: string; filepath: string; hasOpenRFQ: boolean }>> {
  console.error(`Batch mode: Processing ${nsns.length} NSNs...`);
  const results: Array<{
    nsn: string;
    filepath: string;
    hasOpenRFQ: boolean;
  }> = [];

  for (const nsn of nsns) {
    const { result, filepath } = await scrapeSingle(nsn, options);
    results.push({
      nsn,
      filepath,
      hasOpenRFQ: result.hasOpenRFQ,
    });

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

  console.error("=".repeat(50));
  console.error("RFQ Automation Scraper");
  console.error("=".repeat(50));

  if (options.nsns.length === 1) {
    const { result, filepath } = await scrapeSingle(options.nsns[0], options);

    console.error("\n" + "=".repeat(50));
    console.error("SUMMARY");
    console.error("=".repeat(50));
    console.error(`NSN: ${result.nsn}`);
    console.error(`Item: ${result.itemName}`);
    console.error(`RFQ Status: ${result.hasOpenRFQ ? "OPEN" : "NOT OPEN"}`);
    console.error(`Suppliers: ${result.suppliers.length}`);
    console.error(`Output: ${filepath}`);

    if (result.suppliers.length > 0 && result.suppliers[0].contact) {
      const contact = result.suppliers[0].contact;
      console.error("\nPrimary Contact:");
      console.error(`  Company: ${contact.companyName}`);
      if (contact.email) console.error(`  Email: ${contact.email}`);
      if (contact.phone) console.error(`  Phone: ${contact.phone}`);
      if (contact.website) console.error(`  Website: ${contact.website}`);
    }

    // Also output JSON to stdout for piping
    console.log(JSON.stringify(result, null, 2));
  } else {
    const results = await scrapeBatch(options.nsns, options);

    console.error("\n" + "=".repeat(50));
    console.error("BATCH SUMMARY");
    console.error("=".repeat(50));

    for (const r of results) {
      console.error(
        `${r.nsn}: ${r.hasOpenRFQ ? "OPEN" : "NOT OPEN"} -> ${r.filepath}`
      );
    }

    console.log(JSON.stringify(results, null, 2));
  }
}

// Run main
main().catch((error) => {
  console.error("Fatal error:", error);
  process.exit(1);
});
