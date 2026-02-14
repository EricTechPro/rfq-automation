"""
Live integration tests against Railway deployment.

Run with:
    RFQ_TEST_API_KEY="some-random-secret-string" pytest tests/test_api_live.py -v

Requires: Live Railway deployment at RFQ_TEST_BASE_URL

These tests replicate the exact payloads sent by the n8n daily workflows
so we can verify production scraping works end-to-end.
"""

import re
from datetime import datetime

import pytest
import requests

from tests.conftest import API_BASE_URL, API_KEY, KNOWN_NSN


def _get(path, headers=None):
    return requests.get(f"{API_BASE_URL}{path}", headers=headers or {}, timeout=30)


def _post(path, json, headers=None):
    h = {"X-API-Key": API_KEY}
    if headers is not None:
        h.update(headers)
    return requests.post(f"{API_BASE_URL}{path}", json=json, headers=h, timeout=300)


# ── Health check ────────────────────────────────────────────────────

class TestHealthCheck:
    def test_health_returns_200(self):
        """Railway deployment is running and returns health status."""
        resp = _get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("healthy", "degraded", "unhealthy")

    def test_health_has_checks(self):
        """Health response includes service checks."""
        data = _get("/health").json()
        assert "checks" in data
        checks = data["checks"]
        assert "llm" in checks
        assert "firecrawl" in checks
        assert "playwright" in checks

    def test_health_services_configured(self):
        """Firecrawl and LLM services are configured in production."""
        checks = _get("/health").json()["checks"]
        assert checks["firecrawl"]["configured"] is True
        assert checks["llm"]["configured"] is True
        assert checks["llm"]["provider"] == "openrouter"

    def test_root_returns_health(self):
        """Root path returns same health response."""
        resp = _get("/")
        assert resp.status_code == 200
        assert resp.json()["status"] in ("healthy", "degraded", "unhealthy")


# ── Authentication ──────────────────────────────────────────────────

class TestAuthentication:
    def test_auth_required(self):
        """Endpoints reject requests without API key."""
        resp = requests.post(
            f"{API_BASE_URL}/api/scrape-nsn-suppliers",
            json={"nsn": KNOWN_NSN},
            timeout=30,
        )
        assert resp.status_code == 401

    def test_auth_invalid(self):
        """Endpoints reject invalid API keys."""
        resp = requests.post(
            f"{API_BASE_URL}/api/scrape-nsn-suppliers",
            json={"nsn": KNOWN_NSN},
            headers={"X-API-Key": "wrong-key"},
            timeout=30,
        )
        assert resp.status_code == 401


# ── NSN Supplier Scraping ──────────────────────────────────────────

class TestScrapeNSNSuppliers:
    @pytest.mark.slow
    def test_scrape_nsn_suppliers_n8n_payload(self):
        """NSN supplier scraping with n8n daily workflow payload."""
        # n8n/workflow-dibbs-daily.json sends just {"nsn": "..."}
        # Using maxSuppliers=2 to keep test fast
        resp = _post("/api/scrape-nsn-suppliers", {
            "nsn": KNOWN_NSN,
            "maxSuppliers": 2,
        })

        # DIBBS is a government site that goes down frequently.
        # Accept 200 (success) or 500/504 (DIBBS unavailable).
        if resp.status_code in (500, 504):
            pytest.skip(f"DIBBS unavailable (HTTP {resp.status_code})")

        assert resp.status_code == 200
        data = resp.json()

        # Verify structure
        assert "nsn" in data
        assert "nomenclature" in data
        assert "hasOpenRfq" in data
        assert "suppliers" in data
        assert isinstance(data["suppliers"], list)

        # Verify NSN format (13 digits with dashes)
        nsn = data["nsn"]
        assert len(nsn.replace("-", "")) == 13

        # Verify suppliers have expected fields
        for supplier in data["suppliers"]:
            assert "companyName" in supplier
            assert "cageCode" in supplier
            assert "confidence" in supplier
            assert supplier["confidence"] in ("high", "medium")
            # CAGE codes are 5 alphanumeric chars
            assert len(supplier["cageCode"]) == 5


# ── SAM.gov Search ──────────────────────────────────────────────────

