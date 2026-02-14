"""
FastAPI REST API

REST API for batch processing NSNs with date-based scraping and Google Sheets export.
"""

import asyncio
import time
import uuid
from contextlib import asynccontextmanager
from typing import List, Optional

import httpx
from fastapi import FastAPI, HTTPException, Request, Security, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from config import config
from core import scrape_batch, flatten_batch_results, scrape_nsn, flatten_to_rows
from scrapers.browser_pool import browser_pool
from scrapers.dibbs_date import scrape_nsns_by_date, scrape_available_dates
from scrapers.sam_gov import search_opportunities
from scrapers.canada_buys import search_tenders as search_canada_tenders
from scrapers.alberta_purchasing import search_opportunities as search_apc
from services.document import download_document, extract_text_from_pdf, parse_bid_package
from services.llm import classify_conversation_stage, draft_reply, extract_quote_data
from services.normalizer import normalize_any
from utils.logging import get_logger, set_request_id, get_request_id

logger = get_logger(__name__)


# ── Error helpers ───────────────────────────────────────────────────

def _error_response(status_code: int, message: str) -> JSONResponse:
    """Build a structured JSON error response with request_id."""
    body = {"error": message, "status": status_code}
    rid = get_request_id()
    if rid:
        body["request_id"] = rid
    return JSONResponse(status_code=status_code, content=body)

# Rate limiter
limiter = Limiter(key_func=get_remote_address)


# API Key Authentication
API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_api_key(api_key: str = Security(API_KEY_HEADER)):
    """
    Verify API key from X-API-Key header.

    If RFQ_API_KEY is not set, authentication is disabled (for development).
    """
    expected_key = getattr(config, "RFQ_API_KEY", "")
    if expected_key and api_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return api_key


# Pydantic models for API
class BatchRequest(BaseModel):
    """Request body for batch processing."""
    nsns: List[str] = Field(..., description="List of NSNs to process")


class SupplierRow(BaseModel):
    """Flat supplier row in response."""
    nsn: str
    open_status: str
    supplier_name: str
    cage_code: str
    email: str
    phone: str


class BatchSummary(BaseModel):
    """Summary statistics for batch processing."""
    total_nsns: int
    total_rows: int
    successful: int
    failed: int


class BatchResponse(BaseModel):
    """Response body for batch processing."""
    results: List[SupplierRow]
    summary: BatchSummary


class HealthCheck(BaseModel):
    """Individual health check result."""
    configured: bool
    provider: Optional[str] = None

class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    checks: dict


# New Phase 2 Models

class ScrapeByDateRequest(BaseModel):
    """Request body for date-based NSN scraping."""
    date: str = Field(..., description="Date in MM-DD-YYYY format (e.g., '01-12-2026')")
    maxPages: int = Field(default=0, description="Max pages to scrape (0 = all pages)")


class NSNItem(BaseModel):
    """Individual NSN data from date scrape."""
    nsn: str
    nomenclature: str
    solicitation: str
    quantity: int
    issueDate: str
    returnByDate: str


class ScrapeByDateResponse(BaseModel):
    """Response body for date-based NSN scraping."""
    date: str
    totalPages: int
    pagesScraped: int
    totalNsns: int
    nsns: List[NSNItem]
    scrapedAt: str
    error: Optional[str] = None


class ScrapeNSNSuppliersRequest(BaseModel):
    """Request body for NSN supplier scraping."""
    nsn: str = Field(..., description="NSN to scrape suppliers for")
    maxSuppliers: int = Field(default=5, description="Max suppliers for contact discovery (0 = all)")


class SupplierInfo(BaseModel):
    """Supplier contact information."""
    companyName: str
    cageCode: str
    partNumber: str
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    website: Optional[str] = None
    confidence: str


class ScrapeNSNSuppliersResponse(BaseModel):
    """Response body for NSN supplier scraping."""
    nsn: str
    nomenclature: str
    hasOpenRfq: bool
    suppliers: List[SupplierInfo]
    timedOut: bool = False


class BatchSuppliersRequest(BaseModel):
    """Request body for batch NSN supplier scraping."""
    nsns: List[str] = Field(..., description="List of NSNs to scrape suppliers for")
    maxSuppliers: int = Field(default=5, description="Max suppliers per NSN for contact discovery (0 = all)")


class BatchSuppliersNSNResult(BaseModel):
    """Result for a single NSN in a batch supplier scrape."""
    nsn: str
    status: str
    nomenclature: Optional[str] = None
    hasOpenRfq: Optional[bool] = None
    suppliers: List[SupplierInfo] = Field(default_factory=list)
    timedOut: bool = False
    error: Optional[str] = None


class BatchSuppliersResponse(BaseModel):
    """Response body for batch NSN supplier scraping."""
    results: List[BatchSuppliersNSNResult]
    totalNsns: int
    successful: int
    failed: int


