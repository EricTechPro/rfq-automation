/**
 * Configuration Module
 *
 * Centralized configuration loader for the RFQ Automation scraper.
 * Loads settings from environment variables with sensible defaults.
 */

import { config as dotenvConfig } from "dotenv";

// Load .env file
dotenvConfig();

/**
 * Application configuration
 */
export const config = {
  // API Keys
  firecrawl: {
    apiKey: process.env.FIRECRAWL_API_KEY || "",
    apiUrl: process.env.FIRECRAWL_API_URL || "https://api.firecrawl.dev/v2",
    timeout: parseInt(process.env.FIRECRAWL_TIMEOUT || "60000", 10),
  },

  // Base URLs for scrapers
  urls: {
    dibbs: process.env.DIBBS_BASE_URL || "https://www.dibbs.bsm.dla.mil/rfq/rfqnsn.aspx",
    wbparts: process.env.WBPARTS_BASE_URL || "https://www.wbparts.com/rfq",
  },

  // Timeouts
  timeouts: {
    scrape: parseInt(process.env.SCRAPE_TIMEOUT || "30000", 10),
    firecrawl: parseInt(process.env.FIRECRAWL_TIMEOUT || "60000", 10),
  },

  // Retry configuration
  retry: {
    maxRetries: parseInt(process.env.MAX_RETRIES || "3", 10),
    retryDelay: parseInt(process.env.RETRY_DELAY || "1000", 10),
  },

  // Rate limiting
  rateLimit: {
    batchDelay: parseInt(process.env.BATCH_DELAY || "500", 10),
  },

  // Browser settings
  browser: {
    headless: process.env.HEADLESS !== "false",
    userAgent:
      process.env.USER_AGENT ||
      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
  },
} as const;

/**
 * Validate required configuration
 */
export function validateConfig(): { valid: boolean; errors: string[] } {
  const errors: string[] = [];

  // Firecrawl API key is required for contact lookup
  // (but not required if only using DIBBS/WBParts)

  return {
    valid: errors.length === 0,
    errors,
  };
}

/**
 * Check if Firecrawl is configured
 */
export function isFirecrawlConfigured(): boolean {
  return Boolean(config.firecrawl.apiKey && config.firecrawl.apiKey.startsWith("fc-"));
}

export default config;
