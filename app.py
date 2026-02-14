"""
RFQ Automation Streamlit App

Web interface for the RFQ Automation scraper.
All features enabled by default: DIBBS + WBParts + Contact Discovery
"""

import asyncio
import json
from datetime import datetime

import streamlit as st

from config import config
from models import (
    EnhancedRFQResult,
    SupplierWithContact,
)
from core import scrape_nsn, scrape_batch
from utils.helpers import (
    validate_nsn,
    format_nsn_with_dashes,
    save_result,
)


# Page configuration
st.set_page_config(
    page_title="RFQ Automation",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS
st.markdown("""
<style>
    .supplier-card {
        background-color: #f0f2f6;
        border-radius: 10px;
        padding: 20px;
        margin: 10px 0;
    }
    .confidence-high { color: #28a745; font-weight: bold; }
    .confidence-medium { color: #ffc107; font-weight: bold; }
    .confidence-low { color: #dc3545; font-weight: bold; }
    .status-open { color: #28a745; }
    .status-closed { color: #dc3545; }
    .metric-card {
        background-color: #ffffff;
        border: 1px solid #e0e0e0;
        border-radius: 8px;
        padding: 15px;
        text-align: center;
    }
</style>
""", unsafe_allow_html=True)


# Core scraping functions imported from core.py:
# - scrape_nsn(nsn, progress_callback) -> EnhancedRFQResult
# - scrape_batch(nsns, progress_callback, batch_status_callback) -> BatchProcessingResult


async def run_scrape(nsn: str, progress_callback) -> EnhancedRFQResult:
    """Wrapper that calls scrape_nsn from core.py."""
    return await scrape_nsn(nsn, progress_callback)


async def run_batch_scrape(nsns: list, progress_callback, batch_status_callback):
    """Wrapper that calls scrape_batch from core.py."""
    return await scrape_batch(nsns, progress_callback, batch_status_callback)


def render_supplier_card(supplier: SupplierWithContact):
    """Render a supplier card with contact info"""
    with st.container():
        st.markdown(f"""
        <div class="supplier-card">
            <h4>🏢 {supplier.company_name}</h4>
            <p><strong>CAGE Code:</strong> {supplier.cage_code}</p>
            <p><strong>Part Number:</strong> {supplier.part_number}</p>
        </div>
        """, unsafe_allow_html=True)

        if supplier.contact:
            contact = supplier.contact

            col1, col2 = st.columns(2)

            with col1:
                if contact.email:
                    st.markdown(f"📧 **Email:** {contact.email}")
                if contact.phone:
                    st.markdown(f"📞 **Phone:** {contact.phone}")

            with col2:
                if contact.website:
                    st.markdown(f"🌐 **Website:** [{contact.website}]({contact.website})")
                if contact.address:
                    st.markdown(f"📍 **Address:** {contact.address}")

            # Confidence indicator
            confidence_class = f"confidence-{contact.confidence}"
            confidence_emoji = {"high": "🟢", "medium": "🟡", "low": "🔴"}.get(contact.confidence, "⚪")
            st.markdown(f"**Confidence:** <span class='{confidence_class}'>{confidence_emoji} {contact.confidence.upper()}</span>", unsafe_allow_html=True)

            # Additional contacts
            if contact.additional_contacts:
                with st.expander("Additional Contacts"):
                    for person in contact.additional_contacts:
                        info = []
                        if person.name:
                            info.append(f"**{person.name}**")
                        if person.title:
                            info.append(f"({person.title})")
                        if person.email:
                            info.append(f"📧 {person.email}")
                        if person.phone:
                            info.append(f"📞 {person.phone}")
                        st.markdown(" | ".join(info))
        else:
            st.warning("No contact information found")

        st.markdown("---")


def render_batch_results_table(batch_result):
    """Render summary table of all batch results"""
    import pandas as pd
    from models import BatchProcessingResult

    # Build table data
    table_data = []
    for idx, nsn_result in enumerate(batch_result.results, start=1):
        row = {
            "#": idx,
            "NSN": nsn_result.nsn,
            "Status": nsn_result.status.upper(),
            "Item Name": "",
            "RFQ Status": "",
            "Suppliers": 0,
            "Error": ""
        }

        if nsn_result.status == "success" and nsn_result.result:
            result = nsn_result.result
            row["Item Name"] = result.item_name or "N/A"
            row["RFQ Status"] = "OPEN" if result.has_open_rfq else "CLOSED"
            row["Suppliers"] = len(result.suppliers)
        elif nsn_result.status == "error":
            row["Error"] = nsn_result.error_message or "Unknown error"

        table_data.append(row)

    # Create DataFrame
    df = pd.DataFrame(table_data)

    # Display table with styling
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "#": st.column_config.NumberColumn(width="small"),
            "NSN": st.column_config.TextColumn(width="medium"),
            "Status": st.column_config.TextColumn(width="small"),
            "Item Name": st.column_config.TextColumn(width="large"),
            "RFQ Status": st.column_config.TextColumn(width="small"),
            "Suppliers": st.column_config.NumberColumn(width="small"),
            "Error": st.column_config.TextColumn(width="medium")
        }
    )

    return df