class AvailableDatesResponse(BaseModel):
    """Response body for available dates."""
    dates: List[str]
    totalDates: int
    scrapedAt: str


# SAM.gov Models

class SAMSearchRequest(BaseModel):
    """Request body for SAM.gov opportunity search."""
    daysBack: int = Field(default=7, description="Number of days to look back for opportunities")
    setAside: Optional[str] = Field(default=None, description="Set-aside type code (e.g., 'SBA', '8A', 'HZC')")
    ptype: Optional[str] = Field(default=None, description="Procurement type code (e.g., 'o' for Solicitation)")
    naicsCode: Optional[str] = Field(default=None, description="NAICS code filter")
    keyword: Optional[str] = Field(default=None, description="Keyword to search in titles")
    maxPages: int = Field(default=5, description="Maximum pages to fetch (default 5)")
    enrichContacts: Optional[bool] = Field(default=None, description="Fetch contacts from detail pages (None = use config default)")


class SAMContactResponse(BaseModel):
    """Point of contact from SAM.gov."""
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    type: Optional[str] = None


class SAMOpportunityResponse(BaseModel):
    """Individual SAM.gov opportunity in response."""
    title: str = ""
    solicitationNumber: Optional[str] = None
    noticeId: Optional[str] = None
    department: Optional[str] = None
    agency: Optional[str] = None
    postedDate: Optional[str] = None
    responseDeadline: Optional[str] = None
    setAside: Optional[str] = None
    naicsCode: Optional[str] = None
    classificationCode: Optional[str] = None
    description: Optional[str] = None
    placeOfPerformance: Optional[str] = None
    pointOfContact: List[SAMContactResponse] = Field(default_factory=list)
    attachmentLinks: List[str] = Field(default_factory=list)
    sourceUrl: str = ""
    noticeType: Optional[str] = None


class SAMSearchResponse(BaseModel):
    """Response body for SAM.gov opportunity search."""
    source: str = "sam_gov"
    totalPages: int = 0
    pagesScraped: int = 0
    totalOpportunities: int = 0
    opportunities: List[SAMOpportunityResponse] = Field(default_factory=list)
    scrapedAt: str = ""
    error: Optional[str] = None


# Document Intelligence Models

class ExtractDocumentRequest(BaseModel):
    """Request body for document extraction."""
    url: str = Field(..., description="URL to the PDF document")
    extractFields: Optional[List[str]] = Field(
        default=None,
        description="Fields to extract: eligibility, specs, quantity, delivery, deadlines. None = all."
    )


class ExtractDocumentResponse(BaseModel):
    """Response body for document extraction."""
    url: str
    text: str
    parsed: dict
    pageCount: int = 0


# Canadian Portal Models

class CanadaBuysRequest(BaseModel):
    """Request body for Canada Buys search."""
    keywords: Optional[str] = Field(default=None, description="Keyword filter for tender titles")
    daysBack: int = Field(default=7, description="Number of days to look back")
    maxResults: int = Field(default=200, description="Maximum results to return")


class CanadaBuysTender(BaseModel):
    """Individual Canada Buys tender."""
    title: str = ""
    solicitationNumber: str = ""
    status: str = ""
    publishedDate: str = ""
    closingDate: str = ""
    category: str = ""
    region: str = ""
    organization: str = ""
    procurementType: str = ""
    contactName: str = ""
    contactEmail: str = ""
    description: str = ""
    sourceUrl: str = ""
    source: str = "canada_buys"


class CanadaBuysResponse(BaseModel):
    """Response for Canada Buys search."""
    source: str = "canada_buys"
    totalTenders: int = 0
    tenders: List[CanadaBuysTender] = Field(default_factory=list)
    scrapedAt: str = ""


class AlbertaPurchasingRequest(BaseModel):
    """Request body for Alberta Purchasing Connection search."""
    keywords: str = Field(default="", description="Keyword search")
    daysBack: int = Field(default=7, description="Number of days to look back")
    maxResults: int = Field(default=100, description="Maximum results to return")
    statusFilter: str = Field(default="OPEN", description="Status filter: OPEN, CLOSED, AWARD, CANCELLED, EVALUATION, EXPIRED. Empty for all.")
    solicitationType: Optional[str] = Field(default=None, description="Solicitation type: RFQ, RFP, ITB, NRFP, RFEI, etc.")
    category: Optional[str] = Field(default=None, description="Category: GD (Goods), SRV (Services), CNST (Construction)")
    enrichContacts: Optional[bool] = Field(default=None, description="Fetch contacts from detail pages (None = use config default)")


