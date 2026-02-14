# Document Intelligence

## Source
Downloads and extracts text/data from PDF documents (bid packages, solicitations).

## Endpoint

### POST /api/extract-document
Download a PDF, extract text (with OCR fallback), and parse structured bid package info.
- **Output:** `extract_document.json`
- **Parameters:** `{"url": "https://www.dibbs.bsm.dla.mil/rfq/rfqrec.aspx?sn=SPE1C1-26-Q-0117"}`
- **Extracted fields:** eligibility, specs, quantity, delivery, deadlines

## Notes
- DIBBS returned HTTP 503 during this run (site maintenance)
- Requires `pytesseract` and `pdf2image` for OCR of scanned documents
- Text output is capped at 10,000 characters in the API response
- Works with any publicly accessible PDF URL, not just DIBBS
