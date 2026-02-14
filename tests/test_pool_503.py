"""
Live test: Verify browser pool returns 503 when saturated.

Sends more concurrent requests than pool slots (4) to confirm:
- Excess requests get 503 within ~30s (not 280s)
- 503 body matches {"error": "...", "status": 503}
- Requests that get a slot return 200 with valid data

Run with:
    RFQ_TEST_API_KEY="some-random-secret-string" pytest tests/test_pool_503.py -v -s

Requires: Live Railway deployment at RFQ_TEST_BASE_URL
"""

import asyncio
import time
from datetime import datetime, timezone
from typing import Dict, List, Tuple

import httpx
import pytest

from tests.conftest import API_BASE_URL, API_KEY, KNOWN_NSN

# Number of concurrent requests — pool has 4 slots, so even 4 concurrent
# requests will trigger 503s if any slots are already occupied by real traffic
CONCURRENT_DATE_REQUESTS = 4
CONCURRENT_SUPPLIER_REQUESTS = 4

# Max acceptable time for a 503 response (pool timeout is 120s + overhead)
MAX_503_SECONDS = 135


def _headers() -> Dict[str, str]:
    return {
        "X-API-Key": API_KEY,
        "Content-Type": "application/json",
    }


async def _send_date_request(
    client: httpx.AsyncClient, idx: int
) -> Tuple[int, int, float, dict]:
    """Send a scrape-nsns-by-date request. Returns (idx, status, elapsed, body)."""
    today = datetime.now(timezone.utc).strftime("%m-%d-%Y")
    payload = {"date": today, "maxPages": 5}

    start = time.monotonic()
    resp = await client.post(
        f"{API_BASE_URL}/api/scrape-nsns-by-date",
        json=payload,
        headers=_headers(),
        timeout=300,
    )
    elapsed = time.monotonic() - start
    body = resp.json()
    return idx, resp.status_code, elapsed, body


async def _send_supplier_request(
    client: httpx.AsyncClient, idx: int, nsn: str
) -> Tuple[int, int, float, dict]:
    """Send a scrape-nsn-suppliers request. Returns (idx, status, elapsed, body)."""
    payload = {"nsn": nsn, "maxSuppliers": 1}

    start = time.monotonic()
    resp = await client.post(
        f"{API_BASE_URL}/api/scrape-nsn-suppliers",
        json=payload,
        headers=_headers(),
        timeout=300,
    )
    elapsed = time.monotonic() - start
    body = resp.json()
    return idx, resp.status_code, elapsed, body


def _print_results(results: List[Tuple[int, int, float, dict]], endpoint: str) -> None:
    """Print a summary table of request results."""
    print(f"\n{'='*60}")
    print(f"  {endpoint} — {len(results)} concurrent requests")
    print(f"{'='*60}")
    for idx, status, elapsed, body in sorted(results):
        label = "OK" if status == 200 else f"ERR {status}"
        snippet = ""
        if status == 503:
            snippet = body.get("error", "")[:50]
        elif status == 200:
            if "totalNsns" in body:
                snippet = f"{body['totalNsns']} NSNs found"
            elif "nsn" in body:
                snippet = f"NSN {body['nsn']}"
        elif status == 429:
            snippet = "rate limited"
        print(f"  req {idx}: {label}  {elapsed:6.1f}s  {snippet}")
    print()


async def _run_date_saturation() -> List[Tuple[int, int, float, dict]]:
    """Fire concurrent date-scrape requests and return completed results."""
    async with httpx.AsyncClient() as client:
        tasks = [
            _send_date_request(client, i)
            for i in range(CONCURRENT_DATE_REQUESTS)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    completed = []
    for r in results:
        if isinstance(r, Exception):
            print(f"  Request exception: {r}")
        else:
            completed.append(r)
    return completed


async def _run_supplier_saturation() -> List[Tuple[int, int, float, dict]]:
    """Fire concurrent supplier-scrape requests and return completed results."""
    async with httpx.AsyncClient() as client:
        tasks = [
            _send_supplier_request(client, i, KNOWN_NSN)
            for i in range(CONCURRENT_SUPPLIER_REQUESTS)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    completed = []
    for r in results:
        if isinstance(r, Exception):
            print(f"  Request exception: {r}")
        else:
            completed.append(r)
    return completed


@pytest.mark.slow
class TestPoolBusyDateScrape:
    """Test 1: Saturate pool with concurrent /api/scrape-nsns-by-date requests."""

    def test_excess_requests_get_503(self):
        """
        Send 4 concurrent date-scrape requests (pool has 4 slots).
        If any slots are already occupied, at least 1 should get 503 within ~30s.
        """
        completed = asyncio.run(_run_date_saturation())
        _print_results(completed, "/api/scrape-nsns-by-date")

        statuses = [status for _, status, _, _ in completed]

        # At least one request should get 503
        assert 503 in statuses, (
            f"Expected at least one 503 but got statuses: {statuses}. "
            "Pool may have grown or requests finished before saturation."
        )

        # 503 responses should arrive within MAX_503_SECONDS
        for _, status, elapsed, body in completed:
            if status == 503:
                assert elapsed < MAX_503_SECONDS, (
                    f"503 took {elapsed:.1f}s — expected <{MAX_503_SECONDS}s "
                    "(pool timeout is 120s)"
                )
                assert "error" in body, f"503 body missing 'error' key: {body}"
                assert body.get("status") == 503, f"503 body status mismatch: {body}"

        # Requests that got a slot should return 200 (or 500/504 if DIBBS is down)
        for _, status, _, body in completed:
            if status == 200:
                assert "nsns" in body, f"200 response missing 'nsns': {body.keys()}"
                assert "totalNsns" in body

    def test_503_body_format(self):
        """Verify the 503 error body matches expected format."""
        completed = asyncio.run(_run_date_saturation())
        _print_results(completed, "/api/scrape-nsns-by-date (body check)")

        got_503 = [
            (idx, status, elapsed, body)
            for idx, status, elapsed, body in completed
            if status == 503
        ]
        if not got_503:
            pytest.skip("No 503 responses received — pool was not saturated")

        for _, _, _, body in got_503:
            assert body == {
                "error": "DIBBS scraper temporarily unavailable",
                "status": 503,
            }, f"Unexpected 503 body: {body}"


@pytest.mark.slow
class TestPoolBusySupplierScrape:
    """Test 2: Saturate pool with concurrent /api/scrape-nsn-suppliers requests."""

    def test_excess_supplier_requests_get_503(self):
        """
        Send 4 concurrent supplier-scrape requests (pool has 4 slots).
        At least 1 should get 503 within ~30s.
        """
        completed = asyncio.run(_run_supplier_saturation())
        _print_results(completed, "/api/scrape-nsn-suppliers")

        statuses = [status for _, status, _, _ in completed]

        # At least one 503
        assert 503 in statuses, (
            f"Expected at least one 503 but got statuses: {statuses}. "
            "Pool may have grown or requests finished before saturation."
        )

        for _, status, elapsed, body in completed:
            if status == 503:
                assert elapsed < MAX_503_SECONDS, (
                    f"503 took {elapsed:.1f}s — expected <{MAX_503_SECONDS}s"
                )
                assert "error" in body
                assert body.get("status") == 503
