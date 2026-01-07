# RFQ Automation Scraper

Automated NSN/RFQ scraper for DIBBS and WBParts with supplier contact discovery.

## Quick Start (5 minutes)

### Step 1: Check Prerequisites

Open your terminal and check if you have Python installed:

```bash
python3 --version
```

**If you see "command not found":**
- **Mac:** Install from [python.org](https://www.python.org/downloads/) or run `brew install python3`
- **Windows:** Download from [python.org](https://www.python.org/downloads/) and check "Add to PATH" during install
- **Linux:** Run `sudo apt install python3 python3-pip`

### Step 2: Download the Code

```bash
# Clone the repository
git clone https://github.com/EricTechPro/rfq-automation.git

# Navigate into the folder
cd rfq-automation
```

### Step 3: Install Dependencies

```bash
# Install Python packages
pip3 install -r requirements.txt

# Install browser for web scraping (required)
python3 -m playwright install chromium
```

### Step 4: Configure API Key

```bash
# Copy the example config
cp .env.example .env
```

Open `.env` in any text editor and add your Firecrawl API key:
```
FIRECRAWL_API_KEY=fc-your-api-key-here
```

### Step 5: Run It!

```bash
# Process all NSNs from nsns.txt
python3 cli.py --file nsns.txt --force
```

**That's it!** Results will be saved to:
- `output/batch_results.csv` - Spreadsheet format
- `output/batch_results.json` - Full data with all details

---

## Features

- 🔍 **DIBBS Integration** - Scrapes NSN data, suppliers, and RFQ solicitations
- 🛠️ **WBParts Integration** - Additional manufacturer and technical specification data
- 🔥 **Firecrawl Contact Discovery** - AI-powered supplier contact information extraction
- 📊 **Real-time Progress** - Visual progress bar with ETA
- 💾 **CSV & JSON Export** - Download results in multiple formats
- 🔄 **Resume Capability** - Automatically continues if interrupted
- ✅ **Accurate Open/Closed Detection** - Reads actual RFQ status from DIBBS

## Important Note: Cloud Deployment

> **Streamlit Cloud Limitation:** The hosted demo at `rfq-automation-erictech.streamlit.app` cannot perform actual scraping because Streamlit Cloud doesn't support browser automation (Playwright). **For full functionality, run the tool locally** using the Quick Start instructions above.

## Architecture

For comprehensive architecture diagrams and technical documentation, see:

📐 **[Architecture Documentation](docs/architecture-diagram.md)**

## Prerequisites

- Python 3.8+ (check with `python3 --version`)
- Git (check with `git --version`)
- Firecrawl API key (get one at [firecrawl.dev](https://firecrawl.dev))

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
