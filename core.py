"""
Core Business Logic

Shared scraping and processing functions used by Streamlit, API, and CLI interfaces.
"""

import asyncio
import time
from typing import Callable, Optional, List

from config import config
from models import (
    EnhancedRFQResult,
    SupplierWithContact,
    RawData,
    WorkflowStatus,
    ApprovedSource,
    WBPartsManufacturer,
    BatchProcessingResult,
    BatchNSNResult,
)
from scrapers.dibbs import scrape_dibbs
from scrapers.wbparts import scrape_wbparts
from services.firecrawl import find_supplier_contact
from utils.helpers import (
    validate_nsn,
    format_nsn_with_dashes,
    save_result,
    get_timestamp,
)


# Type aliases for callbacks
ProgressCallback = Callable[[int, str], None]
BatchProgressCallback = Callable[[int, int, str], None]
BatchStatusCallback = Callable[[int, BatchNSNResult], None]


def noop_progress(step: int, message: str) -> None:
    """No-op progress callback."""
    pass


def noop_batch_progress(current: int, total: int, message: str) -> None:
    """No-op batch progress callback."""
    pass


def noop_batch_status(nsn_index: int, nsn_result: BatchNSNResult) -> None:
    """No-op batch status callback."""
    pass


def get_unique_suppliers_list(
    dibbs_sources: List[ApprovedSource],
    wbparts_mfrs: List[WBPartsManufacturer]
) -> List[dict]:
    """Get unique suppliers from both sources."""
    seen = set()
    suppliers = []

    for source in dibbs_sources:
        key = f"{source.company_name}|{source.cage_code}"
        if key not in seen and source.company_name:
            seen.add(key)
            suppliers.append({
                "companyName": source.company_name,
                "cageCode": source.cage_code,
                "partNumber": source.part_number
            })

    for mfr in wbparts_mfrs:
        key = f"{mfr.company_name}|{mfr.cage_code}"
        if key not in seen and mfr.company_name:
            seen.add(key)
            suppliers.append({
                "companyName": mfr.company_name,
                "cageCode": mfr.cage_code,
                "partNumber": mfr.part_number
            })

    return suppliers


