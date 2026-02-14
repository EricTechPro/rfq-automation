"""
Email Monitor - Streamlit Page

Email thread viewer with conversation stage classification.
Allows manual testing of the classify-thread and draft-reply LLM endpoints.
"""

import asyncio
import json

import streamlit as st

import sys
sys.path.insert(0, str(__file__).rsplit("/", 2)[0])

from config import config
from services.llm import STAGES


# Page configuration
st.set_page_config(
    page_title="Email Monitor - RFQ Automation",
    page_icon="📧",
    layout="wide",
)


def main():
    """Main Email Monitor page"""

    st.title("📧 Email Monitor")
    st.markdown("Classify email threads and generate reply drafts using LLM.")
    st.markdown("---")

    # Check OpenRouter config
    if not config.is_llm_configured():
        st.warning(
            "**OpenRouter not configured.** "
            "Add `OPENROUTER_API_KEY` to your `.env` file to enable LLM features."
        )

    # ==========================================
    # Thread Input
    # ==========================================
    st.markdown("### Email Thread")

    # Initialize session state
    if "email_thread" not in st.session_state:
        st.session_state.email_thread = []
    if "classification" not in st.session_state:
        st.session_state.classification = None
    if "draft" not in st.session_state:
        st.session_state.draft = None

    # Add email to thread
    st.markdown("#### Add Email to Thread")

    col1, col2 = st.columns([1, 4])

    with col1:
        sender = st.selectbox("From", options=["us", "supplier"])

    with col2:
        body = st.text_area(
            "Email Body",
            height=100,
            placeholder="Enter the email body text...",
        )

    col1, col2, col3 = st.columns([1, 1, 2])

    with col1:
        if st.button("Add to Thread", type="primary", use_container_width=True):
            if body.strip():
                st.session_state.email_thread.append({
                    "from": sender,
                    "body": body.strip(),
                })
                st.session_state.classification = None
                st.session_state.draft = None
                st.rerun()
            else:
                st.warning("Please enter email body text.")

    with col2:
        if st.button("Clear Thread", use_container_width=True):
            st.session_state.email_thread = []
            st.session_state.classification = None
            st.session_state.draft = None
            st.rerun()

    # Display current thread
    if st.session_state.email_thread:
        st.markdown("---")
        st.markdown("#### Current Thread")

        for i, msg in enumerate(st.session_state.email_thread):
            sender_label = "Us" if msg["from"] == "us" else "Supplier"
            icon = "📤" if msg["from"] == "us" else "📥"
            st.markdown(f"**{icon} Email {i+1} (from: {sender_label})**")
            st.text(msg["body"][:500])
            st.markdown("---")

    # ==========================================
    # Classification
    # ==========================================
    if st.session_state.email_thread:
        st.markdown("### Classify & Draft")

        col1, col2, col3 = st.columns(3)

        with col1:
            if st.button(
                "Classify Thread",
                type="primary",
                use_container_width=True,
                disabled=not config.is_llm_configured(),
            ):
                with st.spinner("Classifying with LLM..."):
                    try:
                        from services.llm import classify_conversation_stage
                        stage = asyncio.run(classify_conversation_stage(st.session_state.email_thread))
                        st.session_state.classification = stage
                    except Exception as e:
                        st.error(f"Classification failed: {str(e)}")

        with col2:
            # Optional context for drafting
            context_nsn = st.text_input("NSN (optional)", placeholder="5306-00-373-3291")

        with col3:
            context_qty = st.text_input("Quantity (optional)", placeholder="50")

        # Show classification result
        if st.session_state.classification:
            stage = st.session_state.classification
            stage_idx = STAGES.index(stage) if stage in STAGES else -1
            st.success(f"**Stage:** {stage}")

            # Stage progress bar
            if stage_idx >= 0:
                progress = (stage_idx + 1) / len(STAGES)
                st.progress(progress)

            # Draft reply button
            if st.button(
                "Draft Reply",
                type="primary",
                use_container_width=True,
                disabled=not config.is_llm_configured(),
            ):
                with st.spinner("Drafting reply with LLM..."):
                    try:
                        from services.llm import draft_reply
                        context = {}
                        if context_nsn:
                            context["nsn"] = context_nsn
                        if context_qty:
                            context["quantity"] = context_qty

                        reply = asyncio.run(draft_reply(
                            st.session_state.email_thread,
                            stage,
                            context if context else None,
                        ))
                        st.session_state.draft = reply
                    except Exception as e:
                        st.error(f"Draft failed: {str(e)}")

        # Show draft
        if st.session_state.draft:
            st.markdown("### Draft Reply")
            st.text_area(
                "Generated Reply",
                value=st.session_state.draft,
                height=200,
                disabled=True,
            )

            # Copy button hint
            st.caption("Select all text above and copy to use in your email client.")

    # ==========================================
    # Quick Templates
    # ==========================================
    st.markdown("---")
    st.markdown("### Quick Templates")

    templates = {
        "Initial Outreach": [
            {"from": "us", "body": "Hello,\n\nCan you please provide a quote on the following:\n\n- PN: 12345-678\n- QTY: 50\n- Description: BOLT, MACHINE\n\nThank you, and I look forward to your response."}
        ],
        "Quote Received": [
            {"from": "us", "body": "Hello,\n\nCan you please provide a quote for PN 12345-678, QTY 50?"},
            {"from": "supplier", "body": "Hi,\n\nThank you for your inquiry. Here is our quote:\n\n- PN: 12345-678\n- Unit Price: $12.50\n- Qty: 50\n- Total: $625.00\n- Lead Time: 30 days ARO\n\nPlease let me know if you need anything else."},
        ],
        "Substitute Offered": [
            {"from": "us", "body": "Can you provide a quote for PN 12345-678?"},
            {"from": "supplier", "body": "We no longer manufacture that exact part, but we have a direct replacement: PN 12345-679. Same specs, updated revision. Would you like a quote for the substitute?"},
        ],
    }

    cols = st.columns(len(templates))
    for col, (name, thread) in zip(cols, templates.items()):
        with col:
            if st.button(f"Load: {name}", use_container_width=True):
                st.session_state.email_thread = thread
                st.session_state.classification = None
                st.session_state.draft = None
                st.rerun()

    # ==========================================
    # Sidebar
    # ==========================================
    with st.sidebar:
        st.markdown("### 📧 Email Monitor")
        st.markdown("""
        **Workflow:**
        1. **Build thread** - Add emails from us/supplier
        2. **Classify** - LLM determines conversation stage
        3. **Draft reply** - LLM generates contextual response
        4. **Review & send** - Copy draft to email client
        """)

        st.markdown("---")

        st.markdown("### Conversation Stages")
        for stage in STAGES:
            st.markdown(f"- **{stage}**")

        st.markdown("---")

        st.markdown("### Configuration")
        if config.is_llm_configured():
            st.markdown(f"**Model:** `{config.OPENROUTER_MODEL}`")
            st.markdown("**Status:** Connected")
        else:
            st.markdown("**Status:** Not configured")
            st.markdown("Set `OPENROUTER_API_KEY` in `.env`")


if __name__ == "__main__":
    main()
