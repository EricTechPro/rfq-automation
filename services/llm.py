"""
LLM Service (OpenRouter)

OpenRouter client for email classification, reply drafting, and quote extraction.
"""

import json
from typing import Optional

from openai import AsyncOpenAI

import sys
sys.path.insert(0, str(__file__).rsplit("/", 2)[0])

from config import config
from utils.logging import get_logger

logger = get_logger(__name__)

# Conversation stages from the Feb 2 meeting + email workflow diagram
STAGES = [
    "Outreach Sent",    # Initial email sent, waiting for response
    "Quote Received",   # Supplier sent a quote (PDF/dollar figures)
    "Substitute y/n",   # Supplier offered substitute part
    "Send",             # Ready for next email
    "Not Yet",          # Paused for manual review
]


async def _call_llm(
    messages: list,
    max_tokens: int = 1024,
    temperature: float = 0.3,
) -> str:
    """
    Call OpenRouter LLM (async, non-blocking).

    Args:
        messages: List of message dicts with role/content
        max_tokens: Max response tokens
        temperature: Sampling temperature

    Returns:
        Response text content

    Raises:
        RuntimeError if API call fails
    """
    api_key = config.OPENROUTER_API_KEY
    if not api_key:
        raise RuntimeError("OpenRouter not configured (OPENROUTER_API_KEY)")

    client = AsyncOpenAI(
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
    )

    try:
        response = await client.chat.completions.create(
            model=config.OPENROUTER_MODEL,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
    except Exception:
        logger.error("OpenRouter API call failed (model=%s)", config.OPENROUTER_MODEL, exc_info=True)
        raise

    choice = response.choices[0] if response.choices else None
    if not choice:
        raise RuntimeError(f"No choices in OpenRouter response: {response}")

    return choice.message.content


async def classify_conversation_stage(thread: list) -> str:
    """
    Classify the current stage of an email conversation thread.

    Args:
        thread: List of email dicts with 'from' and 'body' keys.
                'from' should be 'us' or 'supplier'.

    Returns:
        One of: "Outreach Sent", "Quote Received", "Substitute y/n", "Send", "Not Yet"
    """
    logger.info("classify_conversation_stage: %d messages in thread", len(thread))
    thread_text = _format_thread(thread)

    messages = [
        {
            "role": "system",
            "content": (
                "You are an email classification assistant for a government parts procurement team. "
                "Classify the email conversation into exactly one of these stages:\n\n"
                "- Outreach Sent: We sent initial outreach, waiting for supplier response\n"
                "- Quote Received: Supplier has provided a price quote (mentions dollar amounts, pricing, or attached quote)\n"
                "- Substitute y/n: Supplier offered a substitute/alternative part\n"
                "- Send: Ready to send the next email (conversation is progressing normally)\n"
                "- Not Yet: Needs manual review (unclear, out of office, irrelevant, or complex situation)\n\n"
                "Respond with ONLY the stage name, nothing else."
            ),
        },
        {
            "role": "user",
            "content": f"Classify this email thread:\n\n{thread_text}",
        },
    ]

    result = await _call_llm(messages, max_tokens=50, temperature=0.1)
    result = result.strip().strip('"').strip("'")

    # Fuzzy match to valid stages
    for stage in STAGES:
        if stage.lower() in result.lower():
            return stage

    return "Not Yet"


async def draft_reply(
    thread: list,
    stage: str,
    context: Optional[dict] = None,
) -> str:
    """
    Draft a context-aware reply email.

    Args:
        thread: Email thread (list of dicts with 'from' and 'body')
        stage: Current conversation stage
        context: Optional context dict with keys like 'nsn', 'partNumber', 'quantity', etc.

    Returns:
        Draft reply email text
    """
    logger.info("draft_reply: stage=%s, %d messages in thread", stage, len(thread))
    thread_text = _format_thread(thread)
    context_text = ""
    if context:
        context_text = "\n".join(f"- {k}: {v}" for k, v in context.items() if v)

    messages = [
        {
            "role": "system",
            "content": (
                "You are an email drafting assistant for a government parts procurement team. "
                "Draft a professional, concise reply email based on the conversation thread and its current stage. "
                "Keep the tone businesslike but friendly. Do not include a subject line — just the email body. "
                "If the stage is 'Quote Received', thank them for the quote and confirm next steps. "
                "If 'Substitute y/n', ask clarifying questions about the substitute part. "
                "If 'Send' or 'Outreach Sent', draft an appropriate follow-up."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Stage: {stage}\n\n"
                + (f"Context:\n{context_text}\n\n" if context_text else "")
                + f"Thread:\n{thread_text}\n\n"
                "Draft a reply:"
            ),
        },
    ]

    return await _call_llm(messages, max_tokens=512, temperature=0.4)


async def extract_quote_data(text: str) -> dict:
    """
    Extract structured quote data from email or document text.

    Args:
        text: Raw text containing quote information

    Returns:
        Dict with extracted fields: unitPrice, totalPrice, leadTime, partNumber, etc.
    """
    logger.info("extract_quote_data: %d chars of input text", len(text))
    messages = [
        {
            "role": "system",
            "content": (
                "You are a data extraction assistant. Extract structured quote information from the text. "
                "Return a JSON object with these fields (use null if not found):\n"
                "- partNumber: Part number being quoted\n"
                "- unitPrice: Price per unit (number)\n"
                "- totalPrice: Total price (number)\n"
                "- quantity: Quantity quoted\n"
                "- leadTime: Delivery lead time\n"
                "- currency: Currency (default USD)\n"
                "- notes: Any important notes or conditions\n\n"
                "Return ONLY valid JSON, no other text."
            ),
        },
        {
            "role": "user",
            "content": f"Extract quote data from:\n\n{text[:3000]}",
        },
    ]

    result = await _call_llm(messages, max_tokens=256, temperature=0.1)

    # Parse JSON from response
    try:
        # Handle markdown code blocks
        if "```" in result:
            result = result.split("```")[1]
            if result.startswith("json"):
                result = result[4:]
        return json.loads(result.strip())
    except (json.JSONDecodeError, IndexError) as e:
        logger.warning("extract_quote_data: JSON parse failed: %s (raw: %.200s)", e, result)
        return {"raw": result, "error": "Failed to parse structured data"}


def _format_thread(thread: list) -> str:
    """Format email thread for LLM context."""
    lines = []
    for i, msg in enumerate(thread, 1):
        sender = msg.get("from", "unknown")
        body = msg.get("body", "")
        lines.append(f"--- Email {i} (from: {sender}) ---\n{body}\n")
    return "\n".join(lines)