class APCOpportunity(BaseModel):
    """Individual Alberta Purchasing Connection opportunity."""
    title: str = ""
    referenceNumber: str = ""
    solicitationNumber: str = ""
    status: str = ""
    publishedDate: str = ""
    closingDate: str = ""
    organization: str = ""
    categoryCode: str = ""
    solicitationTypeCode: str = ""
    opportunityTypeCode: str = ""
    description: str = ""
    commodityCodes: List[str] = Field(default_factory=list)
    regionOfDelivery: List[str] = Field(default_factory=list)
    sourceUrl: str = ""
    source: str = "alberta_purchasing"
    contactName: str = ""
    contactTitle: str = ""
    contactEmail: str = ""
    contactPhone: str = ""
    contactAddress: str = ""


class AlbertaPurchasingResponse(BaseModel):
    """Response for Alberta Purchasing search."""
    source: str = "alberta_purchasing"
    totalOpportunities: int = 0
    totalAvailable: int = 0
    opportunities: List[APCOpportunity] = Field(default_factory=list)
    scrapedAt: str = ""


# Email Automation Models

class EmailMessage(BaseModel):
    """Single email in a thread."""
    # 'from' is reserved in Python, use alias
    sender: str = Field(..., alias="from", description="'us' or 'supplier'")
    body: str = Field(..., description="Email body text")

    class Config:
        populate_by_name = True


class ClassifyThreadRequest(BaseModel):
    """Request body for email thread classification."""
    thread: List[EmailMessage] = Field(..., description="Email thread messages")


class ClassifyThreadResponse(BaseModel):
    """Response for thread classification."""
    stage: str
    stages: List[str] = Field(
        default=["Outreach Sent", "Quote Received", "Substitute y/n", "Send", "Not Yet"]
    )


class DraftReplyRequest(BaseModel):
    """Request body for drafting a reply."""
    thread: List[EmailMessage] = Field(..., description="Email thread messages")
    stage: Optional[str] = Field(default=None, description="Override conversation stage")
    context: Optional[dict] = Field(default=None, description="Additional context (nsn, partNumber, quantity, etc.)")


class DraftReplyResponse(BaseModel):
    """Response for draft reply."""
    stage: str
    draft: str


class ExtractQuoteRequest(BaseModel):
    """Request body for quote data extraction."""
    text: str = Field(..., description="Text containing quote information")


class ExtractQuoteResponse(BaseModel):
    """Response for quote extraction."""
    data: dict


@asynccontextmanager
async def lifespan(app):
    """Start shared browser pool on startup, stop on shutdown."""
    await browser_pool.start()
    yield
    await browser_pool.stop()


# Create FastAPI app
app = FastAPI(
    title="RFQ Automation API",
    description="REST API for batch processing NSNs and discovering supplier contacts",
    version="2.0.0",
    lifespan=lifespan,
)

# Rate limiter state
app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    logger.warning("Rate limit exceeded: %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=429,
        content={"detail": "Rate limit exceeded. Please try again later."},
    )


