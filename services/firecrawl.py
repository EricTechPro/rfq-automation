"""
Firecrawl Client

AI-powered web scraping for supplier contact discovery using Firecrawl API.
"""

import re
import requests
from datetime import datetime
from typing import Optional, Dict, Any, List
from urllib.parse import urlparse

import sys
sys.path.insert(0, str(__file__).rsplit("/", 2)[0])

from config import config
from models import SupplierContact, ContactPerson


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


def firecrawl_request(endpoint: str, body: Dict[str, Any]) -> Dict[str, Any]:
    """
    Make a request to the Firecrawl API.

    Args:
        endpoint: API endpoint (e.g., "/search", "/scrape")
        body: Request body

    Returns:
        API response as dict
    """
    url = f"{config.FIRECRAWL_API_URL}{endpoint}"

    headers = {
        "Authorization": f"Bearer {config.FIRECRAWL_API_KEY}",
        "Content-Type": "application/json",
    }

    response = requests.post(
        url,
        json=body,
        headers=headers,
        timeout=config.FIRECRAWL_TIMEOUT / 1000  # Convert ms to seconds
    )

    response.raise_for_status()
    return response.json()


def is_excluded_domain(url: str) -> bool:
    """Check if URL is from an excluded domain"""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        return any(excluded in domain for excluded in EXCLUDED_DOMAINS)
    except Exception:
        return False


def search_supplier_website(
    company_name: str,
    cage_code: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Search for a supplier's website using Firecrawl Search API.

    Uses cascading search strategies:
    1. "{company_name} contact"
    2. "{company_name} {cage_code}"
    3. "{company_name}"

    Returns dict with url, title, description or None if not found.
    """
    if not config.is_firecrawl_configured():
        return None

    search_queries = [
        f"{company_name} contact",
    ]

    if cage_code:
        search_queries.append(f"{company_name} {cage_code}")

    search_queries.append(company_name)

    for query in search_queries:
        try:
            response = firecrawl_request("/search", {
                "query": query,
                "limit": 5,
                "sources": ["web"]
            })

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

        except Exception:
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

                if has_email and has_phone and has_address:
                    confidence = "high"
                elif has_email or has_phone:
                    confidence = "medium"
                else:
                    confidence = "low"

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

        except Exception:
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
