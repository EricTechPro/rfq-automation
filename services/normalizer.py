"""
Lead Normalizer

Converts raw scraper output from all 4 sources into the unified UnifiedLead schema.
"""

import re
from datetime import date, datetime
from typing import List, Optional


def _today() -> str:
    return date.today().isoformat()


def _to_yyyy_mm_dd(raw: str) -> str:
    """Convert various date formats to YYYY-MM-DD. Returns '' on failure."""
    if not raw:
        return ""
    raw = raw.strip()

    # Already YYYY-MM-DD
    if re.match(r"^\d{4}-\d{2}-\d{2}$", raw):
        return raw

    # MM-DD-YYYY (DIBBS format)
    m = re.match(r"^(\d{2})-(\d{2})-(\d{4})$", raw)
    if m:
        return f"{m.group(3)}-{m.group(1)}-{m.group(2)}"

    # ISO 8601 with time (SAM.gov: 2026-02-10T00:21:30+00:00)
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S"):
        try:
            dt = datetime.strptime(raw[:19], "%Y-%m-%dT%H:%M:%S")
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            pass

    # Fallback: take first 10 chars if they look like a date
    if len(raw) >= 10 and re.match(r"^\d{4}-\d{2}-\d{2}", raw):
        return raw[:10]

    return raw


def _strip_html(text: str) -> str:
    """Remove HTML tags from a string."""
    if not text:
        return ""
    return re.sub(r"<[^>]+>", "", text).strip()


def _s(val) -> str:
    """Coerce to string, None -> ''."""
    if val is None:
        return ""
    return str(val).strip()


def normalize_sam_opportunities(raw: dict) -> List[dict]:
    """Normalize SAM.gov search results into UnifiedLead rows."""
    leads = []
    for opp in raw.get("opportunities", []):
        # Flatten first point of contact
        contacts = opp.get("pointOfContact", [])
        poc = contacts[0] if contacts else {}

        leads.append({
            "source": "sam_gov",
            "title": _s(opp.get("title")),
            "solicitationNumber": _s(opp.get("solicitationNumber")),
            "description": _strip_html(_s(opp.get("description"))),
            "postedDate": _to_yyyy_mm_dd(_s(opp.get("postedDate"))),
            "closingDate": _to_yyyy_mm_dd(_s(opp.get("responseDeadline"))),
            "sourceUrl": _s(opp.get("sourceUrl")),
            "organization": _s(opp.get("department") or opp.get("agency")),
            "status": _s(opp.get("noticeType")),
            "category": _s(opp.get("naicsCode")),
            "nsn": "",
            "quantity": 0,
            "contactName": _s(poc.get("name")),
            "contactEmail": _s(poc.get("email")),
            "contactPhone": _s(poc.get("phone")),
            "supplierName": "",
            "supplierEmail": "",
            "supplierPhone": "",
            "supplierWebsite": "",
            "cageCode": "",
            "confidence": "",
            "emailStatus": "New",
            "emailDraft": "",
            "documentUrl": "",
            "dateAdded": _today(),
            "notes": "",
        })
    return leads


def normalize_canada_buys_tenders(raw: dict) -> List[dict]:
    """Normalize Canada Buys tenders into UnifiedLead rows."""
    leads = []
    for t in raw.get("tenders", []):
        leads.append({
            "source": "canada_buys",
            "title": _s(t.get("title")),
            "solicitationNumber": _s(t.get("solicitationNumber")),
            "description": _s(t.get("description")),
            "postedDate": _to_yyyy_mm_dd(_s(t.get("publishedDate"))),
            "closingDate": _to_yyyy_mm_dd(_s(t.get("closingDate"))),
            "sourceUrl": _s(t.get("sourceUrl")),
            "organization": _s(t.get("organization")),
            "status": _s(t.get("status")),
            "category": _s(t.get("category")),
            "nsn": "",
            "quantity": 0,
            "contactName": _s(t.get("contactName")),
            "contactEmail": _s(t.get("contactEmail")),
            "contactPhone": "",
            "supplierName": "",
            "supplierEmail": "",
            "supplierPhone": "",
            "supplierWebsite": "",
            "cageCode": "",
            "confidence": "",
            "emailStatus": "New",
            "emailDraft": "",
            "documentUrl": "",
            "dateAdded": _today(),
            "notes": "",
        })
    return leads


def normalize_alberta_opportunities(raw: dict) -> List[dict]:
    """Normalize Alberta Purchasing Connection opportunities into UnifiedLead rows."""
    leads = []
    for o in raw.get("opportunities", []):
        leads.append({
            "source": "alberta_purchasing",
            "title": _s(o.get("title")),
            "solicitationNumber": _s(o.get("solicitationNumber")),
            "description": _s(o.get("description")),
            "postedDate": _to_yyyy_mm_dd(_s(o.get("publishedDate"))),
            "closingDate": _to_yyyy_mm_dd(_s(o.get("closingDate"))),
            "sourceUrl": _s(o.get("sourceUrl")),
            "organization": _s(o.get("organization")),
            "status": _s(o.get("status")),
            "category": _s(o.get("categoryCode")),
            "nsn": "",
            "quantity": 0,
            "contactName": _s(o.get("contactName")),
            "contactEmail": _s(o.get("contactEmail")),
            "contactPhone": _s(o.get("contactPhone")),
            "supplierName": "",
            "supplierEmail": "",
            "supplierPhone": "",
            "supplierWebsite": "",
            "cageCode": "",
            "confidence": "",
            "emailStatus": "New",
            "emailDraft": "",
            "documentUrl": "",
            "dateAdded": _today(),
            "notes": "",
        })
    return leads


def normalize_dibbs_nsns(raw: dict, suppliers: Optional[List[dict]] = None) -> List[dict]:
    """Normalize DIBBS NSN date-scrape results into UnifiedLead rows."""
    leads = []
    for nsn_item in raw.get("nsns", []):
        leads.append({
            "source": "dibbs",
            "title": _s(nsn_item.get("nomenclature")),
            "solicitationNumber": _s(nsn_item.get("solicitation")),
            "description": "",
            "postedDate": _to_yyyy_mm_dd(_s(nsn_item.get("issueDate"))),
            "closingDate": _to_yyyy_mm_dd(_s(nsn_item.get("returnByDate"))),
            "sourceUrl": "",
            "organization": "Defense Logistics Agency",
            "status": "Open",
            "category": "",
            "nsn": _s(nsn_item.get("nsn")),
            "quantity": nsn_item.get("quantity", 0) or 0,
            "contactName": "",
            "contactEmail": "",
            "contactPhone": "",
            "supplierName": "",
            "supplierEmail": "",
            "supplierPhone": "",
            "supplierWebsite": "",
            "cageCode": "",
            "confidence": "",
            "emailStatus": "New",
            "emailDraft": "",
            "documentUrl": "",
            "dateAdded": _today(),
            "notes": "",
        })
    return leads


_NORMALIZERS = {
    "sam_gov": normalize_sam_opportunities,
    "canada_buys": normalize_canada_buys_tenders,
    "alberta_purchasing": normalize_alberta_opportunities,
    "dibbs": normalize_dibbs_nsns,
}


def normalize_any(source: str, raw: dict) -> List[dict]:
    """Route to the correct normalizer by source name."""
    fn = _NORMALIZERS.get(source)
    if not fn:
        raise ValueError(f"Unknown source: {source}. Expected one of: {list(_NORMALIZERS.keys())}")
    return fn(raw)
