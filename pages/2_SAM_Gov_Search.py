"""
SAM.gov Search - Streamlit Page

Search for contract opportunities on SAM.gov.
Uses the SAM.gov public API (requires SAM_GOV_API_KEY).

Workflow:
1. Configure search filters (days back, set-aside, procurement type)
2. Search SAM.gov for matching opportunities
3. View results and export as CSV/JSON
"""

import asyncio
import pandas as pd
from datetime import datetime
import io
import json

import streamlit as st

# Import scraper functions
import sys
sys.path.insert(0, str(__file__).rsplit("/", 2)[0])

from scrapers.sam_gov import search_opportunities, VALID_SET_ASIDES, VALID_PTYPES
from config import config


# Page configuration
st.set_page_config(
    page_title="SAM.gov Search - RFQ Automation",
    page_icon="🏛️",
    layout="wide",
)


async def fetch_opportunities(days_back, set_aside, ptype, naics_code, keyword, max_pages, enrich_contacts=True):
    """Fetch opportunities from SAM.gov"""
    return await search_opportunities(
        days_back=days_back,
        set_aside=set_aside if set_aside != "Any" else None,
        ptype=ptype if ptype != "Any" else None,
        naics_code=naics_code if naics_code else None,
        keyword=keyword if keyword else None,
        max_pages=max_pages,
        enrich_contacts=enrich_contacts,
    )


