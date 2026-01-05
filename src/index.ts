#!/usr/bin/env node
/**
 * RFQ Automation CLI
 *
 * Multi-source NSN/RFQ scraper supporting DIBBS and WBParts.
 *
 * Usage:
 *   npx tsx src/index.ts <NSN>                    # DIBBS only (default)
 *   npx tsx src/index.ts <NSN> --wbparts          # Both DIBBS and WBParts
 *   npx tsx src/index.ts <NSN> --wbparts-only     # WBParts only
 *   npx tsx src/index.ts <NSN1>,<NSN2>            # Batch mode
 */

import { scrapeDIBBS, scrapeDIBBSBatch } from "./dibbs-scraper.js";
import { scrapeWBParts, scrapeWBPartsBatch } from "./wbparts-scraper.js";
import type { CombinedRFQData, CombinedScrapeResult } from "./types.js";

interface CLIOptions {
  nsns: string[];
  wbparts: boolean;
  wbpartsOnly: boolean;
  help: boolean;
}

function parseArgs(args: string[]): CLIOptions {
  const options: CLIOptions = {
    nsns: [],
    wbparts: false,
    wbpartsOnly: false,
    help: false,
  };

  for (const arg of args) {
    if (arg === "--help" || arg === "-h") {
      options.help = true;
    } else if (arg === "--wbparts" || arg === "-w") {
      options.wbparts = true;
    } else if (arg === "--wbparts-only" || arg === "-W") {
      options.wbpartsOnly = true;
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

Scrapes NSN/RFQ data from DIBBS (primary) and WBParts (secondary).

Usage:
  npx tsx src/index.ts <NSN>                    Scrape from DIBBS only
  npx tsx src/index.ts <NSN> --wbparts          Scrape from both sources
  npx tsx src/index.ts <NSN> --wbparts-only     Scrape from WBParts only
  npx tsx src/index.ts <NSN1>,<NSN2>            Batch mode (comma-separated)
  npx tsx src/index.ts --help                   Show this help

Options:
  -w, --wbparts       Include WBParts data (combined output)
  -W, --wbparts-only  Only scrape from WBParts
  -h, --help          Show help

Data Sources:
  DIBBS    https://www.dibbs.bsm.dla.mil  (OPEN status, solicitations)
  WBParts  https://www.wbparts.com        (manufacturer details, specs)

Examples:
  npx tsx src/index.ts 4520-01-261-9675
  npx tsx src/index.ts 4520-01-261-9675 --wbparts
  npx tsx src/index.ts 4520-01-261-9675,4030-01-097-6471 --wbparts

Output:
  JSON to stdout with:
  - NSN, Nomenclature, Item Name
  - Approved Sources / Manufacturers
  - CAGE Codes, Part Numbers
  - Solicitations (DIBBS)
  - Technical Specs (WBParts)
  - hasOpenRFQ status
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

async function scrapeSingle(
  nsn: string,
  options: CLIOptions
): Promise<unknown> {
  if (options.wbpartsOnly) {
    // WBParts only
    console.error(`Scraping WBParts for NSN: ${nsn}...`);
    return await scrapeWBParts(nsn);
  } else if (options.wbparts) {
    // Both sources
    console.error(`Scraping DIBBS + WBParts for NSN: ${nsn}...`);
    const [dibbsResult, wbpartsResult] = await Promise.all([
      scrapeDIBBS(nsn),
      scrapeWBParts(nsn),
    ]);
    return combineResults(dibbsResult, wbpartsResult);
  } else {
    // DIBBS only (default)
    console.error(`Scraping DIBBS for NSN: ${nsn}...`);
    return await scrapeDIBBS(nsn);
  }
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
    await new Promise((resolve) => setTimeout(resolve, 500));
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
