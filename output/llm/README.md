# LLM-Powered Endpoints (OpenRouter)

## Source
These endpoints use OpenRouter LLM for text analysis. No web scraping involved.

## Endpoints

### POST /api/classify-thread
Classifies an email thread into a procurement stage.
- **Output:** `classify_thread.json`
- **Stages:** Outreach Sent, Quote Received, Substitute y/n, Send, Not Yet
- **Sample result:** "Quote Received" (correctly identified supplier pricing response)

### POST /api/extract-quote
Extracts structured quote data (price, quantity, lead time) from email/document text.
- **Output:** `extract_quote.json`
- **Extracted fields:** partNumber, unitPrice, totalPrice, quantity, leadTime, currency, notes

### POST /api/draft-reply
Drafts a context-aware reply for a procurement email thread.
- **Output:** `draft_reply.json`
- **Auto-classifies stage if not provided, then generates appropriate reply**

## Notes
- Requires `OPENROUTER_API_KEY` env var (optionally `OPENROUTER_MODEL` to override default)
- No verification against external websites needed (LLM-generated output)
- Quality verification: read the sample inputs and check if the outputs are reasonable
