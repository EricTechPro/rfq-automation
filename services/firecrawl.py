"""
Firecrawl Client

AI-powered web scraping for supplier contact discovery using Firecrawl API.
"""

import re
import time
import random
import requests
from datetime import datetime
from typing import Optional, Dict, Any, List
from urllib.parse import urlparse

import sys
sys.path.insert(0, str(__file__).rsplit("/", 2)[0])

from config import config
from models import SupplierContact, ContactPerson
from utils.logging import get_logger

logger = get_logger(__name__)


# Domains to filter out from search results
EXCLUDED_DOMAINS = [
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
]


def firecrawl_request(endpoint: str, body: Dict[str, Any], timeout_override: Optional[float] = None, max_retries: int = 3) -> Dict[str, Any]:
    """
    Make a request to the Firecrawl API with retry and exponential backoff.

    Args:
        endpoint: API endpoint (e.g., "/search", "/scrape")
        body: Request body
        timeout_override: Override timeout in seconds (None = use config default)
        max_retries: Maximum number of attempts (default 3)

    Returns:
        API response as dict
    """
    url = f"{config.FIRECRAWL_API_URL}{endpoint}"

    headers = {
        "Authorization": f"Bearer {config.FIRECRAWL_API_KEY}",
        "Content-Type": "application/json",
    }

    timeout = timeout_override if timeout_override is not None else (config.FIRECRAWL_TIMEOUT / 1000)

    if max_retries < 1:
        max_retries = 1

    for attempt in range(max_retries):
        try:
            response = requests.post(
                url,
                json=body,
                headers=headers,
                timeout=timeout
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else 0
            if status in (400, 401, 403, 404):
                raise  # Don't retry permanent errors
            if attempt == max_retries - 1:
                raise
            delay = (2 ** attempt) + random.uniform(0, 1)
            logger.warning("Firecrawl %s attempt %d/%d failed (HTTP %s), retrying in %.1fs",
                          endpoint, attempt + 1, max_retries, status, delay)
            time.sleep(delay)
        except requests.exceptions.Timeout:
            if attempt == max_retries - 1:
                raise
            delay = (2 ** attempt) + random.uniform(0, 1)
            logger.warning("Firecrawl %s timeout, retrying in %.1fs (attempt %d/%d)",
                          endpoint, delay, attempt + 1, max_retries)
            time.sleep(delay)
        except requests.exceptions.ConnectionError:
            if attempt == max_retries - 1:
                raise
            delay = (2 ** attempt) + random.uniform(0, 1)
            logger.warning("Firecrawl %s connection error, retrying in %.1fs (attempt %d/%d)",
                          endpoint, delay, attempt + 1, max_retries)
            time.sleep(delay)


def calculate_confidence(has_email: bool, has_phone: bool, has_address: bool, has_website: bool) -> str:
    """
    Calculate contact confidence level.

    HIGH = email + phone + address + website (all 4)
    MEDIUM = at least phone number
    LOW = website only or nothing
    """
    if has_email and has_phone and has_address and has_website:
        return "high"
    elif has_phone:
        return "medium"
    else:
        return "low"


def is_excluded_domain(url: str) -> bool:
    """Check if URL is from an excluded domain."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        return any(domain == excluded or domain.endswith("." + excluded) for excluded in EXCLUDED_DOMAINS)
    except Exception:
        return True  # Treat unparseable URLs as excluded


def search_supplier_website(
    company_name: str,
    cage_code: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Search for a supplier's website using Firecrawl Search API.

    Uses cascading search strategies:
    1. "{company_name} contact"
    2. "{company_name} {cage_code}" (or just "{company_name}" if no cage code)

    Returns dict with url, title, description or None if not found.
    """
    if not config.is_firecrawl_configured():
        return None

    logger.info("Searching for supplier website: %s (CAGE: %s)", company_name, cage_code or "N/A")

    search_queries = [f"{company_name} contact"]
    if cage_code:
        search_queries.append(f"{company_name} {cage_code}")
    else:
        search_queries.append(company_name)

    for query in search_queries:
        try:
            response = firecrawl_request("/search", {
                "query": query,
                "limit": 5,
                "sources": ["web"]
            }, timeout_override=30)

            if response.get("success") and response.get("data", {}).get("web"):
                results = response["data"]["web"]

                # Filter out excluded domains
                valid_results = [
                    r for r in results
                    if not is_excluded_domain(r.get("url", ""))
                ]

                if valid_results:
                    # Prefer results that mention the company name
                    company_lower = company_name.lower()
                    for result in valid_results:
                        title = result.get("title", "").lower()
                        url = result.get("url", "").lower()
                        if company_lower in title or company_lower in url:
                            return result

                    # Return first valid result as fallback
                    return valid_results[0]

        except Exception as e:
            logger.warning("Firecrawl search failed for query '%s': %s", query, e)
            continue

    return None


def extract_contact_info(
    website_url: str,
    company_name: str
) -> SupplierContact:
    """
    Extract contact information from a website using Firecrawl Scrape API.

    Tries main URL first, then /contact page.

    Returns SupplierContact with discovered info.
    """
    timestamp = datetime.utcnow().isoformat() + "Z"

    # Default empty contact
    empty_contact = SupplierContact(
        companyName=company_name,
        email=None,
        phone=None,
        address=None,
        website=website_url,
        contactPage=None,
        additionalContacts=[],
        source="firecrawl_scrape",
        confidence="low",
        scrapedAt=timestamp
    )

    if not config.is_firecrawl_configured():
        return empty_contact

    logger.info("Extracting contact info from %s for %s", website_url, company_name)

    # URLs to try
    urls_to_try = [website_url]

    # Add /contact page if not already a contact page
    if not any(x in website_url.lower() for x in ["/contact", "/about", "/reach"]):
        parsed = urlparse(website_url)
        contact_url = f"{parsed.scheme}://{parsed.netloc}/contact"
        urls_to_try.append(contact_url)

    # JSON extraction schema
    extraction_schema = {
        "type": "object",
        "properties": {
            "emails": {
                "type": "array",
                "items": {"type": "string"},
                "description": "All email addresses found on the page"
            },
            "phones": {
                "type": "array",
                "items": {"type": "string"},
                "description": "All phone numbers found on the page"
            },
            "address": {
                "type": "string",
                "description": "Physical/mailing address of the company"
            },
            "contactPersons": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "title": {"type": "string"},
                        "email": {"type": "string"},
                        "phone": {"type": "string"}
                    }
                },
                "description": "Individual contact persons found"
            }
        }
    }

    best_result = None
    best_confidence = "low"
    contact_page_url = None

    for url in urls_to_try:
        try:
            response = firecrawl_request("/scrape", {
                "url": url,
                "formats": [
                    "markdown",
                    {
                        "type": "json",
                        "prompt": "Extract all contact information including email addresses, phone numbers, physical address, and contact persons with their names, titles, emails and phone numbers.",
                        "schema": extraction_schema
                    }
                ],
                "timeout": config.FIRECRAWL_TIMEOUT
            })

            if response.get("success"):
                data = response.get("data", {})
                json_data = data.get("json", {})

                emails = json_data.get("emails", [])
                phones = json_data.get("phones", [])
                address = json_data.get("address")
                contact_persons = json_data.get("contactPersons", [])

                # Determine confidence
                has_email = bool(emails)
                has_phone = bool(phones)
                has_address = bool(address)
                has_website = bool(website_url)

                confidence = calculate_confidence(has_email, has_phone, has_address, has_website)

                # Track best result
                confidence_order = {"high": 3, "medium": 2, "low": 1}
                if confidence_order.get(confidence, 0) > confidence_order.get(best_confidence, 0):
                    best_confidence = confidence
                    contact_page_url = url if "/contact" in url else None

                    # Build contact persons list
                    additional_contacts = []
                    for person in contact_persons:
                        additional_contacts.append(ContactPerson(
                            name=person.get("name"),
                            title=person.get("title"),
                            email=person.get("email"),
                            phone=person.get("phone")
                        ))

                    best_result = {
                        "email": emails[0] if emails else None,
                        "phone": phones[0] if phones else None,
                        "address": address,
                        "additional_contacts": additional_contacts,
                        "confidence": confidence
                    }

                    # If we got high confidence, stop searching
                    if confidence == "high":
                        break

        except Exception as e:
            logger.warning("Firecrawl scrape failed for %s: %s", url, e)
            continue

    if best_result:
        return SupplierContact(
            companyName=company_name,
            email=best_result["email"],
            phone=best_result["phone"],
            address=best_result["address"],
            website=website_url,
            contactPage=contact_page_url,
            additionalContacts=best_result["additional_contacts"],
            source="firecrawl_scrape",
            confidence=best_result["confidence"],
            scrapedAt=timestamp
        )

    return empty_contact


def find_supplier_contact(
    company_name: str,
    cage_code: Optional[str] = None,
    known_website: Optional[str] = None
) -> SupplierContact:
    """
    Find contact information for a supplier.

    Combined workflow:
    1. Search for website (if not provided)
    2. Extract contact info from website

    Args:
        company_name: Name of the supplier
        cage_code: Optional CAGE code for search refinement
        known_website: Optional known website URL (skips search)

    Returns:
        SupplierContact with all discovered information
    """
    timestamp = datetime.utcnow().isoformat() + "Z"

    # If website is known, skip search
    if known_website:
        return extract_contact_info(known_website, company_name)

    # Search for website
    search_result = search_supplier_website(company_name, cage_code)

    if search_result:
        website_url = search_result.get("url")
        if website_url:
            return extract_contact_info(website_url, company_name)

    # No website found
    return SupplierContact(
        companyName=company_name,
        email=None,
        phone=None,
        address=None,
        website=None,
        contactPage=None,
        additionalContacts=[],
        source="firecrawl_search",
        confidence="low",
        scrapedAt=timestamp
    )
