/**
 * Firecrawl API Client
 *
 * Handles supplier contact discovery using Firecrawl's Search and Scrape APIs.
 * Uses cascading search strategies to find company websites and extract contact info.
 */

import { config, isFirecrawlConfigured } from "./config.js";
import type {
  SupplierContact,
  FirecrawlSearchResult,
  FirecrawlExtractedContact,
  ContactPerson,
} from "./types.js";

/**
 * Firecrawl API response types
 */
interface FirecrawlSearchResponse {
  success: boolean;
  data?: {
    web?: Array<{
      url: string;
      title: string;
      description: string;
      position: number;
    }>;
  };
  error?: string;
}

interface FirecrawlScrapeResponse {
  success: boolean;
  data?: {
    markdown?: string;
    metadata?: {
      title?: string;
      description?: string;
    };
    json?: FirecrawlExtractedContact;
  };
  error?: string;
}

/**
 * Make a request to Firecrawl API
 */
async function firecrawlRequest<T>(
  endpoint: string,
  body: Record<string, unknown>
): Promise<T> {
  const url = `${config.firecrawl.apiUrl}${endpoint}`;

  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${config.firecrawl.apiKey}`,
    },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(config.firecrawl.timeout),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Firecrawl API error (${response.status}): ${errorText}`);
  }

  return response.json() as Promise<T>;
}

/**
 * Search for a company's website using cascading strategies
 */
export async function searchSupplierWebsite(
  companyName: string,
  cageCode?: string
): Promise<FirecrawlSearchResult | null> {
  if (!isFirecrawlConfigured()) {
    console.error("Firecrawl API key not configured. Skipping contact lookup.");
    return null;
  }

  // Cascading search strategies
  const searchStrategies = [
    `${companyName} contact`,
    cageCode ? `${companyName} ${cageCode}` : null,
    companyName,
  ].filter(Boolean) as string[];

  for (const query of searchStrategies) {
    try {
      console.error(`Searching Firecrawl: "${query}"...`);

      const response = await firecrawlRequest<FirecrawlSearchResponse>(
        "/search",
        {
          query,
          limit: 5,
          sources: ["web"],
        }
      );

      if (response.success && response.data?.web?.length) {
        // Filter for likely company websites (not social media, directories, etc.)
        const relevantResults = response.data.web.filter((result) => {
          const url = result.url.toLowerCase();
          const title = result.title.toLowerCase();
          const companyLower = companyName.toLowerCase().split(/\s+/)[0]; // First word of company

          // Exclude common directories and social media
          const excludePatterns = [
            "linkedin.com",
            "facebook.com",
            "twitter.com",
            "youtube.com",
            "yelp.com",
            "yellowpages.com",
            "manta.com",
            "dnb.com",
            "bloomberg.com",
            "zoominfo.com",
            "crunchbase.com",
          ];

          const isExcluded = excludePatterns.some((pattern) =>
            url.includes(pattern)
          );

          // Prefer results that mention the company name
          const mentionsCompany =
            title.includes(companyLower) || url.includes(companyLower);

          return !isExcluded && mentionsCompany;
        });

        if (relevantResults.length > 0) {
          const best = relevantResults[0];
          console.error(`Found company website: ${best.url}`);
          return {
            url: best.url,
            title: best.title,
            description: best.description,
          };
        }

        // If no filtered results, return first result
        const first = response.data.web[0];
        console.error(`Using first result: ${first.url}`);
        return {
          url: first.url,
          title: first.title,
          description: first.description,
        };
      }
    } catch (error) {
      console.error(`Search failed for "${query}":`, error);
      // Continue to next strategy
    }
  }

  console.error(`No website found for: ${companyName}`);
  return null;
}

/**
 * Find the contact page URL from a website
 */
function findContactPageUrl(baseUrl: string): string {
  // Common contact page patterns
  const url = new URL(baseUrl);
  const basePath = `${url.protocol}//${url.host}`;

  // If already on a contact page, use it
  if (
    baseUrl.includes("/contact") ||
    baseUrl.includes("/about") ||
    baseUrl.includes("/reach")
  ) {
    return baseUrl;
  }

  // Default to /contact
  return `${basePath}/contact`;
}

/**
 * Extract contact information from a website using Firecrawl
 */
