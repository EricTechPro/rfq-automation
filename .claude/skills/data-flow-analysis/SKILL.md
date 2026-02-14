---
name: data-flow-analysis
description: Analyze scraping pipeline flows, detect edge cases, identify race conditions, and design state machines for async operations. Use when designing new features, reviewing implementations, or debugging complex flows in the NSN scraping pipeline.
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
---

# Data Flow Analysis Skill

Comprehensive analysis patterns for scraping pipeline flows, edge cases, race conditions, and state machines in the RFQ Automation system.

## When to Use This Skill

- Designing new scraping features or API endpoints
- Reviewing existing pipeline implementations
- Debugging unexpected scraper behavior
- Identifying edge cases before implementation
- Designing async operation state machines
- Analyzing concurrent scraper safety
- Planning batch processing improvements

## Pipeline Flow Documentation Pattern

### Template Structure

```markdown
# Pipeline Flow: [Feature Name]

## Overview
- **Goal**: What the pipeline stage accomplishes
- **Entry Points**: How data enters this stage (CLI args, API request, batch file)
- **Success Criteria**: What constitutes successful completion
- **Error Criteria**: What constitutes pipeline failure

## Data Sources
- Primary: DIBBS (Defense Logistics Agency Internet Bid Board System)
- Secondary: WBParts (commercial parts database)
- Enrichment: Firecrawl API (contact discovery)

## Prerequisites
- [ ] FIRECRAWL_API_KEY configured
- [ ] Playwright Chromium installed
- [ ] Network access to DIBBS/WBParts
- [ ] NSN input validated (13 digits)

## Main Flow (Happy Path)
1. NSN input → Validation → Formatted NSN
2. Parallel scrape: DIBBS + WBParts → Raw supplier data
3. Merge results → Deduplicated supplier list
4. Sequential contact discovery → Firecrawl enrichment (rate-limited)
5. Build EnhancedRFQResult → Confidence scoring
6. Export → CSV/JSON/API response

## Alternative Flows
- A1: NSN found in DIBBS but not WBParts → Use DIBBS data only
- A2: No suppliers found → Return result with empty suppliers list
- A3: Firecrawl rate limited → Queue and retry with backoff
- A4: Batch mode → Process multiple NSNs with progress tracking

## Exception Flows
- E1: DIBBS consent banner fails → Retry banner click, then fail scrape
- E2: Playwright timeout → Return partial results, mark as incomplete
- E3: Firecrawl API key invalid → Skip contact discovery, return scrape-only results
- E4: Malformed NSN → Reject with validation error before scraping
- E5: Network disconnection mid-scrape → Close browser, return error for NSN

## Edge Cases
- EC1: NSN with no DIBBS listing → WBParts-only results
- EC2: Supplier with no web presence → Contact confidence LOW (filtered by Phase 2 API)
- EC3: Duplicate suppliers from DIBBS + WBParts → Deduplicate by company name
- EC4: Very long supplier list (50+) → Firecrawl takes minutes, show progress
- EC5: NSN format with/without dashes → Normalize before scraping

## State Diagram
input → validating → scraping_dibbs + scraping_wbparts → merging → discovering_contacts → scoring → complete
                                                                                              ↘ failed (at any point) → retry possible

## Data Transformations
NSN string → Formatted NSN → [DIBBS data, WBParts data] → Merged suppliers → Enriched contacts → EnhancedRFQResult → Export format

## Race Condition Analysis
- [Concurrent browser instances competing for system resources]
- [Batch processing overlap when same NSN appears twice]

## Performance Considerations
- Playwright browser launch: ~2-5 seconds per instance
- DIBBS scrape: ~5-15 seconds (consent banner + page load)
- WBParts scrape: ~3-10 seconds
- Firecrawl per supplier: ~2-5 seconds (rate limited)
- Full NSN pipeline: ~30-120 seconds depending on supplier count
```

## Edge Case Detection Framework

### Systematic Edge Case Categories for Web Scraping

