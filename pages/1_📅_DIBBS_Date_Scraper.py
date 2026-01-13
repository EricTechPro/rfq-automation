"""
Scrape by Date - Streamlit Page

Full workflow:
1. Load available dates from DIBBS
2. Select date and scrape all NSNs
3. Optionally scrape supplier contacts for each NSN
4. Export as CSV/JSON
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

from scrapers.dibbs_date import scrape_available_dates, scrape_nsns_by_date
from core import scrape_nsn


# Page configuration
st.set_page_config(
    page_title="DIBBS Date Scraper - RFQ Automation",
    page_icon="📅",
    layout="wide",
)


async def fetch_available_dates():
    """Fetch available dates from DIBBS"""
    return await scrape_available_dates()


async def fetch_nsns_for_date(date: str, max_pages: int):
    """Fetch NSNs for a specific date"""
    return await scrape_nsns_by_date(date, max_pages)


async def fetch_supplier_contacts(nsn: str):
    """Fetch supplier contacts for an NSN"""
    return await scrape_nsn(nsn)


def main():
    """Main Streamlit page"""

    st.title("📅 DIBBS Date Scraper")
    st.markdown("Scrape NSNs from DIBBS by date, then optionally get supplier contacts.")

    st.markdown("---")

    # Initialize session state
    if "available_dates" not in st.session_state:
        st.session_state.available_dates = None
    if "scrape_results" not in st.session_state:
        st.session_state.scrape_results = None
    if "supplier_results" not in st.session_state:
        st.session_state.supplier_results = None

    # ==========================================
    # STEP 1: Load Available Dates
    # ==========================================
    st.markdown("### Step 1: Load Available Dates")

    col1, col2 = st.columns([3, 1])

    with col1:
        st.info("Fetch the list of available RFQ issue dates from DIBBS.")

    with col2:
        load_dates_button = st.button(
            "🔄 Load Dates",
            type="primary" if st.session_state.available_dates is None else "secondary",
            use_container_width=True
        )

    if load_dates_button:
        with st.spinner("Fetching available dates from DIBBS..."):
            try:
                result = asyncio.run(fetch_available_dates())
                st.session_state.available_dates = result["dates"]
                st.success(f"Found {len(result['dates'])} available dates!")
            except Exception as e:
                st.error(f"Failed to fetch dates: {str(e)}")

    if st.session_state.available_dates:
        st.success(f"✅ {len(st.session_state.available_dates)} dates loaded")

    st.markdown("---")

    # ==========================================
    # STEP 2: Select Date and Scrape NSNs
    # ==========================================
    st.markdown("### Step 2: Select Date and Scrape NSNs")

    if not st.session_state.available_dates:
        st.warning("⚠️ Please load available dates first (Step 1)")
    else:
        col1, col2, col3, col4 = st.columns([2, 1, 1, 1])

        with col1:
            selected_date = st.selectbox(
                "Select Date",
                options=st.session_state.available_dates,
                index=0,
                help="Select a date to scrape all NSNs"
            )

        with col2:
            scrape_all_pages = st.checkbox(
                "Scrape All Pages",
                value=True,
                help="Check to scrape all pages, uncheck to limit"
            )

        with col3:
            if scrape_all_pages:
                max_pages = 0
                st.text_input("Max Pages", value="All", disabled=True)
            else:
                max_pages = st.number_input(
                    "Max Pages",
                    min_value=1,
                    max_value=100,
                    value=1,
                    help="Limit to N pages"
                )

        with col4:
            st.markdown("<br>", unsafe_allow_html=True)
            scrape_button = st.button(
                "🔍 Scrape NSNs",
                type="primary",
                use_container_width=True
            )

        if scrape_button and selected_date:
            pages_msg = "all pages" if max_pages == 0 else f"{max_pages} page(s)"
            with st.spinner(f"Scraping NSNs for {selected_date} ({pages_msg})..."):
                try:
                    result = asyncio.run(fetch_nsns_for_date(selected_date, max_pages))
                    st.session_state.scrape_results = result
                    st.session_state.supplier_results = None  # Reset supplier results
                    st.success(f"Found {result['totalNsns']} NSNs!")
                except Exception as e:
                    st.error(f"Scraping failed: {str(e)}")

        # Display NSN Results
        if st.session_state.scrape_results:
            result = st.session_state.scrape_results

            st.markdown("---")
            st.markdown("### 📊 NSN Results")

            # Summary metrics
            col1, col2, col3, col4 = st.columns(4)

            with col1:
                st.metric("Date", result["date"])
            with col2:
                st.metric("Total NSNs", result["totalNsns"])
            with col3:
                st.metric("Pages Scraped", f"{result['pagesScraped']}/{result['totalPages']}")
            with col4:
                st.metric("Scraped At", result["scrapedAt"][:10])

            if result["nsns"]:
                # Results table
                st.markdown("#### NSN List")

                df = pd.DataFrame(result["nsns"])
                df.columns = ["NSN", "Description", "Solicitation", "QTY", "Issue Date", "Return By"]

                st.dataframe(
                    df,
                    use_container_width=True,
                    hide_index=True,
                    height=400
                )

                # Export section
                st.markdown("#### 📥 Export NSN Data")

                col1, col2 = st.columns(2)

                with col1:
                    # CSV download
                    csv_buffer = io.StringIO()
                    df.to_csv(csv_buffer, index=False)
                    csv_data = csv_buffer.getvalue()

                    st.download_button(
                        label="📊 Download CSV",
                        data=csv_data,
                        file_name=f"nsns_{result['date']}.csv",
                        mime="text/csv",
                        use_container_width=True
                    )

                with col2:
                    # JSON download
                    json_data = json.dumps(result, indent=2)

                    st.download_button(
                        label="📥 Download JSON",
                        data=json_data,
                        file_name=f"nsns_{result['date']}.json",
                        mime="application/json",
                        use_container_width=True
                    )

                # JSON Preview
                st.markdown("#### 🔍 JSON Preview")
                with st.expander("View JSON Structure", expanded=False):
                    st.json(result)

            else:
                st.info("No NSNs found for this date.")

    st.markdown("---")

    # ==========================================
    # STEP 3: Scrape Supplier Contacts
    # ==========================================
    st.markdown("### Step 3: Scrape Supplier Contacts (Optional)")

    if not st.session_state.scrape_results or not st.session_state.scrape_results.get("nsns"):
        st.warning("⚠️ Please scrape NSNs first (Step 2)")
    else:
        nsns = st.session_state.scrape_results["nsns"]
        total_nsns = len(nsns)

        st.info(f"Found **{total_nsns} NSNs**. You can now scrape supplier contacts for each one using Firecrawl.")

        col1, col2, col3 = st.columns([1, 1, 1])

        with col1:
            scrape_all_nsns = st.checkbox(
                "Scrape All NSNs",
                value=False,
                help="Scrape contacts for all NSNs (may take a while)"
            )

        with col2:
            if scrape_all_nsns:
                max_nsns = total_nsns
                st.text_input("Max NSNs", value=f"All ({total_nsns})", disabled=True)
            else:
                max_nsns = st.number_input(
                    "Max NSNs to Scrape",
                    min_value=1,
                    max_value=total_nsns,
                    value=min(5, total_nsns),
                    help="Limit number of NSNs to scrape contacts for"
                )

        with col3:
            st.markdown("<br>", unsafe_allow_html=True)
            scrape_suppliers_button = st.button(
                "🔍 Scrape Supplier Contacts",
                type="primary",
                use_container_width=True
            )

        if scrape_suppliers_button:
            nsns_to_scrape = nsns[:max_nsns]
            supplier_results = []

            progress_bar = st.progress(0)
            status_text = st.empty()

            for idx, nsn_data in enumerate(nsns_to_scrape):
                nsn = nsn_data["nsn"]
                status_text.markdown(f"**Processing {idx + 1}/{len(nsns_to_scrape)}:** {nsn}")
                progress_bar.progress((idx + 1) / len(nsns_to_scrape))

                try:
                    result = asyncio.run(fetch_supplier_contacts(nsn))

                    # Filter to HIGH and MEDIUM confidence
                    filtered_suppliers = []
                    for supplier in result.suppliers:
                        if supplier.contact and supplier.contact.confidence in ["high", "medium"]:
                            filtered_suppliers.append({
                                "nsn": nsn,
                                "nomenclature": nsn_data.get("nomenclature", ""),
                                "quantity": nsn_data.get("quantity", 0),
                                "companyName": supplier.company_name,
                                "cageCode": supplier.cage_code,
                                "partNumber": supplier.part_number,
                                "email": supplier.contact.email or "",
                                "phone": supplier.contact.phone or "",
                                "address": supplier.contact.address or "",
                                "website": supplier.contact.website or "",
                                "confidence": supplier.contact.confidence
                            })

                    supplier_results.extend(filtered_suppliers)

                except Exception as e:
                    st.warning(f"Failed to scrape {nsn}: {str(e)}")

            progress_bar.progress(1.0)
            status_text.markdown(f"**✅ Complete!** Found {len(supplier_results)} supplier contacts.")

            st.session_state.supplier_results = supplier_results

        # Display Supplier Results
        if st.session_state.supplier_results:
            suppliers = st.session_state.supplier_results

            st.markdown("---")
            st.markdown("### 📋 Supplier Contact Results")

            st.metric("Total Supplier Contacts", len(suppliers))

            if suppliers:
                # Results table
                df_suppliers = pd.DataFrame(suppliers)

                st.dataframe(
                    df_suppliers,
                    use_container_width=True,
                    hide_index=True,
                    height=400
                )

                # Export section
                st.markdown("#### 📥 Export Supplier Data")

                col1, col2 = st.columns(2)

                with col1:
                    csv_buffer = io.StringIO()
                    df_suppliers.to_csv(csv_buffer, index=False)
                    csv_data = csv_buffer.getvalue()

                    st.download_button(
                        label="📊 Download Suppliers CSV",
                        data=csv_data,
                        file_name=f"suppliers_{st.session_state.scrape_results['date']}.csv",
                        mime="text/csv",
                        use_container_width=True
                    )

                with col2:
                    json_data = json.dumps(suppliers, indent=2)

                    st.download_button(
                        label="📥 Download Suppliers JSON",
                        data=json_data,
                        file_name=f"suppliers_{st.session_state.scrape_results['date']}.json",
                        mime="application/json",
                        use_container_width=True
                    )

                # JSON Preview
                st.markdown("#### 🔍 Supplier JSON Preview")
                with st.expander("View Supplier JSON Structure", expanded=False):
                    st.json(suppliers[:5] if len(suppliers) > 5 else suppliers)

            else:
                st.info("No supplier contacts found (all were LOW confidence).")

    # ==========================================
    # Sidebar
    # ==========================================
    with st.sidebar:
        st.markdown("### 📅 DIBBS Date Scraper")
        st.markdown("""
        **Workflow:**
        1. **Load Dates** - Get available dates from DIBBS
        2. **Scrape NSNs** - Get all NSNs for a date
        3. **Scrape Contacts** - Get supplier info via Firecrawl
        4. **Export** - Download CSV or JSON
        """)

        st.markdown("---")

        st.markdown("### Confidence Levels")
        st.markdown("""
        | Level | Requirements |
        |-------|--------------|
        | **HIGH** | Email + Phone + Address + Website |
        | **MEDIUM** | At least phone number |
        | **LOW** | Dropped (website only) |
        """)

        st.markdown("---")

        st.markdown("### 💡 Tips")
        st.markdown("""
        - Use "Scrape All Pages" to get every NSN
        - Start with a few NSNs to test supplier scraping
        - HIGH/MEDIUM contacts are kept, LOW are filtered out
        """)


if __name__ == "__main__":
    main()
