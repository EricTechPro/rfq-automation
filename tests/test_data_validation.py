"""
Unit tests for data accuracy — verify helpers and models work correctly.

Run with: pytest tests/test_data_validation.py -v
"""

import sys
import os

# Ensure project root is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from utils.helpers import validate_nsn, format_nsn, format_nsn_with_dashes
from models import (
    ApprovedSource, SupplierContact, ContactPerson,
    EnhancedRFQResult, SupplierWithContact, WorkflowStatus,
)
from core import flatten_to_rows
from services.firecrawl import calculate_confidence


# ── NSN Validation ──────────────────────────────────────────────────

class TestNSNValidation:
    def test_valid_nsn_with_dashes(self):
        assert validate_nsn("5306-00-373-3291") is True

    def test_valid_nsn_without_dashes(self):
        assert validate_nsn("5306003733291") is True

    def test_invalid_nsn_short(self):
        assert validate_nsn("12345") is False

    def test_invalid_nsn_letters(self):
        assert validate_nsn("ABCD-EF-GHI-JKLM") is False

    def test_invalid_nsn_empty(self):
        assert validate_nsn("") is False

    def test_invalid_nsn_wrong_dash_format(self):
        assert validate_nsn("53060-0-373-3291") is False


class TestNSNFormatting:
    def test_format_nsn_removes_dashes(self):
        assert format_nsn("5306-00-373-3291") == "5306003733291"

    def test_format_nsn_no_dashes_passthrough(self):
        assert format_nsn("5306003733291") == "5306003733291"

    def test_format_nsn_with_dashes_adds_dashes(self):
        assert format_nsn_with_dashes("5306003733291") == "5306-00-373-3291"

    def test_format_nsn_with_dashes_idempotent(self):
        assert format_nsn_with_dashes("5306-00-373-3291") == "5306-00-373-3291"

    def test_format_nsn_with_dashes_wrong_length(self):
        # Should return input unchanged if not 13 digits
        assert format_nsn_with_dashes("12345") == "12345"


# ── Contact Confidence Levels ───────────────────────────────────────

class TestConfidenceLevels:
    """Test the production calculate_confidence() function from firecrawl.py."""

    def test_high_confidence_all_fields(self):
        assert calculate_confidence(
            has_email=True, has_phone=True, has_address=True, has_website=True
        ) == "high"

    def test_medium_confidence_phone_only(self):
        assert calculate_confidence(
            has_email=False, has_phone=True, has_address=False, has_website=False
        ) == "medium"

    def test_medium_confidence_phone_and_email(self):
        assert calculate_confidence(
            has_email=True, has_phone=True, has_address=False, has_website=False
        ) == "medium"

    def test_medium_confidence_phone_and_address_no_website(self):
        assert calculate_confidence(
            has_email=True, has_phone=True, has_address=True, has_website=False
        ) == "medium"

    def test_low_confidence_website_only(self):
        assert calculate_confidence(
            has_email=False, has_phone=False, has_address=False, has_website=True
        ) == "low"

    def test_low_confidence_email_only(self):
        assert calculate_confidence(
            has_email=True, has_phone=False, has_address=False, has_website=False
        ) == "low"

    def test_low_confidence_nothing(self):
        assert calculate_confidence(
            has_email=False, has_phone=False, has_address=False, has_website=False
        ) == "low"


# ── Pydantic Model Serialization ───────────────────────────────────

class TestModelSerialization:
    def test_approved_source_camel_case(self):
        src = ApprovedSource(cageCode="1A2B3", partNumber="PN-123", companyName="Acme")
        d = src.model_dump(by_alias=True, exclude_none=True)
        assert "cageCode" in d
        assert "partNumber" in d
        assert "companyName" in d
        # Snake case keys should NOT appear in aliased output
        assert "cage_code" not in d

    def test_contact_person_model(self):
        cp = ContactPerson(name="John Doe", title="Sales", email="j@example.com", phone="555-0000")
        d = cp.model_dump(by_alias=True, exclude_none=True)
        assert d["name"] == "John Doe"

    def test_supplier_contact_exclude_none(self):
        sc = SupplierContact(
            companyName="Test",
            email=None,
            phone="555-1234",
            address=None,
            website=None,
            contactPage=None,
            additionalContacts=[],
            source="firecrawl_scrape",
            confidence="medium",
            scrapedAt="2026-01-01T00:00:00Z",
        )
        d = sc.model_dump(by_alias=True, exclude_none=True)
        assert "email" not in d
        assert "phone" in d


# ── Flatten Results ─────────────────────────────────────────────────

class TestFlattenResults:
    def _make_result(self, nsn="5306-00-373-3291", has_open_rfq=True, suppliers=None):
        return EnhancedRFQResult(
            nsn=nsn,
            itemName="BOLT",
            hasOpenRFQ=has_open_rfq,
            suppliers=suppliers or [],
            workflow=WorkflowStatus(
                dibbsStatus="success",
                wbpartsStatus="success",
                firecrawlStatus="success",
            ),
            scrapedAt="2026-01-01T00:00:00Z",
        )

    def test_flatten_no_suppliers(self):
        result = self._make_result(suppliers=[])
        rows = flatten_to_rows(result)
        assert len(rows) == 1
        assert rows[0]["supplier_name"] == ""
        assert rows[0]["open_status"] == "OPEN"

    def test_flatten_with_suppliers(self):
        suppliers = [
            SupplierWithContact(
                company_name="Acme",
                cage_code="1A2B3",
                part_number="PN-1",
                contact=SupplierContact(
                    companyName="Acme",
                    email="a@acme.com",
                    phone="555-1234",
                    address=None,
                    website=None,
                    contactPage=None,
                    additionalContacts=[],
                    source="firecrawl_scrape",
                    confidence="medium",
                    scrapedAt="2026-01-01T00:00:00Z",
                ),
            )
        ]
        result = self._make_result(suppliers=suppliers)
        rows = flatten_to_rows(result)
        assert len(rows) == 1
        assert rows[0]["supplier_name"] == "Acme"
        assert rows[0]["cage_code"] == "1A2B3"
        assert rows[0]["email"] == "a@acme.com"

    def test_flatten_closed_status(self):
        result = self._make_result(has_open_rfq=False)
        rows = flatten_to_rows(result)
        assert rows[0]["open_status"] == "CLOSED"

    def test_flatten_required_columns(self):
        result = self._make_result()
        rows = flatten_to_rows(result)
        required_cols = {"nsn", "open_status", "supplier_name", "cage_code", "email", "phone"}
        assert required_cols.issubset(set(rows[0].keys()))