async def scrape_nsn(
    nsn: str,
    progress_callback: Optional[ProgressCallback] = None
) -> EnhancedRFQResult:
    """
    Run the full scraping workflow for a single NSN.

    Steps:
    1. Scrape DIBBS + WBParts in parallel
    2. Discover contacts for all suppliers
    3. Return enhanced result

    Args:
        nsn: The NSN to scrape
        progress_callback: Optional callback for progress updates (step, message)

    Returns:
        EnhancedRFQResult with complete data
    """
    callback = progress_callback or noop_progress

    # Step 1: Scrape DIBBS + WBParts
    callback(1, "Scraping DIBBS + WBParts...")
    print(f"[DEBUG] scrape_nsn: Starting for NSN {nsn}")

    dibbs_result, wbparts_result = await asyncio.gather(
        scrape_dibbs(nsn),
        scrape_wbparts(nsn)
    )

    # Log DIBBS result
    print(f"[DEBUG] DIBBS result: success={dibbs_result.success}, error={dibbs_result.error}")
    if dibbs_result.data:
        print(f"[DEBUG] DIBBS approved_sources count: {len(dibbs_result.data.approved_sources)}")
    else:
        print(f"[DEBUG] DIBBS data is None")

    # Log WBParts result
    print(f"[DEBUG] WBParts result: success={wbparts_result.success}, error={wbparts_result.error}")
    if wbparts_result.data:
        print(f"[DEBUG] WBParts manufacturers count: {len(wbparts_result.data.manufacturers)}")
    else:
        print(f"[DEBUG] WBParts data is None")

    # Get suppliers
    dibbs_sources = dibbs_result.data.approved_sources if dibbs_result.data else []
    wbparts_mfrs = wbparts_result.data.manufacturers if wbparts_result.data else []
    all_suppliers = get_unique_suppliers_list(dibbs_sources, wbparts_mfrs)
    print(f"[DEBUG] Total unique suppliers: {len(all_suppliers)}")

    has_open_rfq = dibbs_result.data.has_open_rfqs if dibbs_result.data else False

    # Step 2: Contact discovery
    callback(2, f"Discovering contacts for {len(all_suppliers)} supplier(s)...")
    print(f"[DEBUG] Firecrawl configured: {config.is_firecrawl_configured()}")

    suppliers_with_contacts = []
    firecrawl_status = "skipped"

    if all_suppliers and config.is_firecrawl_configured():
        success_count = 0
        print(f"[DEBUG] Starting Firecrawl contact discovery for {len(all_suppliers)} suppliers")

        for idx, supplier in enumerate(all_suppliers):
            print(f"[DEBUG] Finding contact for supplier {idx+1}/{len(all_suppliers)}: {supplier['companyName']}")
            contact = find_supplier_contact(
                supplier["companyName"],
                supplier["cageCode"]
            )

            if contact:
                print(f"[DEBUG] Contact found: confidence={contact.confidence}, email={contact.email}, phone={contact.phone}")
            else:
                print(f"[DEBUG] No contact found for {supplier['companyName']}")

            suppliers_with_contacts.append(SupplierWithContact(
                companyName=supplier["companyName"],
                cageCode=supplier["cageCode"],
                partNumber=supplier["partNumber"],
                contact=contact
            ))

            if contact and contact.confidence != "low":
                success_count += 1

            # Rate limiting
            time.sleep(config.BATCH_DELAY / 1000)

        print(f"[DEBUG] Firecrawl completed: {success_count}/{len(all_suppliers)} high/medium confidence")
        if success_count == len(all_suppliers):
            firecrawl_status = "success"
        elif success_count > 0:
            firecrawl_status = "partial"
        else:
            firecrawl_status = "error"
    else:
        if not all_suppliers:
            print(f"[DEBUG] Skipping Firecrawl: no suppliers found")
        elif not config.is_firecrawl_configured():
            print(f"[DEBUG] Skipping Firecrawl: API not configured")
        # No Firecrawl - just add suppliers without contacts
        for supplier in all_suppliers:
            suppliers_with_contacts.append(SupplierWithContact(
                companyName=supplier["companyName"],
                cageCode=supplier["cageCode"],
                partNumber=supplier["partNumber"],
                contact=None
            ))

    # Step 3: Build result
    callback(3, "Building result...")

    result = EnhancedRFQResult(
        nsn=dibbs_result.data.nsn if dibbs_result.data else format_nsn_with_dashes(nsn),
        itemName=wbparts_result.data.item_name if wbparts_result.data else (
            dibbs_result.data.nomenclature if dibbs_result.data else ""
        ),
        hasOpenRFQ=has_open_rfq,
        suppliers=suppliers_with_contacts,
        rawData=RawData(
            dibbs=dibbs_result.data,
            wbparts=wbparts_result.data
        ),
        workflow=WorkflowStatus(
            dibbsStatus="success" if dibbs_result.success else "error",
            wbpartsStatus="success" if wbparts_result.success else "error",
            firecrawlStatus=firecrawl_status
        ),
        scrapedAt=get_timestamp()
    )

    return result


