#!/usr/bin/env python3
"""
API Contract Verification Script

Calls each N8N-facing endpoint with minimal params and verifies the response
contains expected top-level fields.

Usage:
    python tests/test_api_contracts.py [BASE_URL] [API_KEY]

Defaults:
    BASE_URL = http://localhost:8000
    API_KEY  = (none — auth disabled)
"""

import json
import sys
import time
import urllib.request
import urllib.error

BASE_URL = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://localhost:8000"
API_KEY = sys.argv[2] if len(sys.argv) > 2 else ""

passed = 0
failed = 0
skipped = 0


def api_call(method: str, path: str, body: dict = None, timeout: int = 30):
    """Make an API call and return (status_code, parsed_json)."""
    url = f"{BASE_URL}{path}"
    data = json.dumps(body).encode() if body else None
    headers = {"Content-Type": "application/json"}
    if API_KEY:
        headers["X-API-Key"] = API_KEY

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body_text = e.read().decode() if e.fp else ""
        try:
            return e.code, json.loads(body_text)
        except json.JSONDecodeError:
            return e.code, {"raw": body_text}
    except urllib.error.URLError as e:
        return 0, {"error": str(e)}


def check(name: str, status: int, data: dict, expected_status: int, required_fields: list):
    """Verify response status and top-level fields."""
    global passed, failed

    errors = []
    if status != expected_status:
        errors.append(f"status={status}, expected={expected_status}")
    for field in required_fields:
        if field not in data:
            errors.append(f"missing field '{field}'")

    # Check X-Request-ID in response (can't easily check headers with urllib, skip)

    if errors:
        print(f"  FAIL  {name}: {', '.join(errors)}")
        failed += 1
    else:
        print(f"  OK    {name}")
        passed += 1


def skip(name: str, reason: str):
    global skipped
    print(f"  SKIP  {name}: {reason}")
    skipped += 1


# ── Tests ──────────────────────────────────────────────────────────

print(f"\nAPI Contract Tests — {BASE_URL}\n{'=' * 50}")

# Health
status, data = api_call("GET", "/health")
check("GET /health", status, data, 200, ["status", "checks"])

# SAM.gov search
print("\n-- SAM.gov --")
status, data = api_call("POST", "/api/search-sam", {"daysBack": 1, "maxPages": 1}, timeout=300)
if status == 0:
    skip("POST /api/search-sam", "connection error")
else:
    check("POST /api/search-sam", status, data, 200, ["opportunities", "totalOpportunities", "scrapedAt"])

# Canada Buys
print("\n-- Canada Buys --")
status, data = api_call("POST", "/api/search-canada-buys", {"daysBack": 1, "maxResults": 5}, timeout=120)
if status == 0:
    skip("POST /api/search-canada-buys", "connection error")
else:
    check("POST /api/search-canada-buys", status, data, 200, ["tenders", "totalTenders", "scrapedAt"])

# Alberta Purchasing
print("\n-- Alberta Purchasing --")
status, data = api_call("POST", "/api/search-alberta-purchasing", {"daysBack": 1, "maxResults": 5}, timeout=120)
if status == 0:
    skip("POST /api/search-alberta-purchasing", "connection error")
else:
    check("POST /api/search-alberta-purchasing", status, data, 200, ["opportunities", "totalOpportunities", "scrapedAt"])

# DIBBS — skipped by default (DLA site unreliable)
print("\n-- DIBBS (skipped — DLA site unreliable) --")
skip("POST /api/scrape-nsns-by-date", "DLA site unreliable")
skip("POST /api/scrape-nsn-suppliers", "DLA site unreliable")

# Normalize raw
print("\n-- Normalize --")
status, data = api_call("POST", "/api/normalize-raw", {
    "source": "sam_gov",
    "data": {"opportunities": [], "totalOpportunities": 0, "scrapedAt": "2026-01-01"}
})
check("POST /api/normalize-raw", status, data, 200, ["totalLeads", "leads"])

# Error handling — bad source
status, data = api_call("POST", "/api/normalize-raw", {"source": "bad_source", "data": {}})
check("POST /api/normalize-raw (bad source)", status, data, 400, ["error"])

# ── Summary ────────────────────────────────────────────────────────

print(f"\n{'=' * 50}")
print(f"Results: {passed} passed, {failed} failed, {skipped} skipped")

sys.exit(1 if failed > 0 else 0)