export async function extractContactInfo(
  websiteUrl: string,
  companyName: string
): Promise<SupplierContact> {
  const emptyContact: SupplierContact = {
    companyName,
    email: null,
    phone: null,
    address: null,
    website: websiteUrl,
    contactPage: null,
    additionalContacts: [],
    source: "firecrawl_scrape",
    confidence: "low",
    scrapedAt: new Date().toISOString(),
  };

  if (!isFirecrawlConfigured()) {
    return emptyContact;
  }

  // Try multiple URLs: the given URL, then /contact page
  const urlsToTry = [websiteUrl, findContactPageUrl(websiteUrl)];

  for (const url of urlsToTry) {
    try {
      console.error(`Scraping contact info from: ${url}...`);

      const response = await firecrawlRequest<FirecrawlScrapeResponse>(
        "/scrape",
        {
          url,
          formats: [
            "markdown",
            {
              type: "json",
              prompt:
                "Extract all contact information from this page including: email addresses, phone numbers, physical address, and any contact persons with their names, titles, emails, and phone numbers. Focus on sales, business, or general contact information.",
              schema: {
                type: "object",
                properties: {
                  emails: {
                    type: "array",
                    items: { type: "string" },
                    description: "All email addresses found on the page",
                  },
                  phones: {
                    type: "array",
                    items: { type: "string" },
                    description: "All phone numbers found on the page",
                  },
                  address: {
                    type: "string",
                    description: "Physical/mailing address of the company",
                  },
                  contactPersons: {
                    type: "array",
                    items: {
                      type: "object",
                      properties: {
                        name: { type: "string" },
                        title: { type: "string" },
                        email: { type: "string" },
                        phone: { type: "string" },
                      },
                    },
                    description: "Individual contact persons found",
                  },
                },
              },
            },
          ],
          timeout: config.firecrawl.timeout,
        }
      );

      if (response.success && response.data?.json) {
        const extracted = response.data.json;

        // Determine confidence based on data quality
        let confidence: "high" | "medium" | "low" = "low";
        const hasEmail = extracted.emails && extracted.emails.length > 0;
        const hasPhone = extracted.phones && extracted.phones.length > 0;
        const hasAddress = Boolean(extracted.address);

        if (hasEmail && hasPhone && hasAddress) {
          confidence = "high";
        } else if (hasEmail || hasPhone) {
          confidence = "medium";
        }

        // Format the contact
        const contact: SupplierContact = {
          companyName,
          email: extracted.emails?.[0] || null,
          phone: extracted.phones?.[0] || null,
          address: extracted.address || null,
          website: websiteUrl,
          contactPage: url !== websiteUrl ? url : null,
          additionalContacts: formatContactPersons(extracted.contactPersons),
          source: "firecrawl_scrape",
          confidence,
          scrapedAt: new Date().toISOString(),
        };

        // If we got good data, return it
        if (confidence !== "low") {
          console.error(
            `Extracted contact info (${confidence} confidence): email=${contact.email}, phone=${contact.phone}`
          );
          return contact;
        }
      }
    } catch (error) {
      console.error(`Failed to scrape ${url}:`, error);
      // Continue to next URL
    }
  }

  // Return empty contact with the website at least
  console.error(`Could not extract contact info for: ${companyName}`);
  return emptyContact;
}

/**
 * Format contact persons from extracted data
 */
function formatContactPersons(
  persons: ContactPerson[] | undefined
): ContactPerson[] {
  if (!persons || !Array.isArray(persons)) {
    return [];
  }

  return persons
    .filter((p) => p.name || p.email || p.phone)
    .map((p) => ({
      name: p.name?.trim(),
      title: p.title?.trim(),
      email: p.email?.trim(),
      phone: p.phone?.trim(),
    }));
}

/**
 * Find supplier contact information
 * Combined workflow: search for website, then extract contact info
 */
export async function findSupplierContact(
  companyName: string,
  cageCode?: string,
  knownWebsite?: string
): Promise<SupplierContact> {
  // If we already have a website, skip search
  let websiteUrl = knownWebsite;

  if (!websiteUrl) {
    // Search for the company website
    const searchResult = await searchSupplierWebsite(companyName, cageCode);
    if (searchResult) {
      websiteUrl = searchResult.url;
    }
  }

  if (!websiteUrl) {
    // No website found
    return {
      companyName,
      email: null,
      phone: null,
      address: null,
      website: null,
      contactPage: null,
      additionalContacts: [],
      source: "firecrawl_search",
      confidence: "low",
      scrapedAt: new Date().toISOString(),
    };
  }

  // Extract contact info from the website
  return extractContactInfo(websiteUrl, companyName);
}

/**
 * Find contacts for multiple suppliers
 */
export async function findMultipleSupplierContacts(
  suppliers: Array<{ companyName: string; cageCode?: string }>
): Promise<Map<string, SupplierContact>> {
  const contacts = new Map<string, SupplierContact>();

  for (const supplier of suppliers) {
    const contact = await findSupplierContact(
      supplier.companyName,
      supplier.cageCode
    );
    contacts.set(supplier.companyName, contact);

    // Rate limiting
    await new Promise((resolve) =>
      setTimeout(resolve, config.rateLimit.batchDelay)
    );
  }

  return contacts;
}
