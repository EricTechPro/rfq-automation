"""
Utility Functions

Helper functions for NSN formatting, deduplication, and file I/O.
"""

import json
import re
from pathlib import Path
from typing import Dict, Any
from datetime import datetime

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
