"""
Pydantic Data Models

Type definitions for RFQ data structures matching the TypeScript interfaces.
"""

from datetime import datetime
from typing import Optional, List, Literal
from pydantic import BaseModel, Field


# ============== DIBBS Types ==============

class ApprovedSource(BaseModel):
    """Approved source/supplier from DIBBS"""
    cage_code: str = Field(alias="cageCode")
    part_number: str = Field(alias="partNumber")
    company_name: str = Field(alias="companyName")

    class Config:
        populate_by_name = True


class Solicitation(BaseModel):
    """RFQ solicitation from DIBBS"""
    solicitation_number: str = Field(alias="solicitationNumber")
    solicitation_url: Optional[str] = Field(None, alias="solicitationUrl")
    technical_documents: str = Field("None", alias="technicalDocuments")
    document_urls: List[str] = Field(default_factory=list, alias="documentUrls")
    status: str = Field("", alias="status")  # RFQ/Quote Status: Open, Removed, Cancelled
    pr_number: str = Field(alias="prNumber")
    quantity: int
    issue_date: str = Field(alias="issueDate")
    return_by_date: str = Field(alias="returnByDate")

    class Config:
        populate_by_name = True


class RFQData(BaseModel):
    """Complete DIBBS RFQ data"""
    nsn: str
    nomenclature: str
    amsc: str = ""
    approved_sources: List[ApprovedSource] = Field(default_factory=list, alias="approvedSources")
    solicitations: List[Solicitation] = Field(default_factory=list)
    has_open_rfqs: bool = Field(False, alias="hasOpenRFQs")
    scraped_at: str = Field(alias="scrapedAt")
    source_url: str = Field(alias="sourceUrl")

    class Config:
        populate_by_name = True


class ScrapeResult(BaseModel):
    """Result wrapper for DIBBS scraping"""
    success: bool
    data: Optional[RFQData] = None
    error: Optional[str] = None


# ============== WBParts Types ==============

class WBPartsManufacturer(BaseModel):
    """Manufacturer from WBParts"""
    part_number: str = Field(alias="partNumber")
    cage_code: str = Field(alias="cageCode")
    company_name: str = Field(alias="companyName")

    class Config:
        populate_by_name = True


class WBPartsTechSpec(BaseModel):
    """Technical specification from WBParts"""
    name: str
    value: str


class WBPartsDemand(BaseModel):
    """Demand history entry from WBParts"""
    part_number: str = Field(alias="partNumber")
    request_date: str = Field(alias="requestDate")
    quantity: int
    origin: str


class WBPartsData(BaseModel):
    """Complete WBParts data"""
    nsn: str
    item_name: str = Field("", alias="itemName")
    inc_code: str = Field("", alias="incCode")
    part_alternates: List[str] = Field(default_factory=list, alias="partAlternates")
    manufacturers: List[WBPartsManufacturer] = Field(default_factory=list)
    tech_specs: List[WBPartsTechSpec] = Field(default_factory=list, alias="techSpecs")
    demand_history: List[WBPartsDemand] = Field(default_factory=list, alias="demandHistory")
    assignment_date: str = Field("", alias="assignmentDate")
    source_url: str = Field(alias="sourceUrl")
    scraped_at: str = Field(alias="scrapedAt")

    class Config:
        populate_by_name = True


class WBPartsScrapeResult(BaseModel):
    """Result wrapper for WBParts scraping"""
    success: bool
    data: Optional[WBPartsData] = None
    error: Optional[str] = None


# ============== Contact Types ==============

class ContactPerson(BaseModel):
    """Individual contact person"""
    name: Optional[str] = None
    title: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None


class SupplierContact(BaseModel):
    """Supplier contact information"""
    company_name: str = Field(alias="companyName")
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    website: Optional[str] = None
    contact_page: Optional[str] = Field(None, alias="contactPage")
    additional_contacts: List[ContactPerson] = Field(default_factory=list, alias="additionalContacts")
    source: Literal["firecrawl_search", "firecrawl_scrape", "manual"] = "firecrawl_scrape"
    confidence: Literal["high", "medium", "low"] = "low"
    scraped_at: str = Field(alias="scrapedAt")

    class Config:
        populate_by_name = True


class SupplierWithContact(BaseModel):
    """Supplier with optional contact info"""
    company_name: str = Field(alias="companyName")
    cage_code: str = Field(alias="cageCode")
    part_number: str = Field(alias="partNumber")
    contact: Optional[SupplierContact] = None

    class Config:
        populate_by_name = True


# ============== Enhanced Result ==============

class RawData(BaseModel):
    """Raw data from both sources"""
    dibbs: Optional[RFQData] = None
    wbparts: Optional[WBPartsData] = None


