"""
CRM Dashboard - Streamlit Page

Pipeline status overview across all procurement sources (DIBBS, SAM.gov, Canada Buys, APC).
Shows opportunity counts, status breakdown, and recent activity.
"""

import asyncio
import pandas as pd
from datetime import datetime
import json

import streamlit as st

import sys
sys.path.insert(0, str(__file__).rsplit("/", 2)[0])

from config import config


# Page configuration
st.set_page_config(
    page_title="CRM Dashboard - RFQ Automation",
    page_icon="📊",
    layout="wide",
)


def main():
    """Main CRM Dashboard page"""

    st.title("📊 CRM Pipeline Dashboard")
    st.markdown("Overview of procurement opportunities across all sources.")
    st.markdown("---")

    # ==========================================
    # Source Status Cards
    # ==========================================
    st.markdown("### Source Status")

    col1, col2, col3, col4 = st.columns(4)

    sources = {
        "DIBBS": {
            "icon": "📅",
            "endpoint": "/api/available-dates",
            "status": "Active" if True else "Offline",
            "color": "green",
        },
        "SAM.gov": {
            "icon": "🏛️",
            "endpoint": "/api/search-sam",
            "status": "Active" if config.SAM_GOV_API_KEY or True else "No API Key",
            "color": "green" if config.SAM_GOV_API_KEY else "yellow",
        },
        "Canada Buys": {
            "icon": "🍁",
            "endpoint": "/api/search-canada-buys",
            "status": "Active",
            "color": "green",
        },
        "Alberta Purchasing": {
            "icon": "🏔️",
            "endpoint": "/api/search-alberta-purchasing",
            "status": "Active",
            "color": "green",
        },
    }

    for col, (name, info) in zip([col1, col2, col3, col4], sources.items()):
        with col:
            st.markdown(f"#### {info['icon']} {name}")
            st.markdown(f"**Status:** {info['status']}")
            st.markdown(f"**Endpoint:** `{info['endpoint']}`")

    st.markdown("---")

    # ==========================================
    # Pipeline Stages
    # ==========================================
    st.markdown("### Pipeline Stages")
    st.markdown("Track opportunities through the procurement workflow.")

    stages = [
        {"stage": "New", "description": "Freshly discovered opportunities", "icon": "🆕"},
        {"stage": "Outreach Sent", "description": "Initial email sent to supplier", "icon": "📧"},
        {"stage": "Quote Received", "description": "Supplier provided pricing", "icon": "💰"},
        {"stage": "Substitute y/n", "description": "Supplier offered alternative", "icon": "🔄"},
        {"stage": "Send", "description": "Ready for next action", "icon": "📤"},
        {"stage": "Not Yet", "description": "Paused for manual review", "icon": "⏸️"},
    ]

    cols = st.columns(len(stages))
    for col, stage in zip(cols, stages):
        with col:
            st.markdown(f"**{stage['icon']} {stage['stage']}**")
            st.caption(stage["description"])

    st.markdown("---")

    # ==========================================
    # Service Configuration Status
    # ==========================================
    st.markdown("### Service Configuration")

    config_items = [
        ("Firecrawl API", config.is_firecrawl_configured(), "Contact discovery"),
        ("SAM.gov API Key", bool(config.SAM_GOV_API_KEY), "SAM.gov search (Playwright fallback available)"),
        ("OpenRouter LLM", config.is_llm_configured(), "Email classification & drafting"),
        ("Email (SMTP/IMAP)", bool(config.EMAIL_ADDRESS), "Email outreach automation"),
        ("RFQ API Key", bool(config.RFQ_API_KEY), "API authentication"),
    ]

    for name, configured, purpose in config_items:
        status = "Configured" if configured else "Not configured"
        icon = "✅" if configured else "⚠️"
        st.markdown(f"{icon} **{name}**: {status} — {purpose}")

    st.markdown("---")

    # ==========================================
    # API Endpoints Reference
    # ==========================================
    st.markdown("### API Endpoints")

    endpoints = [
        ("GET", "/health", "Health check", "None"),
        ("POST", "/api/batch", "Batch NSN processing", "None"),
        ("POST", "/api/scrape-nsns-by-date", "DIBBS date scraper", "X-API-Key"),
        ("POST", "/api/scrape-nsn-suppliers", "NSN supplier contacts", "X-API-Key"),
        ("GET", "/api/available-dates", "DIBBS available dates", "X-API-Key"),
        ("POST", "/api/search-sam", "SAM.gov search", "X-API-Key"),
        ("POST", "/api/extract-document", "PDF/OCR extraction", "X-API-Key"),
        ("POST", "/api/search-canada-buys", "Canada Buys search", "X-API-Key"),
        ("POST", "/api/search-alberta-purchasing", "Alberta Purchasing search", "X-API-Key"),
        ("POST", "/api/classify-thread", "Email classification", "X-API-Key"),
        ("POST", "/api/draft-reply", "Email draft reply", "X-API-Key"),
        ("POST", "/api/extract-quote", "Quote data extraction", "X-API-Key"),
    ]

    df = pd.DataFrame(endpoints, columns=["Method", "Path", "Description", "Auth"])
    st.dataframe(df, use_container_width=True, hide_index=True)

    st.markdown("---")

    # ==========================================
    # n8n Workflow Reference
    # ==========================================
    st.markdown("### n8n Workflows")

    workflows = [
        ("RFQ Daily Scraper", "workflow-rfq-daily.json", "Daily DIBBS → Suppliers → Sheets"),
        ("SAM.gov Daily", "workflow-sam-daily.json", "Daily SAM.gov search → Sheets"),
        ("Document Pipeline", "workflow-document-pipeline.json", "PDF extraction → Sheets"),
        ("Canada Buys Daily", "workflow-canada-buys-daily.json", "Canada Buys feed → Sheets"),
        ("Alberta Daily", "workflow-alberta-daily.json", "APC scrape → Sheets"),
        ("Email Outreach", "workflow-email-outreach.json", "New row → Send email → Update status"),
        ("Email Monitor", "workflow-email-monitor.json", "IMAP poll → Classify → Draft reply → Sheets"),
    ]

    df_wf = pd.DataFrame(workflows, columns=["Workflow", "File", "Description"])
    st.dataframe(df_wf, use_container_width=True, hide_index=True)

    # ==========================================
    # Sidebar
    # ==========================================
    with st.sidebar:
        st.markdown("### 📊 CRM Dashboard")
        st.markdown("""
        **Overview of:**
        - All procurement sources
        - Pipeline stages
        - Service configuration
        - API endpoints
        - n8n workflows
        """)

        st.markdown("---")

        st.markdown("### Quick Links")
        st.markdown("""
        - [API Docs](/docs) (when running)
        - [DIBBS](https://www.dibbs.bsm.dla.mil/)
        - [SAM.gov](https://sam.gov)
        - [Canada Buys](https://canadabuys.canada.ca)
        - [Alberta Purchasing](https://purchasing.alberta.ca)
        """)


if __name__ == "__main__":
    main()
