# RFQ Automation Scraper (Python/Streamlit)

Python version of the RFQ Automation Scraper with Streamlit web interface.

## Features

- 🔍 **DIBBS Integration** - Scrapes NSN data, suppliers, and RFQ solicitations
- 🛠️ **WBParts Integration** - Additional manufacturer and technical specification data
- 🔥 **Firecrawl Contact Discovery** - AI-powered supplier contact information extraction
- 🎨 **Interactive Streamlit UI** - User-friendly web interface
- 📊 **Real-time Progress** - Visual feedback during scraping operations
- 💾 **JSON Export** - Download results for further processing

## Architecture

For comprehensive architecture diagrams and technical documentation, see:

📐 **[Architecture Documentation](docs/architecture-diagram.md)**

This includes:
- Complete workflow diagrams showing behind-the-scenes operations
- Batch processing workflow
- Data model structure and relationships
- Technology stack overview

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

### Option 1: Command Line Interface (CLI) - Recommended for Batch Processing

Process multiple NSNs from a file with **resume capability** and **incremental saves**:

```bash
# Process NSNs from a file (auto-resumes if interrupted)
python3 cli.py --file nsns.txt

# Start fresh (ignore previous progress)
python3 cli.py --file nsns.txt --force

# Custom output file name
python3 cli.py --file nsns.txt --output-name my_results

# Process specific NSNs directly
python3 cli.py --nsns "5306003733291,6685011396216,5315011590157"
```

**Output:** Results are saved to `output/batch_results.csv` and `output/batch_results.json`

**Features:**
- **Resume capability** - Automatically skips already-processed NSNs if interrupted
- **Incremental saves** - Results saved after each NSN (no data loss on interruption)
- **Progress tracking** - Visual progress bar with ETA
- **Rate limiting** - Automatic delays to avoid overwhelming servers

### Option 2: Streamlit Web Interface

Launch the interactive web app:

```bash
streamlit run app.py
```

Or use the unified entry point:

```bash
python3 main.py streamlit
```

The app opens at `http://localhost:8501` with:
- Single NSN or batch processing modes
- Real-time progress visualization
- CSV and JSON export options

### Option 3: REST API

Start the FastAPI server for programmatic access:

```bash
python3 main.py api
```

Or directly:

```bash
uvicorn api:app --host 0.0.0.0 --port 8000
```

**Endpoints:**
- `GET /health` - Health check
- `POST /api/batch` - Process batch of NSNs

**Example:**
```bash
curl -X POST http://localhost:8000/api/batch \
  -H "Content-Type: application/json" \
  -d '{"nsns": ["5306003733291", "6685011396216"]}'
```

API docs available at `http://localhost:8000/docs`

## Project Structure

```
rfq-automation/
├── app.py                    # Streamlit web interface
├── api.py                    # FastAPI REST API
├── cli.py                    # Command line interface
├── core.py                   # Shared business logic
├── main.py                   # Unified entry point
├── config.py                 # Configuration loader (supports .env + Streamlit secrets)
├── models.py                 # Pydantic data models
├── requirements.txt          # Python dependencies
├── .env.example              # Environment variables template
├── nsns.txt                  # Sample NSN list for batch processing
├── .streamlit/
│   ├── config.toml           # Streamlit configuration
│   └── secrets.toml.example  # Streamlit Cloud secrets template
├── scrapers/
│   ├── __init__.py
│   ├── dibbs.py              # DIBBS scraper (RFQ status detection)
│   └── wbparts.py            # WBParts scraper
├── services/
│   ├── __init__.py
│   └── firecrawl.py          # Firecrawl API client
├── utils/
│   ├── __init__.py
│   └── helpers.py            # Utility functions
├── output/                   # CSV/JSON output directory
└── docs/
    └── architecture-diagram.md  # Technical documentation
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