def main():
    """Main Streamlit page"""

    st.title("🏛️ SAM.gov Opportunity Search")
    st.markdown("Search for federal contract opportunities on SAM.gov using the public API.")

    # Check API key
    if not config.SAM_GOV_API_KEY:
        st.info(
            "**Using Playwright scraper** (no API key needed). "
            "For faster results, get a free API key at [sam.gov](https://sam.gov) > Account > API Key, "
            "then add `SAM_GOV_API_KEY` to your `.env` file."
        )

    st.markdown("---")

    # Initialize session state
    if "sam_results" not in st.session_state:
        st.session_state.sam_results = None

    # ==========================================
    # Search Filters
    # ==========================================
    st.markdown("### Search Filters")

    col1, col2, col3 = st.columns(3)

    with col1:
        days_back = st.slider(
            "Days Back",
            min_value=1,
            max_value=365,
            value=7,
            help="Number of days to look back for posted opportunities"
        )

        # Set-aside filter
        set_aside_options = ["Any"] + list(VALID_SET_ASIDES.keys())
        set_aside_labels = ["Any"] + [
            f"{k} - {v}" for k, v in VALID_SET_ASIDES.items()
        ]
        set_aside_idx = st.selectbox(
            "Set-Aside Type",
            options=range(len(set_aside_options)),
            format_func=lambda i: set_aside_labels[i],
            index=0,
            help="Filter by small business set-aside type"
        )
        set_aside = set_aside_options[set_aside_idx]

    with col2:
        # Procurement type filter
        ptype_options = ["Any"] + list(VALID_PTYPES.keys())
        ptype_labels = ["Any"] + [
            f"{v}" for v in VALID_PTYPES.values()
        ]
        ptype_idx = st.selectbox(
            "Procurement Type",
            options=range(len(ptype_options)),
            format_func=lambda i: ptype_labels[i],
            index=0,
            help="Filter by procurement type"
        )
        ptype = ptype_options[ptype_idx]

        naics_code = st.text_input(
            "NAICS Code",
            value="",
            help="Filter by NAICS industry code (up to 6 digits)",
            max_chars=6,
        )

    with col3:
        keyword = st.text_input(
            "Keyword Search",
            value="",
            help="Search in opportunity titles"
        )

        max_pages = st.number_input(
            "Max Pages",
            min_value=1,
            max_value=50,
            value=5,
            help="Maximum number of API pages to fetch (100 results per page)"
        )

        enrich_contacts = st.checkbox(
            "Fetch contact details",
            value=True,
            help="Visit each result's detail page to get contact info (~2s per result)"
        )

    # Search button
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        search_button = st.button(
            "🔍 Search SAM.gov",
            type="primary",
            use_container_width=True
        )

    if search_button:
        spinner_msg = "Searching SAM.gov and fetching contacts..." if enrich_contacts else "Searching SAM.gov..."
        with st.spinner(spinner_msg):
            try:
                result = asyncio.run(fetch_opportunities(
                    days_back=days_back,
                    set_aside=set_aside,
                    ptype=ptype,
                    naics_code=naics_code,
                    keyword=keyword,
                    max_pages=max_pages,
                    enrich_contacts=enrich_contacts,
                ))
                st.session_state.sam_results = result

                if result.get("error"):
                    st.error(f"API Error: {result['error']}")
                else:
                    st.success(f"Found {result['totalOpportunities']} opportunities!")

            except Exception as e:
                st.error(f"Search failed: {str(e)}")

    # ==========================================
    # Results Display
    # ==========================================
    if st.session_state.sam_results:
        result = st.session_state.sam_results

        if result.get("error") and not result.get("opportunities"):
            pass  # Error already shown above
        else:
            st.markdown("---")
            st.markdown("### 📊 Search Results")

            # Summary metrics
            col1, col2, col3, col4 = st.columns(4)

            with col1:
                st.metric("Total Opportunities", result["totalOpportunities"])
            with col2:
                st.metric("Results Fetched", len(result.get("opportunities", [])))
            with col3:
                st.metric("Pages Scraped", f"{result['pagesScraped']}/{result['totalPages']}")
            with col4:
                st.metric("Scraped At", result["scrapedAt"][:10])

            opps = result.get("opportunities", [])
            if opps:
                # Build dataframe
                rows = []
                for opp in opps:
                    # Get primary contact
                    contacts = opp.get("pointOfContact", [])
                    primary = next((c for c in contacts if c.get("type") == "primary"), None)
                    if not primary and contacts:
                        primary = contacts[0]

                    rows.append({
                        "Title": opp.get("title", ""),
                        "Solicitation #": opp.get("solicitationNumber", ""),
                        "Type": opp.get("noticeType", ""),
                        "Set-Aside": opp.get("setAside", ""),
                        "Agency": opp.get("agency") or opp.get("department", ""),
                        "Posted": opp.get("postedDate", "")[:10] if opp.get("postedDate") else "",
                        "Deadline": opp.get("responseDeadline", "")[:10] if opp.get("responseDeadline") else "",
                        "NAICS": opp.get("naicsCode", ""),
                        "Contact Name": primary.get("name", "") if primary else "",
                        "Contact Email": primary.get("email", "") if primary else "",
                        "Contact Phone": primary.get("phone", "") if primary else "",
                        "Location": opp.get("placeOfPerformance", ""),
                        "Link": opp.get("sourceUrl", ""),
                    })

                df = pd.DataFrame(rows)

                st.markdown("#### Opportunities")
                st.dataframe(
                    df,
                    use_container_width=True,
                    hide_index=True,
                    height=400,
                )

                # Export section
                st.markdown("#### 📥 Export Data")

                col1, col2 = st.columns(2)

                with col1:
                    csv_buffer = io.StringIO()
                    df.to_csv(csv_buffer, index=False)
                    csv_data = csv_buffer.getvalue()

                    st.download_button(
                        label="📊 Download CSV",
                        data=csv_data,
                        file_name=f"sam_gov_{datetime.now().strftime('%Y-%m-%d')}.csv",
                        mime="text/csv",
                        use_container_width=True,
                    )

                with col2:
                    json_data = json.dumps(result, indent=2)

                    st.download_button(
                        label="📥 Download JSON",
                        data=json_data,
                        file_name=f"sam_gov_{datetime.now().strftime('%Y-%m-%d')}.json",
                        mime="application/json",
                        use_container_width=True,
                    )

                # JSON Preview
                st.markdown("#### 🔍 JSON Preview")
                with st.expander("View JSON Structure", expanded=False):
                    preview = {
                        **{k: v for k, v in result.items() if k != "opportunities"},
                        "opportunities": opps[:3],
                    }
                    st.json(preview)

            else:
                st.info("No opportunities found matching your criteria.")

    # ==========================================
    # Sidebar
    # ==========================================
    with st.sidebar:
        st.markdown("### 🏛️ SAM.gov Search")
        st.markdown("""
        **Workflow:**
        1. **Set Filters** - Days back, set-aside, type
        2. **Search** - Query SAM.gov API
        3. **Review** - Browse opportunities
        4. **Export** - Download CSV or JSON
        """)

        st.markdown("---")

        st.markdown("### Set-Aside Types")
        st.markdown("""
        | Code | Description |
        |------|-------------|
        | **SBA** | Total Small Business |
        | **8A** | 8(a) Set-Aside |
        | **HZC** | HUBZone |
        | **SDVOSBC** | Service-Disabled Vet |
        | **WOSB** | Women-Owned SB |
        """)

        st.markdown("---")

        st.markdown("### 💡 Tips")
        st.markdown("""
        - Get a free API key at [sam.gov](https://sam.gov)
        - Use NAICS codes to filter by industry
        - Combine filters to narrow results
        - Export to CSV for Google Sheets import
        """)

        st.markdown("---")
        if config.SAM_GOV_API_KEY:
            st.markdown("**Mode:** API (key configured)")
        else:
            st.markdown("**Mode:** Playwright scraper (no API key)")


if __name__ == "__main__":
    main()