# Request logging middleware with correlation ID
@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    # Generate or accept correlation ID
    rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:8]
    set_request_id(rid)

    start = time.time()
    response = await call_next(request)
    duration_ms = (time.time() - start) * 1000

    # Include request_id in response header
    response.headers["X-Request-ID"] = rid

    logger.info(
        "%s %s %d %.0fms",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response


# Add CORS middleware for browser access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint with service status."""
    import shutil

    playwright_installed = shutil.which("chromium") is not None or shutil.which("chromium-browser") is not None
    # Also check playwright's own browser path
    if not playwright_installed:
        try:
            from pathlib import Path
            import os
            pw_browsers = Path(os.path.expanduser("~")) / ".cache" / "ms-playwright"
            playwright_installed = pw_browsers.exists() and any(pw_browsers.iterdir())
        except Exception:
            pass

    checks = {
        "llm": {
            "configured": config.is_llm_configured(),
            "provider": "openrouter" if config.is_llm_configured() else None,
        },
        "firecrawl": {
            "configured": config.is_firecrawl_configured(),
        },
        "playwright": {
            "installed": playwright_installed,
        },
        "browser_pool": {
            "started": browser_pool._started,
            "max_pages": config.MAX_BROWSER_PAGES,
        },
    }

    # Determine overall status
    # browser_pool.started is the reliable indicator — shutil.which misses
    # Playwright-managed browsers inside Docker
    can_scrape = playwright_installed or browser_pool._started
    if not can_scrape:
        status = "unhealthy"
    elif not config.is_firecrawl_configured() or not config.is_llm_configured():
        status = "degraded"
    else:
        status = "healthy"

    return HealthResponse(status=status, checks=checks)


@app.get("/", response_model=HealthResponse)
async def root_health():
    """Root health check for Railway deployment."""
    return await health_check()


@app.post("/api/batch", response_model=BatchResponse)
@limiter.limit("5/minute")
async def process_batch(request: Request, body: BatchRequest):
    """
    Process a batch of NSNs.

    Accepts a list of NSNs and returns flattened supplier data with one row per supplier.
    """
    if not body.nsns:
        raise HTTPException(status_code=400, detail="No NSNs provided")

    if len(body.nsns) > 500:
        raise HTTPException(
            status_code=400,
            detail="Maximum 500 NSNs per batch request"
        )

    try:
        batch_result = await scrape_batch(body.nsns)
        flat_rows = flatten_batch_results(batch_result)

        supplier_rows = [
            SupplierRow(
                nsn=row["nsn"],
                open_status=row["open_status"],
                supplier_name=row["supplier_name"],
                cage_code=row["cage_code"],
                email=row["email"],
                phone=row["phone"]
            )
            for row in flat_rows
        ]

        return BatchResponse(
            results=supplier_rows,
            summary=BatchSummary(
                total_nsns=batch_result.total_nsns,
                total_rows=len(flat_rows),
                successful=batch_result.successful,
                failed=batch_result.failed
            )
        )
    except asyncio.TimeoutError:
        logger.error("Batch processing timed out")
        return _error_response(504, "Batch processing timed out")
    except Exception as e:
        logger.error("Batch processing failed: %s", e, exc_info=True)
        return _error_response(500, "Batch processing failed")


# ============================================
# Phase 2 Endpoints (with API Key Auth)
# ============================================

@app.post("/api/scrape-nsns-by-date", response_model=ScrapeByDateResponse)
@limiter.limit("5/minute")
async def scrape_nsns_by_date_endpoint(
    request: Request,
    body: ScrapeByDateRequest,
    api_key: str = Depends(verify_api_key)
):
    """
    Scrape all NSNs from DIBBS for a given date.

    Returns NSNs with metadata (does NOT include supplier contacts).
    """
    try:
        logger.info("scrape-nsns-by-date: starting", date=body.date, max_pages=body.maxPages)

        async def _scrape_with_pool():
            pool_start = time.monotonic()
            async with browser_pool.get_context() as ctx:
                pool_wait = time.monotonic() - pool_start
                if pool_wait > 5:
                    logger.warning(
                        "scrape-nsns-by-date waited %.1fs for browser page",
                        pool_wait,
                    )
                return await scrape_nsns_by_date(
                    date=body.date,
                    max_pages=body.maxPages,
                    browser_context=ctx,
                )

        result = await asyncio.wait_for(_scrape_with_pool(), timeout=280)

        logger.info(
            "scrape-nsns-by-date: completed, found %d NSNs across %d/%d pages",
            result["totalNsns"], result["pagesScraped"], result["totalPages"],
            date=body.date,
        )

        return ScrapeByDateResponse(
            date=result["date"],
            totalPages=result["totalPages"],
            pagesScraped=result["pagesScraped"],
            totalNsns=result["totalNsns"],
            nsns=[
                NSNItem(
                    nsn=nsn["nsn"],
                    nomenclature=nsn["nomenclature"],
                    solicitation=nsn["solicitation"],
                    quantity=nsn["quantity"],
                    issueDate=nsn["issueDate"],
                    returnByDate=nsn["returnByDate"]
                )
                for nsn in result["nsns"]
            ],
            scrapedAt=result["scrapedAt"],
            error=result.get("error")
        )

    except asyncio.TimeoutError:
        logger.error("scrape-nsns-by-date timed out after 280s")
        return _error_response(504, "DIBBS date scrape timed out")
    except RuntimeError as e:
        logger.error("scrape-nsns-by-date unavailable: %s", e)
        return _error_response(503, "DIBBS scraper temporarily unavailable")
    except Exception as e:
        logger.error("scrape-nsns-by-date failed: %s", e, exc_info=True)
        return _error_response(500, f"Scraping failed: {type(e).__name__}: {e}")


@app.post("/api/scrape-nsn-suppliers", response_model=ScrapeNSNSuppliersResponse)
@limiter.limit("20/minute")
async def scrape_nsn_suppliers_endpoint(
    request: Request,
    body: ScrapeNSNSuppliersRequest,
    api_key: str = Depends(verify_api_key)
):
    """
    Scrape supplier contact information for a specific NSN.

    Only returns HIGH and MEDIUM confidence contacts (filters out LOW).
    """
    try:
        logger.info("scrape-nsn-suppliers: starting", nsn=body.nsn, max_suppliers=body.maxSuppliers)

        result = await asyncio.wait_for(
            scrape_nsn(body.nsn, max_suppliers=body.maxSuppliers, timeout_seconds=180),
            timeout=280,
        )

        # Filter to HIGH and MEDIUM confidence only
        filtered_suppliers = []
        for supplier in result.suppliers:
            confidence = "low"
            if supplier.contact:
                confidence = supplier.contact.confidence

            # Only include HIGH and MEDIUM
            if confidence in ["high", "medium"]:
                filtered_suppliers.append(SupplierInfo(
                    companyName=supplier.company_name,
                    cageCode=supplier.cage_code,
                    partNumber=supplier.part_number,
                    email=supplier.contact.email if supplier.contact else None,
                    phone=supplier.contact.phone if supplier.contact else None,
                    address=supplier.contact.address if supplier.contact else None,
                    website=supplier.contact.website if supplier.contact else None,
                    confidence=confidence
                ))

        logger.info(
            "scrape-nsn-suppliers: completed, %d suppliers (filtered from %d total)",
            len(filtered_suppliers), len(result.suppliers),
            nsn=body.nsn,
            timed_out=result.workflow.firecrawl_status == "partial_timeout",
        )

        return ScrapeNSNSuppliersResponse(
            nsn=result.nsn,
            nomenclature=result.item_name or "",
            hasOpenRfq=result.has_open_rfq,
            suppliers=filtered_suppliers,
            timedOut=result.workflow.firecrawl_status == "partial_timeout"
        )

    except asyncio.TimeoutError:
        logger.error("scrape-nsn-suppliers timed out after 280s", nsn=body.nsn)
        return _error_response(504, "Supplier scrape timed out")
    except RuntimeError as e:
        logger.error("scrape-nsn-suppliers unavailable: %s", e)
        return _error_response(503, "Supplier scraper temporarily unavailable")
    except Exception as e:
        logger.error("scrape-nsn-suppliers failed: %s", e, exc_info=True)
        return _error_response(500, f"Scraping failed: {type(e).__name__}: {e}")


@app.post("/api/scrape-nsns-suppliers-batch", response_model=BatchSuppliersResponse)
@limiter.limit("20/minute")
async def scrape_nsns_suppliers_batch_endpoint(
    request: Request,
    body: BatchSuppliersRequest,
    api_key: str = Depends(verify_api_key)
):
    """
    Scrape supplier contact information for multiple NSNs in one call.

    Processes NSNs with controlled concurrency (2 at a time to match browser pool).
    Only returns HIGH and MEDIUM confidence contacts.
    """
    if not body.nsns:
        raise HTTPException(status_code=400, detail="No NSNs provided")
    if len(body.nsns) > 50:
        raise HTTPException(status_code=400, detail="Maximum 50 NSNs per batch request")

    NSN_CONCURRENCY = 2  # 2 NSNs × 2 pages each = 4 browser pages (matches pool)

    logger.info(
        "scrape-nsns-suppliers-batch: starting %d NSNs (max_suppliers=%d)",
        len(body.nsns), body.maxSuppliers,
    )

    async def _scrape_one(nsn: str) -> BatchSuppliersNSNResult:
        try:
            result = await scrape_nsn(
                nsn, max_suppliers=body.maxSuppliers, timeout_seconds=180
            )

            filtered = []
            for supplier in result.suppliers:
                confidence = "low"
                if supplier.contact:
                    confidence = supplier.contact.confidence
                if confidence in ["high", "medium"]:
                    filtered.append(SupplierInfo(
                        companyName=supplier.company_name,
                        cageCode=supplier.cage_code,
                        partNumber=supplier.part_number,
                        email=supplier.contact.email if supplier.contact else None,
                        phone=supplier.contact.phone if supplier.contact else None,
                        address=supplier.contact.address if supplier.contact else None,
                        website=supplier.contact.website if supplier.contact else None,
                        confidence=confidence,
                    ))

            return BatchSuppliersNSNResult(
                nsn=result.nsn,
                status="success",
                nomenclature=result.item_name or "",
                hasOpenRfq=result.has_open_rfq,
                suppliers=filtered,
                timedOut=result.workflow.firecrawl_status == "partial_timeout",
            )
        except Exception as e:
            logger.warning("Batch supplier scrape failed for NSN %s: %s", nsn, e)
            return BatchSuppliersNSNResult(
                nsn=nsn,
                status="error",
                error=str(e),
            )

    nsn_sem = asyncio.Semaphore(NSN_CONCURRENCY)

    async def _limited_scrape(nsn: str) -> BatchSuppliersNSNResult:
        async with nsn_sem:
            return await _scrape_one(nsn)

    try:
        results = await asyncio.wait_for(
            asyncio.gather(*[_limited_scrape(nsn) for nsn in body.nsns]),
            timeout=600,
        )

        successful = sum(1 for r in results if r.status == "success")
        failed = sum(1 for r in results if r.status == "error")

        logger.info(
            "scrape-nsns-suppliers-batch: completed %d/%d successful",
            successful, len(body.nsns),
        )

        return BatchSuppliersResponse(
            results=list(results),
            totalNsns=len(body.nsns),
            successful=successful,
            failed=failed,
        )

    except asyncio.TimeoutError:
        logger.error("scrape-nsns-suppliers-batch timed out after 600s")
        return _error_response(504, "Batch supplier scrape timed out")
    except Exception as e:
        logger.error("scrape-nsns-suppliers-batch failed: %s", e, exc_info=True)
        return _error_response(500, "Batch supplier scrape failed")


@app.get("/api/available-dates", response_model=AvailableDatesResponse)
@limiter.limit("5/minute")
async def get_available_dates(request: Request, api_key: str = Depends(verify_api_key)):
    """
    Get available RFQ issue dates from DIBBS.
    """
    try:
        async with browser_pool.get_context() as ctx:
            result = await asyncio.wait_for(
                scrape_available_dates(browser_context=ctx),
                timeout=280,
            )

        return AvailableDatesResponse(
            dates=result["dates"],
            totalDates=result["totalDates"],
            scrapedAt=result["scrapedAt"]
        )

    except asyncio.TimeoutError:
        logger.error("available-dates timed out after 280s")
        return _error_response(504, "Available dates fetch timed out")
    except RuntimeError as e:
        logger.error("available-dates unavailable: %s", e)
        return _error_response(503, "DIBBS scraper temporarily unavailable")
    except Exception as e:
        logger.error("available-dates failed: %s", e, exc_info=True)
        return _error_response(500, "Failed to fetch dates")


@app.post("/api/search-sam", response_model=SAMSearchResponse)
@limiter.limit("5/minute")
async def search_sam_endpoint(
    request: Request,
    body: SAMSearchRequest,
    api_key: str = Depends(verify_api_key)
):
    """
    Search SAM.gov for contract opportunities.
    """
    try:
        async with browser_pool.get_context() as ctx:
            result = await asyncio.wait_for(
                search_opportunities(
                    days_back=body.daysBack,
                    set_aside=body.setAside,
                    ptype=body.ptype,
                    naics_code=body.naicsCode,
                    keyword=body.keyword,
                    max_pages=body.maxPages,
                    enrich_contacts=body.enrichContacts,
                    browser_context=ctx,
                ),
                timeout=280,
            )

        # Convert opportunities to response format
        opps = []
        for opp in result.get("opportunities", []):
            contacts = [
                SAMContactResponse(
                    name=c.get("name"),
                    email=c.get("email"),
                    phone=c.get("phone"),
                    type=c.get("type"),
                )
                for c in opp.get("pointOfContact", [])
            ]
            opps.append(SAMOpportunityResponse(
                title=opp.get("title", ""),
                solicitationNumber=opp.get("solicitationNumber"),
                noticeId=opp.get("noticeId"),
                department=opp.get("department"),
                agency=opp.get("agency"),
                postedDate=opp.get("postedDate"),
                responseDeadline=opp.get("responseDeadline"),
                setAside=opp.get("setAside"),
                naicsCode=opp.get("naicsCode"),
                classificationCode=opp.get("classificationCode"),
                description=opp.get("description"),
                placeOfPerformance=opp.get("placeOfPerformance"),
                pointOfContact=contacts,
                attachmentLinks=opp.get("attachmentLinks", []),
                sourceUrl=opp.get("sourceUrl", ""),
                noticeType=opp.get("noticeType"),
            ))

        return SAMSearchResponse(
            source=result.get("source", "sam_gov"),
            totalPages=result.get("totalPages", 0),
            pagesScraped=result.get("pagesScraped", 0),
            totalOpportunities=result.get("totalOpportunities", 0),
            opportunities=opps,
            scrapedAt=result.get("scrapedAt", ""),
            error=result.get("error"),
        )

    except asyncio.TimeoutError:
        logger.error("search-sam timed out after 280s")
        return _error_response(504, "SAM.gov search timed out")
    except RuntimeError as e:
        logger.error("search-sam unavailable: %s", e)
        return _error_response(503, "SAM.gov scraper temporarily unavailable")
    except Exception as e:
        logger.error("search-sam failed: %s", e, exc_info=True)
        return _error_response(500, "SAM.gov search failed")


# ============================================
# Document Intelligence Endpoints
# ============================================

@app.post("/api/extract-document", response_model=ExtractDocumentResponse)
@limiter.limit("5/minute")
async def extract_document_endpoint(
    request: Request,
    body: ExtractDocumentRequest,
    api_key: str = Depends(verify_api_key)
):
    """
    Download and extract text/data from a PDF document URL.
    """
    try:
        pdf_bytes = await download_document(body.url)
        text, page_count = extract_text_from_pdf(pdf_bytes)
        parsed = parse_bid_package(text, body.extractFields)

        return ExtractDocumentResponse(
            url=body.url,
            text=text[:10000],  # Limit text to 10k chars in response
            parsed=parsed,
            pageCount=page_count,
        )

    except ValueError as e:
        return _error_response(400, str(e))
    except httpx.HTTPStatusError as e:
        return _error_response(400, "Failed to download document: HTTP %d" % e.response.status_code)
    except asyncio.TimeoutError:
        logger.error("extract-document timed out")
        return _error_response(504, "Document extraction timed out")
    except Exception as e:
        logger.error("extract-document failed: %s", e, exc_info=True)
        return _error_response(500, "Document extraction failed")


# ============================================
# Canadian Portal Endpoints
# ============================================

@app.post("/api/search-canada-buys", response_model=CanadaBuysResponse)
@limiter.limit("5/minute")
async def search_canada_buys_endpoint(
    request: Request,
    body: CanadaBuysRequest,
    api_key: str = Depends(verify_api_key)
):
    """
    Search Canada Buys (canadabuys.canada.ca) for tender opportunities.
    """
    try:
        result = await asyncio.wait_for(
            search_canada_tenders(
                keywords=body.keywords,
                days_back=body.daysBack,
                max_results=body.maxResults,
            ),
            timeout=110,
        )

        tenders = [
            CanadaBuysTender(**t)
            for t in result.get("tenders", [])
        ]

        return CanadaBuysResponse(
            source=result.get("source", "canada_buys"),
            totalTenders=result.get("totalTenders", 0),
            tenders=tenders,
            scrapedAt=result.get("scrapedAt", ""),
        )

    except asyncio.TimeoutError:
        logger.error("search-canada-buys timed out after 110s")
        return _error_response(504, "Canada Buys search timed out")
    except Exception as e:
        logger.error("search-canada-buys failed: %s", e, exc_info=True)
        return _error_response(500, "Canada Buys search failed")


@app.post("/api/search-alberta-purchasing", response_model=AlbertaPurchasingResponse)
@limiter.limit("5/minute")
async def search_alberta_purchasing_endpoint(
    request: Request,
    body: AlbertaPurchasingRequest,
    api_key: str = Depends(verify_api_key)
):
    """
    Search Alberta Purchasing Connection for opportunities.
    """
    try:
        # Resolve enrichContacts: explicit request param > config default
        enrich = body.enrichContacts
        if enrich is None:
            enrich = getattr(config, "APC_ENRICH_CONTACTS", False)

        timeout = 300 if enrich else 110

        async with browser_pool.get_context() as ctx:
            result = await asyncio.wait_for(
                search_apc(
                    keywords=body.keywords,
                    days_back=body.daysBack,
                    max_results=body.maxResults,
                    status_filter=body.statusFilter,
                    solicitation_type=body.solicitationType,
                    category=body.category,
                    enrich_contacts=enrich,
                    browser_context=ctx,
                ),
                timeout=timeout,
            )

        opportunities = [
            APCOpportunity(**o)
            for o in result.get("opportunities", [])
        ]

        return AlbertaPurchasingResponse(
            source=result.get("source", "alberta_purchasing"),
            totalOpportunities=result.get("totalOpportunities", 0),
            totalAvailable=result.get("totalAvailable", 0),
            opportunities=opportunities,
            scrapedAt=result.get("scrapedAt", ""),
        )

    except asyncio.TimeoutError:
        logger.error("search-alberta-purchasing timed out")
        return _error_response(504, "Alberta Purchasing search timed out")
    except RuntimeError as e:
        logger.error("search-alberta-purchasing unavailable: %s", e)
        return _error_response(503, "Alberta Purchasing scraper temporarily unavailable")
    except Exception as e:
        logger.error("search-alberta-purchasing failed: %s", e, exc_info=True)
        return _error_response(500, "Alberta Purchasing search failed")


# ============================================
# Email Automation Endpoints
# ============================================

@app.post("/api/classify-thread", response_model=ClassifyThreadResponse)
@limiter.limit("20/minute")
async def classify_thread_endpoint(
    request: Request,
    body: ClassifyThreadRequest,
    api_key: str = Depends(verify_api_key)
):
    """
    Classify an email conversation thread into a procurement stage.
    """
    try:
        thread_dicts = [
            {"from": msg.sender, "body": msg.body}
            for msg in body.thread
        ]
        stage = await classify_conversation_stage(thread_dicts)

        return ClassifyThreadResponse(stage=stage)

    except RuntimeError as e:
        logger.error("classify-thread unavailable: %s", e)
        return _error_response(503, "LLM service unavailable")
    except Exception as e:
        logger.error("classify-thread failed: %s", e, exc_info=True)
        return _error_response(500, "Classification failed")


@app.post("/api/draft-reply", response_model=DraftReplyResponse)
@limiter.limit("20/minute")
async def draft_reply_endpoint(
    request: Request,
    body: DraftReplyRequest,
    api_key: str = Depends(verify_api_key)
):
    """
    Draft a context-aware reply email for a procurement conversation.
    """
    try:
        thread_dicts = [
            {"from": msg.sender, "body": msg.body}
            for msg in body.thread
        ]

        # Auto-classify if stage not provided
        stage = body.stage
        if not stage:
            stage = await classify_conversation_stage(thread_dicts)

        reply = await draft_reply(thread_dicts, stage, body.context)

        return DraftReplyResponse(stage=stage, draft=reply)

    except RuntimeError as e:
        logger.error("draft-reply unavailable: %s", e)
        return _error_response(503, "LLM service unavailable")
    except Exception as e:
        logger.error("draft-reply failed: %s", e, exc_info=True)
        return _error_response(500, "Draft failed")


@app.post("/api/extract-quote", response_model=ExtractQuoteResponse)
@limiter.limit("20/minute")
async def extract_quote_endpoint(
    request: Request,
    body: ExtractQuoteRequest,
    api_key: str = Depends(verify_api_key)
):
    """
    Extract structured quote data from email or document text.
    """
    try:
        data = await extract_quote_data(body.text)
        return ExtractQuoteResponse(data=data)

    except RuntimeError as e:
        logger.error("extract-quote unavailable: %s", e)
        return _error_response(503, "LLM service unavailable")
    except Exception as e:
        logger.error("extract-quote failed: %s", e, exc_info=True)
        return _error_response(500, "Quote extraction failed")


# ============================================
# Normalize Endpoints
# ============================================

class NormalizeLeadsRequest(BaseModel):
    """Request body for scrape + normalize."""
    source: str = Field(..., description="Source: sam_gov, canada_buys, alberta_purchasing, dibbs")
    daysBack: int = Field(default=7, description="Number of days to look back")
    maxPages: int = Field(default=1, description="Max pages to scrape")
    keyword: Optional[str] = Field(default=None, description="Keyword filter (SAM.gov / Canada Buys)")


class NormalizeRawRequest(BaseModel):
    """Request body for normalizing pre-fetched data."""
    source: str = Field(..., description="Source: sam_gov, canada_buys, alberta_purchasing, dibbs")
    data: dict = Field(..., description="Raw scraper output to normalize")


class NormalizeLeadsResponse(BaseModel):
    """Response body for normalized leads."""
    totalLeads: int = 0
    leads: List[dict] = Field(default_factory=list)


@app.post("/api/normalize-leads", response_model=NormalizeLeadsResponse)
@limiter.limit("5/minute")
async def normalize_leads_endpoint(
    request: Request,
    body: NormalizeLeadsRequest,
    api_key: str = Depends(verify_api_key)
):
    """
    Scrape a source and return normalized UnifiedLead rows.
    """
    try:
        if body.source == "sam_gov":
            async with browser_pool.get_context() as ctx:
                raw = await search_opportunities(
                    days_back=body.daysBack,
                    max_pages=body.maxPages,
                    keyword=body.keyword,
                    browser_context=ctx,
                )
        elif body.source == "canada_buys":
            raw = await search_canada_tenders(
                keywords=body.keyword,
                days_back=body.daysBack,
                max_results=200,
            )
        elif body.source == "alberta_purchasing":
            async with browser_pool.get_context() as ctx:
                raw = await search_apc(
                    keywords=body.keyword or "",
                    days_back=body.daysBack,
                    max_results=100,
                    browser_context=ctx,
                )
        elif body.source == "dibbs":
            from datetime import date as dt_date
            today = dt_date.today().strftime("%m-%d-%Y")
            async with browser_pool.get_context() as ctx:
                raw = await scrape_nsns_by_date(date=today, max_pages=body.maxPages, browser_context=ctx)
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown source: {body.source}. Use: sam_gov, canada_buys, alberta_purchasing, dibbs"
            )

        leads = normalize_any(body.source, raw)
        return NormalizeLeadsResponse(totalLeads=len(leads), leads=leads)

    except HTTPException:
        raise
    except asyncio.TimeoutError:
        logger.error("normalize-leads timed out")
        return _error_response(504, "Normalize timed out")
    except RuntimeError as e:
        logger.error("normalize-leads unavailable: %s", e)
        return _error_response(503, "Scraper temporarily unavailable")
    except Exception as e:
        logger.error("normalize-leads failed: %s", e, exc_info=True)
        return _error_response(500, "Normalize failed")


@app.post("/api/normalize-raw", response_model=NormalizeLeadsResponse)
@limiter.limit("20/minute")
async def normalize_raw_endpoint(
    request: Request,
    body: NormalizeRawRequest,
    api_key: str = Depends(verify_api_key)
):
    """
    Normalize pre-fetched raw scraper data into UnifiedLead rows.
    """
    try:
        leads = normalize_any(body.source, body.data)
        return NormalizeLeadsResponse(totalLeads=len(leads), leads=leads)

    except ValueError as e:
        return _error_response(400, str(e))
    except Exception as e:
        logger.error("normalize-raw failed: %s", e, exc_info=True)
        return _error_response(500, "Normalize failed")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