```python
# Conceptual framework for edge case analysis

EDGE_CASE_CATEGORIES = [
    {
        "name": "Input Validation",
        "checks": [
            {
                "id": "EC-INP-001",
                "description": "Empty NSN input",
                "input_type": "user",
                "severity": "high",
                "test_scenario": "Submit empty string or whitespace as NSN",
                "expected_behavior": "Return validation error with format hint"
            },
            {
                "id": "EC-INP-002",
                "description": "Invalid NSN format",
                "input_type": "user",
                "severity": "high",
                "test_scenario": "Submit NSN with wrong digit count or letters",
                "expected_behavior": "Reject with specific format error (must be 13 digits)"
            },
            {
                "id": "EC-INP-003",
                "description": "NSN with dashes vs without",
                "input_type": "user",
                "severity": "medium",
                "test_scenario": "Submit '5306-00-373-3291' vs '5306003733291'",
                "expected_behavior": "Accept both formats, normalize internally"
            },
            {
                "id": "EC-INP-004",
                "description": "Duplicate NSNs in batch",
                "input_type": "user",
                "severity": "medium",
                "test_scenario": "Submit batch file with same NSN twice",
                "expected_behavior": "Deduplicate, scrape once, report once"
            },
            {
                "id": "EC-INP-005",
                "description": "Batch file with mixed valid/invalid NSNs",
                "input_type": "user",
                "severity": "medium",
                "test_scenario": "File with 10 NSNs, 3 invalid",
                "expected_behavior": "Process valid ones, report invalid ones separately"
            }
        ]
    },
    {
        "name": "Scraper Reliability",
        "checks": [
            {
                "id": "EC-SCR-001",
                "description": "DIBBS consent banner not appearing",
                "input_type": "system",
                "severity": "critical",
                "test_scenario": "DIBBS page loads without DoD consent banner",
                "expected_behavior": "Detect absence, proceed to scrape (banner may have been accepted)"
            },
            {
                "id": "EC-SCR-002",
                "description": "DIBBS page structure changed",
                "input_type": "external",
                "severity": "critical",
                "test_scenario": "DIBBS updates their HTML structure",
                "expected_behavior": "Scraper returns empty/error, logged for investigation"
            },
            {
                "id": "EC-SCR-003",
                "description": "WBParts returns no results for valid NSN",
                "input_type": "external",
                "severity": "medium",
                "test_scenario": "NSN exists in DIBBS but not WBParts",
                "expected_behavior": "Return DIBBS-only results, no error"
            },
            {
                "id": "EC-SCR-004",
                "description": "Playwright browser crash mid-scrape",
                "input_type": "system",
                "severity": "high",
                "test_scenario": "Chromium process dies during page.goto()",
                "expected_behavior": "Catch error, clean up resources, return error for NSN"
            },
            {
                "id": "EC-SCR-005",
                "description": "Page load timeout",
                "input_type": "system",
                "severity": "high",
                "test_scenario": "DIBBS takes >30 seconds to respond",
                "expected_behavior": "Timeout gracefully, retry once, then fail NSN"
            },
            {
                "id": "EC-SCR-006",
                "description": "DIBBS pagination with many pages",
                "input_type": "external",
                "severity": "medium",
                "test_scenario": "Date-based search returns 50+ pages of results",
                "expected_behavior": "Paginate with reasonable limit, report if truncated"
            }
        ]
    },
    {
        "name": "API & Rate Limiting",
        "checks": [
            {
                "id": "EC-API-001",
                "description": "Firecrawl API rate limit hit",
                "input_type": "external",
                "severity": "high",
                "test_scenario": "Batch of 50 NSNs with 200 suppliers total",
                "expected_behavior": "Respect rate limit, queue requests, backoff"
            },
            {
                "id": "EC-API-002",
                "description": "Firecrawl API key expired/invalid",
                "input_type": "system",
                "severity": "critical",
                "test_scenario": "API returns 401/403",
                "expected_behavior": "Skip contact discovery, return scrape-only results with warning"
            },
            {
                "id": "EC-API-003",
                "description": "Firecrawl returns empty results for known company",
                "input_type": "external",
                "severity": "medium",
                "test_scenario": "Well-known supplier returns no contact info",
                "expected_behavior": "Set confidence LOW, include in results"
            },
            {
                "id": "EC-API-004",
                "description": "Firecrawl service down",
                "input_type": "external",
                "severity": "high",
                "test_scenario": "Firecrawl returns 500/503 for all requests",
                "expected_behavior": "Retry with backoff, then skip contact discovery entirely"
            }
        ]
    },
    {
        "name": "Batch Processing",
        "checks": [
            {
                "id": "EC-BAT-001",
                "description": "Resume after interruption",
                "input_type": "user",
                "severity": "high",
                "test_scenario": "Process 100 NSNs, crash at #50, restart",
                "expected_behavior": "Resume from #50 using progress file (cli.py --file without --force)"
            },
            {
                "id": "EC-BAT-002",
                "description": "Very large batch (1000+ NSNs)",
                "input_type": "user",
                "severity": "medium",
                "test_scenario": "Submit file with 1000 NSNs",
                "expected_behavior": "Process with progress bar, incremental CSV saves"
            },
            {
                "id": "EC-BAT-003",
                "description": "Concurrent batch requests via API",
                "input_type": "user",
                "severity": "high",
                "test_scenario": "Two API clients submit batch requests simultaneously",
                "expected_behavior": "Handle independently, no shared state corruption"
            },
            {
                "id": "EC-BAT-004",
                "description": "Output file write failure",
                "input_type": "system",
                "severity": "high",
                "test_scenario": "Disk full or permission denied on CSV write",
                "expected_behavior": "Catch error, keep results in memory, report write failure"
            }
        ]
    },
    {
        "name": "Data Integrity",
        "checks": [
            {
                "id": "EC-DAT-001",
                "description": "Supplier name mismatch between DIBBS and WBParts",
                "input_type": "external",
                "severity": "medium",
                "test_scenario": "Same company listed as 'ABC Corp' and 'ABC Corporation'",
                "expected_behavior": "Fuzzy match or treat as separate suppliers"
            },
            {
                "id": "EC-DAT-002",
                "description": "Contact info conflicts (different phones for same company)",
                "input_type": "external",
                "severity": "low",
                "test_scenario": "Firecrawl returns different phone than DIBBS listing",
                "expected_behavior": "Include both, let user decide"
            },
            {
                "id": "EC-DAT-003",
                "description": "Pydantic model validation failure on scraped data",
                "input_type": "system",
                "severity": "high",
                "test_scenario": "Scraped data doesn't fit expected model fields",
                "expected_behavior": "Log validation error, skip malformed entry, continue"
            }
        ]
    }
]
```

