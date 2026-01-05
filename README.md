# RFQ Automation Scraper

Multi-source NSN/RFQ data scraper for government procurement automation.

## Overview

This tool scrapes Request for Quote (RFQ) data from two government/defense sources:

- **DIBBS** (Defense Logistics Agency Internet Bid Board System) - Primary source for OPEN RFQ status
- **WBParts** - Secondary source for manufacturer details and technical specifications

## Features

- Automatic DoD consent banner handling
- Multi-source data combination with unified JSON output
- Batch processing support
- OPEN/CLOSED RFQ status detection
- Manufacturer and CAGE code extraction

## Installation

```bash
npm install
npx playwright install chromium
```

## Usage

### DIBBS Only (Default)
```bash
npx tsx src/index.ts <NSN>
npx tsx src/index.ts 4520-01-261-9675
```

### Combined DIBBS + WBParts
```bash
npx tsx src/index.ts <NSN> --wbparts
npx tsx src/index.ts 4520-01-261-9675 --wbparts
```

### WBParts Only
```bash
npx tsx src/index.ts <NSN> --wbparts-only
```

### Batch Mode
```bash
npx tsx src/index.ts <NSN1>,<NSN2>,<NSN3>
npx tsx src/index.ts 4520-01-261-9675,4030-01-097-6471 --wbparts
```

### Help
```bash
npx tsx src/index.ts --help
```

## Output Format

All output is JSON to stdout. Log messages go to stderr.

### DIBBS-only Output
```json
{
  "success": true,
  "data": {
    "nsn": "4520-01-261-9675",
    "nomenclature": "HEATER,VENTILATION",
    "approvedSources": [
      {
        "cageCode": "74924",
        "partNumber": "210-19082-42",
        "companyName": "INDEECO LLC"
      }
    ],
    "solicitations": [...],
    "hasOpenRFQs": false
  }
}
```

### Combined Output (--wbparts)
```json
{
  "success": true,
  "data": {
    "dibbs": {...},
    "wbparts": {...},
    "hasOpenRFQ": false,
    "primaryCompany": "INDEECO LLC",
    "primaryCageCode": "74924",
    "summary": {
      "nsn": "4520-01-261-9675",
      "companyNames": ["INDEECO LLC", "INDUSTRIAL ENGINEERING..."],
      "cageCodes": ["74924"],
      "partNumbers": [...]
    }
  }
}
```

## Data Sources

| Source | URL | Purpose |
|--------|-----|---------|
| DIBBS | `dibbs.bsm.dla.mil` | OPEN status (source of truth), solicitations |
| WBParts | `wbparts.com` | Manufacturer details, technical specs |

## Project Structure

```
src/
├── index.ts           # CLI entry point
├── types.ts           # TypeScript interfaces
├── dibbs-scraper.ts   # DIBBS scraping logic
└── wbparts-scraper.ts # WBParts scraping logic
```

## Test NSNs

These NSNs are confirmed working for testing:

1. `4520-01-261-9675` - INDEECO LLC (Heater, Ventilation)
2. `4030-01-097-6471` - Shackle, Special

## n8n Integration

Use the Execute Command node:
```
cd /path/to/rfq-automation && npx tsx src/index.ts {{$json.nsn}}
```

## License

MIT
