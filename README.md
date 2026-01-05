# RFQ Automation Scraper (Python/Streamlit)

Python version of the RFQ Automation Scraper with Streamlit web interface.

## Features

- 🔍 **DIBBS Integration** - Scrapes NSN data, suppliers, and RFQ solicitations
- 🛠️ **WBParts Integration** - Additional manufacturer and technical specification data
- 🔥 **Firecrawl Contact Discovery** - AI-powered supplier contact information extraction
- 🎨 **Interactive Streamlit UI** - User-friendly web interface
- 📊 **Real-time Progress** - Visual feedback during scraping operations
- 💾 **JSON Export** - Download results for further processing

## Prerequisites

- Python 3.8+
- Firecrawl API key (get one at [firecrawl.dev](https://firecrawl.dev))

## Installation

1. **Clone or navigate to the project:**
   ```bash
   cd rfq-automation-python
   ```

2. **Install dependencies:**
   ```bash
   pip3 install -r requirements.txt
   ```

3. **Install Playwright browsers:**
   ```bash
   python3 -m playwright install chromium
   ```

4. **Set up environment variables:**
   ```bash
   cp .env.example .env
   ```

   Edit `.env` and add your Firecrawl API key:
   ```
   FIRECRAWL_API_KEY=your_api_key_here
   ```

## Usage

### Streamlit Web Interface

Launch the Streamlit app:

```bash
streamlit run app.py
```

The app will open in your browser at `http://localhost:8501`. Features:

- Enter an NSN (format: XXXX-XX-XXX-XXXX or XXXXXXXXXXXX)
- Click "Search NSN" to start scraping
- View real-time progress through 3 stages:
  1. DIBBS scraping
  2. WBParts scraping
  3. Contact discovery
- Download results as JSON

### Command-Line Test

Run the test script to verify installation:

```bash
python3 test_scraper.py
```

## Project Structure

```
rfq-automation-python/
├── app.py                    # Streamlit web interface
├── config.py                 # Configuration loader
├── models.py                 # Pydantic data models
├── test_scraper.py          # Test script
├── requirements.txt         # Python dependencies
├── .env.example             # Environment variables template
├── scrapers/
│   ├── __init__.py
│   ├── dibbs.py            # DIBBS scraper
│   └── wbparts.py          # WBParts scraper
├── services/
│   ├── __init__.py
│   └── firecrawl.py        # Firecrawl API client
├── utils/
│   ├── __init__.py
│   └── helpers.py          # Utility functions
└── results/                 # JSON output directory
```

## Data Models

### DIBBS Data
- **NSN** - National Stock Number
- **Nomenclature** - Item description
- **Approved Sources** - List of approved suppliers with CAGE codes
- **Solicitations** - Active RFQ solicitations with dates and requirements
- **Open RFQ Status** - Whether there are currently open RFQs

### WBParts Data
- **Item Name** - Part description
- **Manufacturers** - List of manufacturers with CAGE codes
- **Technical Specifications** - Part specifications and characteristics
- **Demand History** - Historical demand data

### Contact Information
- **Email** - Primary contact email
- **Phone** - Primary contact phone
- **Website** - Company website
- **Address** - Physical address
- **Additional Contacts** - List of specific contact persons
- **Confidence** - AI confidence level (high/medium/low)

## API Response Format

```json
{
  "nsn": "4520-01-261-9675",
  "itemName": "HEATER,VENTILATION",
  "hasOpenRFQ": false,
  "suppliers": [
    {
      "cageCode": "19071",
      "companyName": "INDEECO LLC",
      "partNumber": "2619675-1",
      "contact": {
        "email": "contact@example.com",
        "phone": "+1-234-567-8900",
        "website": "https://example.com",
        "confidence": "high"
      }
    }
  ],
  "rawData": {
    "dibbs": { ... },
    "wbparts": { ... }
  },
  "workflow": {
    "dibbsStatus": "success",
    "wbpartsStatus": "success",
    "firecrawlStatus": "success"
  }
}
```

## Configuration

Environment variables (`.env`):

```env
# Firecrawl API Configuration
FIRECRAWL_API_KEY=your_api_key_here
FIRECRAWL_SEARCH_LIMIT=3
```

## Troubleshooting

### Playwright Installation Issues

If browser installation fails:
```bash
python3 -m playwright install --force chromium
```

### Import Errors

Ensure all dependencies are installed:
```bash
pip3 install -r requirements.txt --upgrade
```

### Firecrawl API Errors

- Verify your API key is correct in `.env`
- Check your Firecrawl account credits
- Ensure you have internet connectivity

## Differences from Node.js Version

This Python version maintains feature parity with the Node.js implementation while offering:

- **Streamlit UI** - Interactive web interface (vs. Express API)
- **Pydantic Models** - Strong type validation
- **Python Ecosystem** - Native Python data science integration
- **Async Support** - Modern async/await patterns

Both versions share the same:
- Data sources (DIBBS, WBParts, Firecrawl)
- Data models and structure
- Core scraping logic
- Output format

## License

MIT

## Related Projects

- Node.js version: `../rfq-automation/`
