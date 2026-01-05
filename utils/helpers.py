"""
Utility Functions

Helper functions for NSN formatting, deduplication, and file I/O.
"""

import json
import re
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime

from models import ApprovedSource, WBPartsManufacturer


def format_nsn(nsn: str) -> str:
    """
    Remove dashes from NSN.

    Input: "4520-01-261-9675" or "4520012619675"
    Output: "4520012619675"
    """
    return nsn.replace("-", "")


def format_nsn_with_dashes(nsn: str) -> str:
    """
    Format NSN with dashes.

    Input: "4520012619675" or "4520-01-261-9675"
    Output: "4520-01-261-9675"
    """
    # Remove existing dashes first
    clean = nsn.replace("-", "")

    # Validate length
    if len(clean) != 13:
        return nsn

    # Format: XXXX-XX-XXX-XXXX
    return f"{clean[:4]}-{clean[4:6]}-{clean[6:9]}-{clean[9:13]}"


def validate_nsn(nsn: str) -> bool:
    """
    Validate NSN format.

    Valid formats:
    - "4520-01-261-9675" (with dashes)
    - "4520012619675" (without dashes)
    """
    # With dashes pattern
    pattern_with_dashes = r"^\d{4}-\d{2}-\d{3}-\d{4}$"
    # Without dashes pattern
    pattern_without_dashes = r"^\d{13}$"

    return bool(re.match(pattern_with_dashes, nsn) or re.match(pattern_without_dashes, nsn))


def get_unique_suppliers(
    dibbs_sources: List[ApprovedSource],
    wbparts_mfrs: List[WBPartsManufacturer]
) -> List[Dict[str, str]]:
    """
    Get unique suppliers from DIBBS and WBParts data.

    Deduplicates by company_name + cage_code.
    DIBBS sources take precedence.
    """
    seen = set()
    suppliers = []

    # Process DIBBS sources first
    for source in dibbs_sources:
        key = f"{source.company_name}|{source.cage_code}"
        if key not in seen and source.company_name:
            seen.add(key)
            suppliers.append({
                "companyName": source.company_name,
                "cageCode": source.cage_code,
                "partNumber": source.part_number
            })

    # Process WBParts manufacturers
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


def save_result(nsn: str, result: Dict[str, Any], output_dir: str = "./results") -> str:
    """
    Save result to JSON file.

    Creates output directory if it doesn't exist.
    Returns the filepath.
    """
    # Create output directory
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Create filename
    filename = f"{format_nsn_with_dashes(nsn)}.json"
    filepath = output_path / filename

    # Write JSON
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    return str(filepath)


def get_timestamp() -> str:
    """Get current timestamp in ISO 8601 format"""
    return datetime.utcnow().isoformat() + "Z"
