"""
Shared test constants for RFQ Automation tests.
"""

import os

# Railway deployment base URL
API_BASE_URL = os.getenv(
    "RFQ_TEST_BASE_URL",
    "https://web-production-d9a0e.up.railway.app",
)

# API key for authenticated endpoints (must be set via env var for live tests)
API_KEY = os.getenv("RFQ_TEST_API_KEY", "")

# Known-good NSN for live testing (bolt, machine — common supply item)
KNOWN_NSN = "5306-00-373-3291"
