"""
Document Intelligence Service

PDF download, text extraction, and structured parsing for bid/solicitation documents.
Uses PyMuPDF for native PDF text and pytesseract + pdf2image for OCR on scanned PDFs.
"""

import io
import ipaddress
import re
import socket
from typing import Optional, Tuple
from urllib.parse import urlparse

import httpx
import fitz  # PyMuPDF

MAX_DOCUMENT_SIZE = 50 * 1024 * 1024  # 50 MB


def _validate_url(url: str) -> None:
    """Validate URL to prevent SSRF attacks."""
    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Unsupported URL scheme: {parsed.scheme}")

    hostname = parsed.hostname
    if not hostname:
        raise ValueError("URL has no hostname")

    # Resolve hostname and check for private/internal IPs
    try:
        for info in socket.getaddrinfo(hostname, None):
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                raise ValueError(f"URL resolves to private/internal address: {ip}")
    except socket.gaierror:
        raise ValueError(f"Cannot resolve hostname: {hostname}")


async def download_document(url: str, timeout: int = 30) -> bytes:
    """
    Download a document from a URL.

    Args:
        url: URL to download from
        timeout: Request timeout in seconds

    Returns:
        Raw bytes of the document

    Raises:
        ValueError: If URL is invalid or points to internal network
        httpx.HTTPStatusError: If download fails
    """
    _validate_url(url)

    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=timeout,
        max_redirects=5,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        },
    ) as client:
        response = await client.get(url)
        response.raise_for_status()

        if len(response.content) > MAX_DOCUMENT_SIZE:
            raise ValueError(f"Document exceeds {MAX_DOCUMENT_SIZE // (1024*1024)} MB limit")

        return response.content


def extract_text_from_pdf(pdf_bytes: bytes) -> Tuple[str, int]:
    """
    Extract text from a PDF. Uses PyMuPDF for native text extraction,
    falls back to OCR (pytesseract + pdf2image) for scanned/image-based PDFs.

    Args:
        pdf_bytes: Raw PDF file bytes

    Returns:
        Tuple of (extracted text, page count)
    """
    # Try PyMuPDF first (fast, works for native PDFs)
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page_count = len(doc)
    pages_text = []

    for page in doc:
        text = page.get_text()
        if text.strip():
            pages_text.append(text.strip())

    doc.close()

    # If we got meaningful text, return it
    combined = "\n\n".join(pages_text)
    if len(combined.strip()) > 50:
        return combined, page_count

    # Fall back to OCR for scanned PDFs
    return _ocr_pdf(pdf_bytes), page_count


def _ocr_pdf(pdf_bytes: bytes) -> str:
    """
    OCR fallback for scanned/image-based PDFs.
    Requires tesseract-ocr and poppler-utils system packages.
    """
    try:
        from pdf2image import convert_from_bytes
        import pytesseract
    except ImportError:
        return "[OCR dependencies not installed: pip install pytesseract pdf2image]"

    try:
        images = convert_from_bytes(pdf_bytes, dpi=300)
        pages_text = []
        for img in images:
            text = pytesseract.image_to_string(img)
            if text.strip():
                pages_text.append(text.strip())
        return "\n\n".join(pages_text) if pages_text else "[No text extracted via OCR]"
    except Exception as e:
        return f"[OCR failed: {e}]"


def parse_bid_package(text: str, extract_fields: Optional[list] = None) -> dict:
    """
    Parse structured information from bid/solicitation document text.

    Args:
        text: Raw extracted text from PDF
        extract_fields: Optional list of fields to extract. If None, extracts all.
                       Valid fields: eligibility, specs, quantity, delivery, deadlines

    Returns:
        Dict with extracted fields
    """
    all_fields = {"eligibility", "specs", "quantity", "delivery", "deadlines"}
    fields = set(extract_fields) if extract_fields else all_fields

    result = {}

    if "eligibility" in fields:
        result["eligibility"] = _extract_eligibility(text)

    if "specs" in fields:
        result["specs"] = _extract_specs(text)

    if "quantity" in fields:
        result["quantity"] = _extract_quantity(text)

    if "delivery" in fields:
        result["delivery"] = _extract_delivery(text)

    if "deadlines" in fields:
        result["deadlines"] = _extract_deadlines(text)

    return result


