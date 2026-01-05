/**
 * DIBBS RFQ Data Types
 *
 * These interfaces represent the data structure extracted from the
 * Defense Logistics Agency Internet Bid Board System (DIBBS)
 */

/**
 * Approved source data from the RFQ
 */
export interface ApprovedSource {
  cageCode: string;
  partNumber: string;
  companyName: string;
}

/**
 * Individual solicitation/RFQ entry
 */
export interface Solicitation {
  solicitationNumber: string;
  solicitationUrl: string | null;
  technicalDocuments: string;
  prNumber: string;
  quantity: number;
  issueDate: string;
  returnByDate: string;
}

/**
 * Complete RFQ data extracted from DIBBS
 */
export interface RFQData {
  /** National Stock Number (e.g., "4520-01-261-9675") */
  nsn: string;

  /** Item description (e.g., "HEATER,VENTILATION") */
  nomenclature: string;

  /** Acquisition Method Suffix Code */
  amsc: string;

  /** Approved source data (manufacturers) */
  approvedSources: ApprovedSource[];

  /** Active solicitations */
  solicitations: Solicitation[];

  /** Whether any OPEN RFQs exist */
  hasOpenRFQs: boolean;

  /** Timestamp of extraction */
  scrapedAt: string;

  /** Source URL */
  sourceUrl: string;
}

/**
 * Scraper result including error handling
 */
export interface ScrapeResult {
  success: boolean;
  data: RFQData | null;
  error: string | null;
}

// ============================================
// WBParts Types
// ============================================

/**
 * Manufacturer data from WBParts
 */
export interface WBPartsManufacturer {
  partNumber: string;
  cageCode: string;
  companyName: string;
}

/**
 * Technical specification from WBParts
 */
export interface WBPartsTechSpec {
  name: string;
  value: string;
}

/**
 * Demand history entry from WBParts
 */
export interface WBPartsDemand {
  partNumber: string;
  requestDate: string;
  quantity: number;
  origin: string;
}

/**
 * Complete WBParts data
 */
export interface WBPartsData {
  /** National Stock Number */
  nsn: string;

  /** Item name/description */
  itemName: string;

  /** INC (Item Name Code) */
  incCode: string;

  /** Part number alternates */
  partAlternates: string[];

  /** Manufacturer data */
  manufacturers: WBPartsManufacturer[];

  /** Technical specifications */
  techSpecs: WBPartsTechSpec[];

  /** Recent demand history */
  demandHistory: WBPartsDemand[];

  /** Assignment date */
  assignmentDate: string;

  /** Source URL */
  sourceUrl: string;

  /** Timestamp of extraction */
  scrapedAt: string;
}

/**
 * WBParts scraper result
 */
export interface WBPartsScrapeResult {
  success: boolean;
  data: WBPartsData | null;
  error: string | null;
}

// ============================================
// Combined Multi-Source Types
// ============================================

/**
 * Combined data from multiple sources
 */
export interface CombinedRFQData {
  /** DIBBS data (source of truth for OPEN status) */
  dibbs: RFQData | null;

  /** WBParts data (secondary confirmation, manufacturer details) */
  wbparts: WBPartsData | null;

  /** Whether RFQ is currently OPEN (from DIBBS) */
  hasOpenRFQ: boolean;

  /** Primary manufacturer/company name */
  primaryCompany: string | null;

  /** Primary CAGE code */
  primaryCageCode: string | null;

  /** Merged data summary */
  summary: {
    nsn: string;
    itemName: string;
    companyNames: string[];
    cageCodes: string[];
    partNumbers: string[];
  };
}

/**
 * Combined scraper result
 */
export interface CombinedScrapeResult {
  success: boolean;
  data: CombinedRFQData | null;
  dibbsError: string | null;
  wbpartsError: string | null;
}

// ============================================
// Supplier Contact Types (Firecrawl Integration)
// ============================================

/**
 * Contact person at a supplier
 */
export interface ContactPerson {
  name?: string;
  title?: string;
  email?: string;
  phone?: string;
}

/**
 * Supplier contact information extracted via Firecrawl
 */
export interface SupplierContact {
  /** Company name */
  companyName: string;

  /** Primary email address */
  email: string | null;

  /** Primary phone number */
  phone: string | null;

  /** Physical address */
  address: string | null;

  /** Company website URL */
  website: string | null;

  /** Contact page URL */
  contactPage: string | null;

  /** Additional contact persons found */
  additionalContacts: ContactPerson[];

  /** Data source */
  source: "firecrawl_search" | "firecrawl_scrape" | "manual";

  /** Confidence level */
  confidence: "high" | "medium" | "low";

  /** Timestamp of extraction */
  scrapedAt: string;
}

/**
 * Supplier with RFQ data and contact info combined
 */
export interface SupplierWithContact {
  companyName: string;
  cageCode: string;
  partNumber: string;
  contact: SupplierContact | null;
}

/**
 * Enhanced RFQ result with supplier contacts
 */
export interface EnhancedRFQResult {
  /** National Stock Number */
  nsn: string;

  /** Item name/nomenclature */
  itemName: string;

  /** Whether RFQ is open */
  hasOpenRFQ: boolean;

  /** Suppliers with contact information */
  suppliers: SupplierWithContact[];

  /** Raw data from scrapers */
  rawData: {
    dibbs: RFQData | null;
    wbparts: WBPartsData | null;
  };

  /** Workflow status */
  workflow: {
    dibbsStatus: "success" | "error" | "skipped";
    wbpartsStatus: "success" | "error" | "skipped";
    firecrawlStatus: "success" | "error" | "skipped" | "partial";
  };

  /** Timestamp */
  scrapedAt: string;
}

/**
 * Firecrawl search result
 */
export interface FirecrawlSearchResult {
  url: string;
  title: string;
  description: string;
}

/**
 * Firecrawl extracted contact data
 */
export interface FirecrawlExtractedContact {
  emails: string[];
  phones: string[];
  address: string | null;
  contactPersons: ContactPerson[];
}