class TestSearchSAM:
    @pytest.mark.slow
    def test_search_sam_n8n_payload(self):
        """SAM.gov search with exact n8n daily workflow payload."""
        # Exact payload from n8n/workflow-sam-daily.json
        resp = _post("/api/search-sam", {
            "daysBack": 1,
            "maxPages": 1,
            "enrichContacts": True,
        })
        assert resp.status_code == 200
        data = resp.json()

        assert "opportunities" in data
        assert "totalOpportunities" in data
        assert data["source"] == "sam_gov"
        assert "scrapedAt" in data

        if data["opportunities"]:
            opp = data["opportunities"][0]
            assert "title" in opp
            assert "sourceUrl" in opp


# ── Canada Buys Search ──────────────────────────────────────────────

class TestSearchCanadaBuys:
    @pytest.mark.slow
    def test_search_canada_buys_n8n_payload(self):
        """Canada Buys search with exact n8n daily workflow payload."""
        # Exact payload from n8n/workflow-canada-buys-daily.json
        resp = _post("/api/search-canada-buys", {
            "daysBack": 1,
            "maxResults": 200,
        })
        assert resp.status_code == 200
        data = resp.json()

        assert "tenders" in data
        assert data["source"].startswith("canada_buys")
        assert "scrapedAt" in data

        if data["tenders"]:
            tender = data["tenders"][0]
            assert "title" in tender
            assert "solicitationNumber" in tender


# ── Alberta Purchasing Search ───────────────────────────────────────

class TestSearchAlbertaPurchasing:
    @pytest.mark.slow
    def test_search_alberta_n8n_payload(self):
        """Alberta Purchasing search with exact n8n daily workflow payload."""
        # Exact payload from n8n/workflow-alberta-daily.json
        resp = _post("/api/search-alberta-purchasing", {
            "daysBack": 1,
            "maxResults": 100,
        })

        # Alberta Purchasing scraper can timeout or be unavailable
        if resp.status_code in (503, 504):
            pytest.skip(f"Alberta Purchasing unavailable (HTTP {resp.status_code})")

        assert resp.status_code == 200
        data = resp.json()

        assert "opportunities" in data
        assert data["source"] == "alberta_purchasing"
        assert "scrapedAt" in data

        if data["opportunities"]:
            opp = data["opportunities"][0]
            assert "title" in opp
            assert "referenceNumber" in opp


# ── DIBBS Date Scraping ─────────────────────────────────────────────

class TestScrapeDIBBSByDate:
    @pytest.mark.slow
    def test_scrape_nsns_by_date_n8n_payload(self):
        """DIBBS date scraping with n8n daily workflow payload."""
        # n8n sends today's date as MM-dd-yyyy
        today = datetime.utcnow().strftime("%m-%d-%Y")
        resp = _post("/api/scrape-nsns-by-date", {
            "date": today,
            "maxPages": 1,  # n8n uses 5, but use 1 for faster tests
        })

        # DIBBS goes down frequently
        if resp.status_code in (500, 503, 504):
            pytest.skip(f"DIBBS unavailable (HTTP {resp.status_code})")

        assert resp.status_code == 200
        data = resp.json()

        assert "nsns" in data
        assert "totalNsns" in data
        assert "date" in data
        assert "scrapedAt" in data
        assert isinstance(data["nsns"], list)

        if data["nsns"]:
            nsn_item = data["nsns"][0]
            assert "nsn" in nsn_item
            assert "nomenclature" in nsn_item
            assert "solicitation" in nsn_item
            # NSN should be 13 digits (with or without dashes)
            assert len(nsn_item["nsn"].replace("-", "")) == 13


# ── LLM Endpoints ──────────────────────────────────────────────────

class TestClassifyThread:
    def test_classify_thread(self):
        """Email classification returns a valid stage."""
        resp = _post("/api/classify-thread", {
            "thread": [
                {"from": "us", "body": "Hello, we are looking for a quote on NSN 5306-00-373-3291, qty 100."},
                {"from": "supplier", "body": "We can offer $2.50 per unit, lead time 4 weeks."},
            ]
        })
        assert resp.status_code == 200
        data = resp.json()

        assert "stage" in data
        valid_stages = ["Outreach Sent", "Quote Received", "Substitute y/n", "Send", "Not Yet"]
        assert data["stage"] in valid_stages


class TestExtractQuote:
    def test_extract_quote(self):
        """Quote extraction returns structured data."""
        resp = _post("/api/extract-quote", {
            "text": "Part Number: 12345-678, Unit Price: $15.50, Quantity: 200, Lead time: 6 weeks. Total: $3,100.00 USD."
        })
        assert resp.status_code == 200
        data = resp.json()

        assert "data" in data
        quote = data["data"]
        # Should have extracted at least some fields
        assert isinstance(quote, dict)