def _extract_eligibility(text: str) -> str:
    """Extract eligibility/qualification requirements."""
    patterns = [
        r"(?i)(?:eligib(?:le|ility)|qualif(?:y|ied|ication)|set[- ]aside|small business|8\(a\)|hubzone|sdvosb|wosb)[^\n]*(?:\n[^\n]+){0,5}",
        r"(?i)(?:offeror|bidder|contractor)\s+(?:must|shall|should)[^\n]*(?:\n[^\n]+){0,3}",
        r"(?i)(?:restriction|limited to|only eligible)[^\n]*(?:\n[^\n]+){0,3}",
    ]
    matches = []
    for pattern in patterns:
        for m in re.finditer(pattern, text):
            matches.append(m.group().strip())
    return "\n".join(matches) if matches else "Not specified"


def _extract_specs(text: str) -> str:
    """Extract technical specifications."""
    patterns = [
        r"(?i)(?:specification|spec\b|technical requirement|part number|nsn|nomenclature|material)[^\n]*(?:\n[^\n]+){0,5}",
        r"(?i)(?:mil[- ]?spec|mil[- ]?std|fed[- ]?spec|astm|ansi|iso)[^\n]*(?:\n[^\n]+){0,3}",
        r"(?i)(?:drawing|blueprint|revision|amendment)[^\n]*(?:\n[^\n]+){0,2}",
    ]
    matches = []
    for pattern in patterns:
        for m in re.finditer(pattern, text):
            matches.append(m.group().strip())
    return "\n".join(matches) if matches else "Not specified"


def _extract_quantity(text: str) -> str:
    """Extract quantity information."""
    patterns = [
        r"(?i)(?:quantit(?:y|ies)|qty)[^\n]*(?:\n[^\n]+){0,2}",
        r"(?i)(?:each|ea|lot|set|unit)\s*[:=]?\s*\d+[^\n]*",
        r"(?i)\b\d+\s+(?:each|ea|units?|pieces?|lots?|sets?)\b[^\n]*",
    ]
    matches = []
    for pattern in patterns:
        for m in re.finditer(pattern, text):
            matches.append(m.group().strip())
    return "\n".join(matches) if matches else "Not specified"


def _extract_delivery(text: str) -> str:
    """Extract delivery schedule and destination."""
    patterns = [
        r"(?i)(?:deliver(?:y|ed|ing)|ship(?:ping|ped|ment)|f\.?o\.?b\.?|destination)[^\n]*(?:\n[^\n]+){0,3}",
        r"(?i)(?:days?\s+(?:after|ard|arod|from))[^\n]*",
        r"(?i)(?:\d+\s+(?:calendar|business|working)\s+days?)[^\n]*",
    ]
    matches = []
    for pattern in patterns:
        for m in re.finditer(pattern, text):
            matches.append(m.group().strip())
    return "\n".join(matches) if matches else "Not specified"


def _extract_deadlines(text: str) -> str:
    """Extract deadline dates."""
    patterns = [
        r"(?i)(?:deadline|due date|closing date|return by|respond by|submit(?:ted)? by)[^\n]*(?:\n[^\n]+){0,2}",
        r"(?i)(?:no later than|nlt|on or before)[^\n]*",
        r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b[^\n]*",
    ]
    matches = []
    seen = set()
    for pattern in patterns:
        for m in re.finditer(pattern, text):
            line = m.group().strip()
            if line not in seen:
                seen.add(line)
                matches.append(line)
    return "\n".join(matches) if matches else "Not specified"
