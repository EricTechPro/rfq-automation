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
    FIRECRAWL_TIMEOUT: int = int(get_secret("FIRECRAWL_TIMEOUT", "30000"))
    FIRECRAWL_CONCURRENCY: int = int(get_secret("FIRECRAWL_CONCURRENCY", "3"))

    # API Authentication
    RFQ_API_KEY: str = get_secret("RFQ_API_KEY", "")

    # Base URLs
    DIBBS_BASE_URL: str = os.getenv("DIBBS_BASE_URL", "https://www.dibbs.bsm.dla.mil/rfq/rfqnsn.aspx")
    WBPARTS_BASE_URL: str = os.getenv("WBPARTS_BASE_URL", "https://www.wbparts.com/rfq")
    SAM_GOV_BASE_URL: str = get_secret("SAM_GOV_BASE_URL", "https://sam.gov")
    SAM_GOV_API_URL: str = get_secret("SAM_GOV_API_URL", "https://api.sam.gov/opportunities/v2/search")
    SAM_GOV_API_KEY: str = get_secret("SAM_GOV_API_KEY", "")
    SAM_GOV_PAGE_SIZE: int = int(get_secret("SAM_GOV_PAGE_SIZE", "25"))
    SAM_GOV_DETAIL_TIMEOUT: int = int(get_secret("SAM_GOV_DETAIL_TIMEOUT", "15000"))
    SAM_GOV_MAX_DETAIL_PAGES: int = int(get_secret("SAM_GOV_MAX_DETAIL_PAGES", "50"))
    SAM_GOV_ENRICH_CONTACTS: bool = get_secret("SAM_GOV_ENRICH_CONTACTS", "true").lower() != "false"

    # Timeouts (in milliseconds)
    SCRAPE_TIMEOUT: int = int(os.getenv("SCRAPE_TIMEOUT", "90000"))

    # Retry configuration
    MAX_RETRIES: int = int(os.getenv("MAX_RETRIES", "3"))
    RETRY_DELAY: int = int(os.getenv("RETRY_DELAY", "1000"))

    # Rate limiting
    BATCH_DELAY: int = int(os.getenv("BATCH_DELAY", "500"))

    # OpenRouter LLM
    OPENROUTER_API_KEY: str = get_secret("OPENROUTER_API_KEY", "")
    OPENROUTER_MODEL: str = get_secret("OPENROUTER_MODEL", "google/gemini-2.5-flash-lite")

    # Email (IMAP/SMTP)
    EMAIL_ADDRESS: str = get_secret("EMAIL_ADDRESS", "")
    EMAIL_APP_PASSWORD: str = get_secret("EMAIL_APP_PASSWORD", "")

    # Canadian Portals
    CANADA_BUYS_FEED_URL: str = get_secret(
        "CANADA_BUYS_FEED_URL",
        "https://canadabuys.canada.ca/opendata/pub/openTenderNotice-ouvertAvisAppelOffres.csv"
    )
    APC_SCRAPE_DELAY: int = int(get_secret("APC_SCRAPE_DELAY", "3000"))
    APC_ENRICH_CONTACTS: bool = get_secret("APC_ENRICH_CONTACTS", "false").lower() != "false"
    APC_DETAIL_CONCURRENCY: int = int(get_secret("APC_DETAIL_CONCURRENCY", "5"))

    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FORMAT: str = os.getenv("LOG_FORMAT", "json")  # "json" (production) or "pretty" (local dev)

    # Browser settings
    HEADLESS: bool = os.getenv("HEADLESS", "true").lower() != "false"
    MAX_BROWSER_PAGES: int = int(os.getenv("MAX_BROWSER_PAGES", "4"))
    BROWSER_POOL_TIMEOUT: int = int(os.getenv("BROWSER_POOL_TIMEOUT", "300"))
    USER_AGENT: str = os.getenv(
        "USER_AGENT",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    @classmethod
    def is_firecrawl_configured(cls) -> bool:
        """Check if Firecrawl API is configured"""
        return bool(cls.FIRECRAWL_API_KEY and cls.FIRECRAWL_API_KEY.startswith("fc-"))

    @classmethod
    def is_llm_configured(cls) -> bool:
        """Check if OpenRouter LLM is configured"""
        return bool(cls.OPENROUTER_API_KEY)


config = Config()