## State Machine Design Pattern

### NSN Processing Pipeline State Machine

```python
# Conceptual state machine for NSN processing

from enum import Enum
from typing import Optional
from dataclasses import dataclass

class NSNState(Enum):
    PENDING = "pending"
    VALIDATING = "validating"
    SCRAPING_DIBBS = "scraping_dibbs"
    SCRAPING_WBPARTS = "scraping_wbparts"
    SCRAPING_PARALLEL = "scraping_parallel"  # DIBBS + WBParts concurrent
    MERGING_RESULTS = "merging_results"
    DISCOVERING_CONTACTS = "discovering_contacts"
    SCORING = "scoring"
    COMPLETE = "complete"
    FAILED = "failed"
    SKIPPED = "skipped"  # Already processed (resume mode)

class NSNEvent(Enum):
    START = "start"
    VALIDATION_PASSED = "validation_passed"
    VALIDATION_FAILED = "validation_failed"
    DIBBS_COMPLETE = "dibbs_complete"
    WBPARTS_COMPLETE = "wbparts_complete"
    SCRAPE_FAILED = "scrape_failed"
    MERGE_COMPLETE = "merge_complete"
    CONTACT_FOUND = "contact_found"
    CONTACT_DISCOVERY_COMPLETE = "contact_discovery_complete"
    SCORING_COMPLETE = "scoring_complete"
    ERROR = "error"
    RETRY = "retry"

@dataclass
class NSNContext:
    nsn: str
    formatted_nsn: Optional[str] = None
    dibbs_data: Optional[dict] = None
    wbparts_data: Optional[dict] = None
    merged_suppliers: list = None
    contacts: list = None
    result: Optional[dict] = None
    error: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 2

# State transitions
TRANSITIONS = {
    NSNState.PENDING: {
        NSNEvent.START: NSNState.VALIDATING,
    },
    NSNState.VALIDATING: {
        NSNEvent.VALIDATION_PASSED: NSNState.SCRAPING_PARALLEL,
        NSNEvent.VALIDATION_FAILED: NSNState.FAILED,
    },
    NSNState.SCRAPING_PARALLEL: {
        NSNEvent.DIBBS_COMPLETE: NSNState.SCRAPING_PARALLEL,  # Wait for both
        NSNEvent.WBPARTS_COMPLETE: NSNState.SCRAPING_PARALLEL,  # Wait for both
        NSNEvent.MERGE_COMPLETE: NSNState.MERGING_RESULTS,
        NSNEvent.SCRAPE_FAILED: NSNState.FAILED,  # If both fail
    },
    NSNState.MERGING_RESULTS: {
        NSNEvent.MERGE_COMPLETE: NSNState.DISCOVERING_CONTACTS,
    },
    NSNState.DISCOVERING_CONTACTS: {
        NSNEvent.CONTACT_FOUND: NSNState.DISCOVERING_CONTACTS,  # Per supplier
        NSNEvent.CONTACT_DISCOVERY_COMPLETE: NSNState.SCORING,
        NSNEvent.ERROR: NSNState.SCORING,  # Proceed without contacts
    },
    NSNState.SCORING: {
        NSNEvent.SCORING_COMPLETE: NSNState.COMPLETE,
    },
    NSNState.FAILED: {
        NSNEvent.RETRY: NSNState.VALIDATING,  # If retries remaining
    },
}
```