def export_batch_to_csv(batch_result) -> str:
    """Export batch results to CSV format"""
    import io
    import csv
    from models import BatchProcessingResult

    # Build CSV rows
    rows = []
    header = ["NSN", "Status", "Item Name", "RFQ Status", "Supplier Count", "DIBBS Status", "WBParts Status", "Contacts Status", "Error"]
    rows.append(header)

    for nsn_result in batch_result.results:
        row = [
            nsn_result.nsn,
            nsn_result.status.upper(),
            "", "", "0", "", "", "", ""
        ]

        if nsn_result.status == "success" and nsn_result.result:
            result = nsn_result.result
            row[2] = result.item_name or "N/A"
            row[3] = "OPEN" if result.has_open_rfq else "CLOSED"
            row[4] = str(len(result.suppliers))
            row[5] = result.workflow.dibbs_status.upper()
            row[6] = result.workflow.wbparts_status.upper()
            row[7] = result.workflow.firecrawl_status.upper()
        elif nsn_result.status == "error":
            row[8] = nsn_result.error_message or "Unknown error"

        rows.append(row)

    # Generate CSV string
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerows(rows)
    return output.getvalue()


def export_batch_to_json(batch_result) -> str:
    """Export complete batch results to JSON"""
    import json
    from models import BatchProcessingResult

    # Convert to dict
    batch_dict = batch_result.model_dump(by_alias=True, exclude_none=True)

    # Pretty print JSON
    return json.dumps(batch_dict, indent=2, ensure_ascii=False)


def render_detailed_nsn_result(result):
    """Render detailed view for a single NSN result (reusable component)"""
    from models import EnhancedRFQResult

    # Summary metrics
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("NSN", result.nsn)

    with col2:
        st.metric("Item", result.item_name or "N/A")

    with col3:
        status_emoji = "🟢 OPEN" if result.has_open_rfq else "🔴 CLOSED"
        st.metric("RFQ Status", status_emoji)

    with col4:
        st.metric("Suppliers", len(result.suppliers))

    # Workflow status
    col1, col2, col3 = st.columns(3)

    with col1:
        dibbs_icon = "✅" if result.workflow.dibbs_status == "success" else "❌"
        st.markdown(f"{dibbs_icon} DIBBS: {result.workflow.dibbs_status}")

    with col2:
        wbparts_icon = "✅" if result.workflow.wbparts_status == "success" else "❌"
        st.markdown(f"{wbparts_icon} WBParts: {result.workflow.wbparts_status}")

    with col3:
        firecrawl_icons = {
            "success": "✅",
            "partial": "🟡",
            "error": "❌",
            "skipped": "⏭️"
        }
        fc_icon = firecrawl_icons.get(result.workflow.firecrawl_status, "❓")
        st.markdown(f"{fc_icon} Contacts: {result.workflow.firecrawl_status}")

    # Suppliers section
    st.markdown("#### 👥 Suppliers")
    if result.suppliers:
        for supplier in result.suppliers:
            render_supplier_card(supplier)
    else:
        st.info("No suppliers found")

    # Raw data section
    st.markdown("#### 📁 Raw Data")
    col1, col2 = st.columns(2)

    with col1:
        with st.expander("DIBBS Data"):
            if result.raw_data.dibbs:
                st.json(result.raw_data.dibbs.model_dump(by_alias=True, exclude_none=True))
            else:
                st.info("No DIBBS data")

    with col2:
        with st.expander("WBParts Data"):
            if result.raw_data.wbparts:
                st.json(result.raw_data.wbparts.model_dump(by_alias=True, exclude_none=True))
            else:
                st.info("No WBParts data")


