"""
Configuration Module

Centralized configuration loader for the RFQ Automation scraper.
Supports both local .env files AND Streamlit Cloud secrets.

Local development: Use .env file
Streamlit Cloud: Use Secrets dashboard (TOML format)
"""

import os
from dotenv import load_dotenv

# Load .env file for local development
load_dotenv()


def get_secret(key: str, default: str = "") -> str:
    """
    Get a secret value, checking Streamlit secrets first (for cloud deployment),
    then falling back to environment variables (for local development).
    """
    # Try Streamlit secrets first (for Streamlit Cloud deployment)
    try:
        import streamlit as st
        if hasattr(st, 'secrets') and key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass  # Not running in Streamlit or secrets not configured

    # Fall back to environment variables (local development)
    return os.getenv(key, default)


class Config:
    """Application configuration"""

    # Firecrawl API
    FIRECRAWL_API_KEY: str = get_secret("FIRECRAWL_API_KEY", "")
    FIRECRAWL_API_URL: str = get_secret("FIRECRAWL_API_URL", "https://api.firecrawl.dev/v2")
    FIRECRAWL_TIMEOUT: int = int(get_secret("FIRECRAWL_TIMEOUT", "60000"))

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