class WorkflowStatus(BaseModel):
    """Workflow status for each step"""
    dibbs_status: Literal["success", "error", "skipped"] = Field("skipped", alias="dibbsStatus")
    wbparts_status: Literal["success", "error", "skipped"] = Field("skipped", alias="wbpartsStatus")
    firecrawl_status: Literal["success", "error", "skipped", "partial", "partial_timeout"] = Field("skipped", alias="firecrawlStatus")

    class Config:
        populate_by_name = True


class EnhancedRFQResult(BaseModel):
    """Complete enhanced RFQ result with all data"""
    nsn: str
    item_name: str = Field("", alias="itemName")
    has_open_rfq: bool = Field(False, alias="hasOpenRFQ")
    suppliers: List[SupplierWithContact] = Field(default_factory=list)
    raw_data: RawData = Field(default_factory=RawData, alias="rawData")
    workflow: WorkflowStatus = Field(default_factory=WorkflowStatus)
    scraped_at: str = Field(alias="scrapedAt")

    class Config:
        populate_by_name = True

    def model_dump_json_compatible(self) -> dict:
        """Export with camelCase keys for JSON compatibility"""
        return self.model_dump(by_alias=True, exclude_none=True)


# ============== Batch Processing Types ==============

class BatchNSNResult(BaseModel):
    """Individual NSN result within a batch"""
    nsn: str
    status: Literal["pending", "processing", "success", "error"]
    result: Optional[EnhancedRFQResult] = None
    error_message: Optional[str] = Field(None, alias="errorMessage")
    processed_at: Optional[str] = Field(None, alias="processedAt")

    class Config:
        populate_by_name = True


class BatchProcessingResult(BaseModel):
    """Complete batch processing result"""
    total_nsns: int = Field(alias="totalNsns")
    processed: int = 0
    successful: int = 0
    failed: int = 0
    results: List[BatchNSNResult] = Field(default_factory=list)
    started_at: str = Field(alias="startedAt")
    completed_at: Optional[str] = Field(None, alias="completedAt")

    class Config:
        populate_by_name = True


# ============== Unified Lead Schema ==============

class UnifiedLead(BaseModel):
    """Flat 25-column lead schema for Google Sheets — 1 row = 1 lead."""
    source: str = ""                    # "dibbs", "sam_gov", "canada_buys", "alberta_purchasing"
    title: str = ""
    solicitationNumber: str = ""
    description: str = ""
    postedDate: str = ""                # YYYY-MM-DD
    closingDate: str = ""               # YYYY-MM-DD
    sourceUrl: str = ""
    organization: str = ""
    status: str = ""
    category: str = ""
    nsn: str = ""                       # DIBBS only
    quantity: int = 0                   # DIBBS only
    contactName: str = ""               # Buyer POC
    contactEmail: str = ""
    contactPhone: str = ""
    supplierName: str = ""              # From Firecrawl
    supplierEmail: str = ""
    supplierPhone: str = ""
    supplierWebsite: str = ""
    cageCode: str = ""
    confidence: str = ""
    emailStatus: str = "New"            # Pipeline stage
    emailDraft: str = ""
    documentUrl: str = ""
    dateAdded: str = ""
    notes: str = ""


# ============== SAM.gov Types ==============

class SAMPointOfContact(BaseModel):
    """Point of contact from SAM.gov opportunity"""
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    type: Optional[str] = None  # "primary" or "secondary"

    class Config:
        populate_by_name = True


class SAMOpportunity(BaseModel):
    """Individual opportunity from SAM.gov"""
    title: str = ""
    solicitation_number: Optional[str] = Field(None, alias="solicitationNumber")
    notice_id: Optional[str] = Field(None, alias="noticeId")
    department: Optional[str] = None
    agency: Optional[str] = None
    posted_date: Optional[str] = Field(None, alias="postedDate")
    response_deadline: Optional[str] = Field(None, alias="responseDeadline")
    set_aside: Optional[str] = Field(None, alias="setAside")
    naics_code: Optional[str] = Field(None, alias="naicsCode")
    classification_code: Optional[str] = Field(None, alias="classificationCode")
    description: Optional[str] = None
    place_of_performance: Optional[str] = Field(None, alias="placeOfPerformance")
    point_of_contact: List[SAMPointOfContact] = Field(default_factory=list, alias="pointOfContact")
    attachment_links: List[str] = Field(default_factory=list, alias="attachmentLinks")
    source_url: str = Field("", alias="sourceUrl")
    notice_type: Optional[str] = Field(None, alias="noticeType")

    class Config:
        populate_by_name = True


class SAMSearchResult(BaseModel):
    """Result wrapper for SAM.gov search"""
    source: str = "sam_gov"
    total_pages: int = Field(0, alias="totalPages")
    pages_scraped: int = Field(0, alias="pagesScraped")
    total_opportunities: int = Field(0, alias="totalOpportunities")
    opportunities: List[SAMOpportunity] = Field(default_factory=list)
    scraped_at: str = Field(alias="scrapedAt")

    class Config:
        populate_by_name = True