def main():
    """Main Streamlit app"""

    # Sidebar
    with st.sidebar:
        st.title("📋 RFQ Automation")
        st.markdown("Multi-source NSN/RFQ scraper with automatic contact discovery")

        st.markdown("---")

        st.markdown("### Data Sources")
        st.markdown("- 🏛️ **DIBBS** - RFQ status, solicitations")
        st.markdown("- 📦 **WBParts** - Manufacturer details")
        st.markdown("- 🔍 **Firecrawl** - Contact discovery")

        st.markdown("---")

        # Configuration status
        st.markdown("### Configuration")
        if config.is_firecrawl_configured():
            st.success("✅ Firecrawl API configured")
        else:
            st.warning("⚠️ Firecrawl API not configured")
            st.caption("Contact discovery will be skipped")

    # Main content
    st.title("📋 RFQ Automation Scraper")

    st.markdown("""
    Scrape RFQ data from DIBBS and WBParts, and automatically discover supplier contact information.
    """)

    # Mode toggle
    st.markdown("### Input Mode")
    processing_mode = st.radio(
        "Select processing mode:",
        options=["Single NSN", "Batch NSNs"],
        horizontal=True,
        help="Single: Process one NSN | Batch: Process multiple NSNs (one per line)"
    )

    st.markdown("---")

    # Initialize variables
    nsn_input = ""
    scrape_button = False
    nsn_textarea = ""
    batch_scrape_button = False

    if processing_mode == "Single NSN":
        # Single NSN mode (existing UI)
        col1, col2 = st.columns([3, 1])

        with col1:
            nsn_input = st.text_input(
                "Enter NSN",
                placeholder="4520-01-261-9675",
                help="Format: XXXX-XX-XXX-XXXX"
            )

        with col2:
            st.markdown("<br>", unsafe_allow_html=True)
            scrape_button = st.button("🔍 Scrape", type="primary", use_container_width=True)

        # Quick examples
        st.markdown("**Quick Examples:**")
        col1, col2, col3 = st.columns(3)

        with col1:
            if st.button("HEATER,VENTILATION", use_container_width=True):
                st.session_state["nsn_to_scrape"] = "4520-01-261-9675"
                st.rerun()

        with col2:
            if st.button("SHACKLE,SPECIAL", use_container_width=True):
                st.session_state["nsn_to_scrape"] = "4030-01-097-6471"
                st.rerun()

        # Check for NSN from session state
        if "nsn_to_scrape" in st.session_state:
            nsn_input = st.session_state.pop("nsn_to_scrape")
            scrape_button = True

    else:
        # Batch NSN mode (new UI)
        nsn_textarea = st.text_area(
            "Enter NSNs (one per line)",
            placeholder="4520-01-261-9675\n4030-01-097-6471\n5340-00-111-2222",
            height=150,
            help="Enter one NSN per line. Empty lines and invalid NSNs will be skipped."
        )

        col1, col2 = st.columns([3, 1])

        with col1:
            nsn_count = len([line.strip() for line in nsn_textarea.split('\n') if line.strip()])
            st.info(f"📋 {nsn_count} NSN(s) entered")

        with col2:
            batch_scrape_button = st.button("🔍 Scrape Batch", type="primary", use_container_width=True)

    # ============== SINGLE NSN PROCESSING ==============
    if processing_mode == "Single NSN" and scrape_button and nsn_input:
        # Validate NSN
        if not validate_nsn(nsn_input):
            st.error("❌ Invalid NSN format. Expected: XXXX-XX-XXX-XXXX")
            return

        nsn = format_nsn_with_dashes(nsn_input)

        # Progress section
        st.markdown("---")
        st.markdown("### Progress")

        progress_bar = st.progress(0)
        status_text = st.empty()

        def update_progress(step: int, message: str):
            progress = step / 3
            progress_bar.progress(progress)
            status_text.markdown(f"**Step {step}/3:** {message}")

        # Run scrape
        try:
            result = asyncio.run(run_scrape(nsn, update_progress))

            progress_bar.progress(1.0)
            status_text.markdown("**✅ Complete!**")

            # Save result
            result_dict = result.model_dump(by_alias=True, exclude_none=True)
            filepath = save_result(nsn, result_dict)

            st.success(f"✅ Results saved to: {filepath}")

            # Results section
            st.markdown("---")
            st.markdown("### 📊 Results")

            # Use reusable component for detailed view
            render_detailed_nsn_result(result)

            # Download button
            st.markdown("---")
            json_str = json.dumps(result_dict, indent=2)
            st.download_button(
                label="📥 Download JSON",
                data=json_str,
                file_name=f"{nsn}.json",
                mime="application/json",
                use_container_width=True
            )

        except Exception as e:
            progress_bar.progress(1.0)
            status_text.markdown("**❌ Error!**")
            st.error(f"An error occurred: {str(e)}")

    # ============== BATCH NSN PROCESSING ==============
    elif processing_mode == "Batch NSNs" and batch_scrape_button and nsn_textarea:
        from models import BatchProcessingResult

        # Parse NSNs from textarea
        nsn_lines = [line.strip() for line in nsn_textarea.split('\n') if line.strip()]

        if not nsn_lines:
            st.error("❌ Please enter at least one NSN")
        else:
            # Progress section
            st.markdown("---")
            st.markdown("### Batch Processing")

            overall_progress = st.progress(0)
            status_text = st.empty()

            # Results container (updates in real-time)
            results_container = st.empty()

            def update_batch_progress(current: int, total: int, message: str):
                progress = current / total if total > 0 else 0
                overall_progress.progress(progress)
                status_text.markdown(f"**Progress: {current}/{total}** - {message}")

            def update_batch_status(nsn_index: int, nsn_result):
                # Show real-time status in results container
                with results_container.container():
                    st.markdown(f"**Current Status:**")
                    # Note: batch_result is updated in the async function
                    pass

            # Run batch scrape
            try:
                batch_result = asyncio.run(
                    run_batch_scrape(nsn_lines, update_batch_progress, update_batch_status)
                )

                overall_progress.progress(1.0)
                status_text.markdown(f"**✅ Batch Complete!** - {batch_result.successful} successful, {batch_result.failed} failed")

                # Clear results container
                results_container.empty()

                # Display batch results
                st.markdown("---")
                st.markdown("### 📊 Batch Results")

                # Summary metrics
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Total NSNs", batch_result.total_nsns)
                with col2:
                    st.metric("Successful", batch_result.successful)
                with col3:
                    st.metric("Failed", batch_result.failed)
                with col4:
                    success_rate = (batch_result.successful / batch_result.total_nsns * 100) if batch_result.total_nsns > 0 else 0
                    st.metric("Success Rate", f"{success_rate:.1f}%")

                # Results table
                st.markdown("#### Summary Table")
                df = render_batch_results_table(batch_result)

                # Export options
                st.markdown("---")
                st.markdown("#### 📥 Export Options")

                col1, col2 = st.columns(2)

                with col1:
                    # CSV export
                    csv_data = export_batch_to_csv(batch_result)
                    st.download_button(
                        label="📊 Download CSV Summary",
                        data=csv_data,
                        file_name=f"batch_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        mime="text/csv",
                        use_container_width=True
                    )

                with col2:
                    # JSON export
                    json_data = export_batch_to_json(batch_result)
                    st.download_button(
                        label="📥 Download Complete JSON",
                        data=json_data,
                        file_name=f"batch_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                        mime="application/json",
                        use_container_width=True
                    )

                # Expandable JSON view
                st.markdown("---")
                st.markdown("#### 🔍 Complete JSON Data")
                with st.expander("View Complete Batch JSON", expanded=False):
                    st.json(batch_result.model_dump(by_alias=True, exclude_none=True))

                # Expandable detailed views
                st.markdown("---")
                st.markdown("#### 📋 Detailed Results")

                for idx, nsn_result in enumerate(batch_result.results, start=1):
                    if nsn_result.status == "success" and nsn_result.result:
                        with st.expander(f"NSN {idx}: {nsn_result.nsn} - {nsn_result.result.item_name or 'N/A'}"):
                            render_detailed_nsn_result(nsn_result.result)
                    elif nsn_result.status == "error":
                        with st.expander(f"NSN {idx}: {nsn_result.nsn} - ❌ ERROR"):
                            st.error(f"Error: {nsn_result.error_message}")

            except Exception as e:
                overall_progress.progress(1.0)
                status_text.markdown("**❌ Batch Error!**")
                st.error(f"An error occurred during batch processing: {str(e)}")

    # Footer
    st.markdown("---")
    st.caption("RFQ Automation Scraper v2.0 | DIBBS + WBParts + Firecrawl")


if __name__ == "__main__":
    main()