async def scrape_batch(
    nsns: List[str],
    progress_callback: Optional[BatchProgressCallback] = None,
    batch_status_callback: Optional[BatchStatusCallback] = None
) -> BatchProcessingResult:
    """
    Process multiple NSNs sequentially with rate limiting.

    Args:
        nsns: List of NSN strings to process
        progress_callback: Optional progress update callback (current, total, message)
        batch_status_callback: Optional batch status callback (nsn_index, result)

    Returns:
        BatchProcessingResult with all individual results
    """
    progress_cb = progress_callback or noop_batch_progress
    status_cb = batch_status_callback or noop_batch_status

    batch_result = BatchProcessingResult(
        totalNsns=len(nsns),
        results=[],
        startedAt=get_timestamp()
    )

    for idx, nsn in enumerate(nsns, start=1):
        # Validate NSN
        if not validate_nsn(nsn):
            batch_result.results.append(BatchNSNResult(
                nsn=nsn,
                status="error",
                errorMessage=f"Invalid NSN format: {nsn}",
                processedAt=get_timestamp()
            ))
            batch_result.processed += 1
            batch_result.failed += 1
            status_cb(idx, batch_result.results[-1])
            continue

        # Format NSN
        formatted_nsn = format_nsn_with_dashes(nsn)

        # Update batch progress
        progress_cb(idx, len(nsns), f"Processing NSN {idx}/{len(nsns)}: {formatted_nsn}")

        # Create batch result entry
        batch_nsn_result = BatchNSNResult(
            nsn=formatted_nsn,
            status="processing"
        )
        batch_result.results.append(batch_nsn_result)
        status_cb(idx, batch_nsn_result)

        try:
            # Process individual NSN
            def nsn_progress(step: int, message: str):
                full_message = f"NSN {idx}/{len(nsns)} - Step {step}/3: {message}"
                progress_cb(idx, len(nsns), full_message)

            result = await scrape_nsn(formatted_nsn, nsn_progress)

            # Update success
            batch_nsn_result.status = "success"
            batch_nsn_result.result = result
            batch_nsn_result.processed_at = get_timestamp()
            batch_result.successful += 1

            # Save individual result
            result_dict = result.model_dump(by_alias=True, exclude_none=True)
            save_result(formatted_nsn, result_dict)

        except Exception as e:
            # Update failure
            batch_nsn_result.status = "error"
            batch_nsn_result.error_message = str(e)
            batch_nsn_result.processed_at = get_timestamp()
            batch_result.failed += 1

        batch_result.processed += 1
        status_cb(idx, batch_nsn_result)

        # Rate limiting between NSNs (except last one)
        if idx < len(nsns):
            time.sleep(config.BATCH_DELAY / 1000)

    batch_result.completed_at = get_timestamp()
    return batch_result


def flatten_to_rows(result: EnhancedRFQResult) -> List[dict]:
    """
    Flatten EnhancedRFQResult to one row per supplier.

    Args:
        result: The enhanced RFQ result to flatten

    Returns:
        List of flat dictionaries, one per supplier
    """
    rows = []
    open_status = "OPEN" if result.has_open_rfq else "CLOSED"

    if not result.suppliers:
        # No suppliers - output one row with empty fields
        rows.append({
            "nsn": result.nsn,
            "open_status": open_status,
            "supplier_name": "",
            "cage_code": "",
            "email": "",
            "phone": ""
        })
    else:
        # One row per supplier
        for supplier in result.suppliers:
            email = supplier.contact.email if supplier.contact else ""
            phone = supplier.contact.phone if supplier.contact else ""
            rows.append({
                "nsn": result.nsn,
                "open_status": open_status,
                "supplier_name": supplier.company_name,
                "cage_code": supplier.cage_code,
                "email": email or "",
                "phone": phone or ""
            })

    return rows


def flatten_batch_results(batch_result: BatchProcessingResult) -> List[dict]:
    """
    Flatten all batch results to flat rows.

    Args:
        batch_result: The batch processing result

    Returns:
        List of flat dictionaries, one per supplier across all NSNs
    """
    all_rows = []

    for nsn_result in batch_result.results:
        if nsn_result.status == "success" and nsn_result.result:
            rows = flatten_to_rows(nsn_result.result)
            all_rows.extend(rows)
        elif nsn_result.status == "error":
            # Include error NSNs with empty supplier data
            all_rows.append({
                "nsn": nsn_result.nsn,
                "open_status": "ERROR",
                "supplier_name": "",
                "cage_code": "",
                "email": "",
                "phone": ""
            })

    return all_rows