## Race Condition Analysis Pattern

### Common Race Conditions in RFQ Automation

```python
# Analysis document for race conditions

RACE_CONDITIONS = [
    {
        "id": "RC-001",
        "name": "Concurrent Browser Resource Exhaustion",
        "scenario": "Batch processing launches too many Playwright browsers simultaneously",
        "affected_operations": ["scrape_dibbs()", "scrape_wbparts()", "asyncio.gather()"],
        "prevention": "Semaphore to limit concurrent browser instances",
        "implementation": """
            import asyncio

            # Limit concurrent browser instances
            browser_semaphore = asyncio.Semaphore(3)  # Max 3 browsers at once

            async def scrape_with_limit(scrape_fn, *args):
                async with browser_semaphore:
                    return await scrape_fn(*args)

            # In batch processing:
            tasks = [scrape_with_limit(scrape_nsn, nsn) for nsn in nsns]
            results = await asyncio.gather(*tasks, return_exceptions=True)
        """
    },
    {
        "id": "RC-002",
        "name": "Duplicate NSN Processing in Batch",
        "scenario": "Same NSN appears twice in batch file, gets scraped concurrently",
        "affected_operations": ["scrape_batch()", "scrape_nsn()"],
        "prevention": "Deduplicate NSN list before processing, cache results",
        "implementation": """
            # Deduplicate before processing
            unique_nsns = list(dict.fromkeys(nsns))  # Preserves order

            # Or use a result cache
            results_cache = {}

            async def scrape_nsn_cached(nsn):
                if nsn in results_cache:
                    return results_cache[nsn]
                result = await scrape_nsn(nsn)
                results_cache[nsn] = result
                return result
        """
    },
    {
        "id": "RC-003",
        "name": "Progress File Write Conflict",
        "scenario": "CLI resume mode reads progress file while batch processor is writing to it",
        "affected_operations": ["cli.py save_progress()", "cli.py load_progress()"],
        "prevention": "Atomic file writes (write to temp, then rename)",
        "implementation": """
            import tempfile
            import os

            def save_progress_atomic(progress_data, filepath):
                # Write to temp file in same directory
                dir_name = os.path.dirname(filepath)
                with tempfile.NamedTemporaryFile(
                    mode='w', dir=dir_name, delete=False, suffix='.tmp'
                ) as tmp:
                    json.dump(progress_data, tmp)
                    tmp_path = tmp.name
                # Atomic rename
                os.replace(tmp_path, filepath)
        """
    },
    {
        "id": "RC-004",
        "name": "Firecrawl Rate Limit Window Overlap",
        "scenario": "Multiple API endpoints trigger Firecrawl calls simultaneously, exceeding rate limit",
        "affected_operations": ["search_company()", "extract_contacts()"],
        "prevention": "Global rate limiter shared across all Firecrawl callers",
        "implementation": """
            import asyncio
            import time

            class RateLimiter:
                def __init__(self, calls_per_minute=20):
                    self.calls_per_minute = calls_per_minute
                    self.interval = 60.0 / calls_per_minute
                    self.last_call = 0
                    self._lock = asyncio.Lock()

                async def acquire(self):
                    async with self._lock:
                        now = time.monotonic()
                        wait_time = self.interval - (now - self.last_call)
                        if wait_time > 0:
                            await asyncio.sleep(wait_time)
                        self.last_call = time.monotonic()

            # Global instance
            firecrawl_limiter = RateLimiter(calls_per_minute=20)

            async def search_company(company_name):
                await firecrawl_limiter.acquire()
                # ... firecrawl API call
        """
    }
]
```

## Flow Analysis Checklist

