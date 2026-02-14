# RFQ Automation — Architecture Overview

Visual guide to the system's components, data flows, and project timeline.

## 1. System Overview

All components and how they connect — n8n orchestrates, FastAPI does the work, Google Sheets stores the data.

```mermaid
graph TD
    n8n["n8n<br/>(Orchestration)"]
    api["FastAPI<br/>(Railway)"]
    sheets["Google Sheets<br/>(Data Store)"]
    email["Email Inbox<br/>(IMAP / SMTP)"]

    sam["SAM.gov"]
    canada["Canada Buys"]
    alberta["Alberta Purchasing"]
    dibbs["DIBBS (DLA)"]

    firecrawl["Firecrawl API<br/>(Contact Discovery)"]
    llm["OpenRouter LLM<br/>(Gemini Flash)"]
    ocr["Document Pipeline<br/>(PDF + OCR)"]

    n8n -- "cron triggers" --> api
    api -- "Playwright" --> sam
    api -- "CSV feed" --> canada
    api -- "Playwright" --> alberta
    api -. "blocked by .mil IP filter" .-> dibbs

    api --> firecrawl
    api --> ocr
    api --> llm

    n8n -- "read/write rows" --> sheets
    n8n -- "poll / send" --> email
    email -- "replies" --> n8n

    classDef blocked stroke-dasharray:5 5,stroke:#e74c3c
    class dibbs blocked
```

## 2. Daily Scraping Pipeline

Four government sources feed into a single normalized Google Sheet. Runs on cron between 1–4 AM daily.

```mermaid
graph LR
    cron["n8n Cron<br/>1–4 AM daily"]

    sam["SAM.gov"]
    canada["Canada Buys"]
    alberta["Alberta<br/>Purchasing"]
    dibbs["DIBBS<br/>(blocked)"]

    normalize["Normalize<br/>Leads"]
    dedup["Dedup<br/>Sub-workflow"]
    sheet["Google Sheet<br/>(Master)"]

    cron --> sam & canada & alberta
    cron -. "failing" .-> dibbs

    sam & canada & alberta --> normalize
    dibbs -. "no data" .-> normalize
    normalize --> dedup --> sheet

    classDef blocked stroke-dasharray:5 5,stroke:#e74c3c
    class dibbs blocked
```

## 3. Email Automation Flow

Two paths: outbound outreach to suppliers and inbound reply handling with LLM intelligence.

```mermaid
graph TD
    subgraph Outbound
        sheet["Google Sheet<br/>(contacts)"]
        outreach["n8n Outreach<br/>Workflow"]
        template["Templated<br/>Email"]
        supplier["Supplier<br/>Inbox"]

        sheet --> outreach --> template --> supplier
    end

    subgraph Inbound
        reply["Supplier<br/>Reply"]
        monitor["n8n Email<br/>Monitor"]
        classify["classify-thread<br/>(LLM)"]
        extract["extract-quote<br/>(LLM)"]
        draft["draft-reply<br/>(LLM)"]
        drafts["Drafts Folder<br/>(Human Review)"]

        reply --> monitor --> classify
        classify --> extract --> draft --> drafts
    end

    supplier -. "replies" .-> reply
```

## 4. Document Intelligence

PDF bid packages are downloaded, OCR'd, and parsed into structured fields.

```mermaid
graph LR
    url["PDF URL"]
    download["Download<br/>PDF"]
    ocr["OCR<br/>(Tesseract)"]
    parse["Parse<br/>Fields"]
    output["Structured Output"]

    url --> download --> ocr --> parse --> output

    output --- fields["Eligibility | Specs | Quantity<br/>Delivery | Deadlines"]
```

## 5. Roadmap

Three-week roadmap from current state through full end-to-end testing.

```mermaid
gantt
    title 3-Week Roadmap
    dateFormat YYYY-MM-DD
    axisFormat %b %d

    section Week 1
    Finalize DIBBS + Data Validation     :active, w1, 2026-02-16, 7d

    section Week 2
    Email Bot — replies + AI drafting    :w2, after w1, 7d

    section Week 3
    Full End-to-End Testing              :w3, after w2, 7d
```
