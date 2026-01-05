"""
Configuration Module

Centralized configuration loader for the RFQ Automation scraper.
Loads settings from environment variables with sensible defaults.
"""

import os
from dotenv import load_dotenv

# Load .env file
load_dotenv()


class Config:
    """Application configuration"""

    # Firecrawl API
    FIRECRAWL_API_KEY: str = os.getenv("FIRECRAWL_API_KEY", "")
    FIRECRAWL_API_URL: str = os.getenv("FIRECRAWL_API_URL", "https://api.firecrawl.dev/v2")
    FIRECRAWL_TIMEOUT: int = int(os.getenv("FIRECRAWL_TIMEOUT", "60000"))

    # Base URLs
    DIBBS_BASE_URL: str = os.getenv("DIBBS_BASE_URL", "https://www.dibbs.bsm.dla.mil/rfq/rfqnsn.aspx")
    WBPARTS_BASE_URL: str = os.getenv("WBPARTS_BASE_URL", "https://www.wbparts.com/rfq")

    # Timeouts (in milliseconds)
    SCRAPE_TIMEOUT: int = int(os.getenv("SCRAPE_TIMEOUT", "30000"))

    # Retry configuration
    MAX_RETRIES: int = int(os.getenv("MAX_RETRIES", "3"))
    RETRY_DELAY: int = int(os.getenv("RETRY_DELAY", "1000"))

    # Rate limiting
    BATCH_DELAY: int = int(os.getenv("BATCH_DELAY", "500"))

    # Browser settings
    HEADLESS: bool = os.getenv("HEADLESS", "true").lower() != "false"
    USER_AGENT: str = os.getenv(
        "USER_AGENT",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    @classmethod
    def is_firecrawl_configured(cls) -> bool:
        """Check if Firecrawl API is configured"""
        return bool(cls.FIRECRAWL_API_KEY and cls.FIRECRAWL_API_KEY.startswith("fc-"))


config = Config()