Use this checklist when analyzing any pipeline flow:

```markdown
## Flow Analysis: [Feature Name]

### Input Validation
- [ ] NSN format validated (13 digits, with/without dashes)
- [ ] Batch file format validated (one NSN per line)
- [ ] API request body validated (Pydantic models)
- [ ] Error messages include expected format

### Pipeline State Management
- [ ] Clear initial state defined for each NSN
- [ ] All state transitions documented
- [ ] Failed states allow retry
- [ ] Progress persisted for resume capability (CLI)

### Error Handling
- [ ] Playwright timeouts handled (browser launch, page load, element wait)
- [ ] Network errors handled (DNS, connection refused, SSL)
- [ ] API errors handled (401, 403, 429, 500)
- [ ] Partial results returned when possible

### Resource Management
- [ ] Browsers closed in all code paths (including exceptions)
- [ ] Concurrent browser count limited
- [ ] Firecrawl rate limits respected
- [ ] Memory usage bounded for large batches

### Data Quality
- [ ] Supplier deduplication across sources
- [ ] Contact confidence scoring correct (HIGH/MEDIUM/LOW)
- [ ] Pydantic model validation at stage boundaries
- [ ] camelCase aliases used for JSON output

### Batch Processing
- [ ] Progress tracking with progress bar (CLI)
- [ ] Incremental result saving (don't lose completed results on crash)
- [ ] Resume capability tested
- [ ] Duplicate NSN handling

### API Behavior
- [ ] Phase 2 endpoints require X-API-Key when RFQ_API_KEY is set
- [ ] LOW confidence contacts filtered from Phase 2 responses
- [ ] Date-based scraping pagination works correctly
- [ ] Response format matches Pydantic model (by_alias=True)
```

## Example: NSN Batch Processing Flow Analysis

```markdown
# Pipeline Flow: Batch NSN Processing (CLI)

## Overview
- **Goal**: Process a file of NSNs, scraping DIBBS/WBParts and discovering contacts for each
- **Entry Points**: `python3 cli.py --file nsns.txt [--force]`
- **Success Criteria**: All NSNs processed, results exported to CSV + JSON
- **Error Criteria**: Unrecoverable crash losing all progress

## Main Flow (Happy Path)
1. Read NSN file → Validate each NSN → Build processing queue
2. Check for existing progress file (unless --force) → Resume or start fresh
3. For each NSN:
   a. Scrape DIBBS + WBParts in parallel → Merge supplier data
   b. Discover contacts via Firecrawl (sequential, rate-limited) → Score confidence
   c. Save incremental progress → Update progress bar
4. Export final results → CSV + JSON files

## Alternative Flows
- A1: --force flag → Skip progress check, start from scratch
- A2: --nsns flag → Process inline NSN list instead of file
- A3: NSN already in progress file → Skip (unless --force)

## Exception Flows
- E1: Invalid NSN in file → Log warning, skip to next NSN
- E2: All scrapers fail for one NSN → Mark failed, continue batch
- E3: Firecrawl exhausts rate limit → Wait and retry, don't skip
- E4: Disk full on incremental save → Warn, keep results in memory
- E5: Ctrl+C interruption → Save current progress, exit cleanly
- E6: Network drops for extended period → Retry loop with backoff, eventually fail

## Edge Cases
- EC1: Empty NSN file → Show error, exit immediately
- EC2: Single NSN in batch → Process normally, same output format
- EC3: 1000+ NSNs → Memory management, ensure incremental saves
- EC4: Same NSN appears twice in file → Process once, report once
- EC5: Resume with modified NSN file → Process only new/remaining NSNs
- EC6: Progress file corrupted → Warn, offer to start fresh

## State Diagram
reading_file → validating → processing_batch → [per NSN: scraping → discovering → scoring] → exporting → complete
                                                                              ↘ failed NSN → skip, continue batch

## Race Conditions
- RC1: Multiple CLI processes on same file → File lock on progress file
- RC2: Browser resource exhaustion → Semaphore for concurrent instances
- RC3: Incremental save during Ctrl+C → Signal handler for clean shutdown

## Performance Considerations
- Browser launch overhead: ~2-5s per scraper instance (2 per NSN)
- Firecrawl per supplier: ~2-5s (rate limited, sequential)
- 10-NSN batch: ~5-15 minutes depending on supplier count
- 100-NSN batch: ~1-3 hours
- Bottleneck: Firecrawl rate limiting (not scraping)
```
