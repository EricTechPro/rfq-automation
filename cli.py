"""
Command Line Interface

CLI for batch processing NSNs from command line or file.
Features:
- Incremental CSV/JSON updates after each NSN
- Resume capability - automatically skips already-processed NSNs
- Progress tracking with ETA
"""

import argparse
import asyncio
import csv
import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Set

from core import scrape_batch, flatten_to_rows
from utils.helpers import format_nsn_with_dashes


class ProgressTracker:
    """Track progress with timing and ETA calculation."""

    def __init__(self, total: int, already_processed: int = 0):
        self.total = total
        self.already_processed = already_processed
        self.start_time = time.time()
        self.current = 0
        self.successful = 0
        self.failed = 0

    def update(self, current: int):
        """Update progress tracking."""
        self.current = current

    def get_elapsed(self) -> str:
        """Get elapsed time as formatted string."""
        elapsed = time.time() - self.start_time
        return str(timedelta(seconds=int(elapsed)))

    def get_eta(self) -> str:
        """Calculate estimated time remaining."""
        if self.current == 0:
            return "calculating..."

        elapsed = time.time() - self.start_time
        avg_per_item = elapsed / self.current
        remaining = (self.total - self.current) * avg_per_item

        if remaining < 60:
            return f"{int(remaining)}s"
        elif remaining < 3600:
            return f"{int(remaining / 60)}m {int(remaining % 60)}s"
        else:
            hours = int(remaining / 3600)
            minutes = int((remaining % 3600) / 60)
            return f"{hours}h {minutes}m"

    def get_progress_bar(self, width: int = 20) -> str:
        """Generate a visual progress bar."""
        if self.total == 0:
            return "[" + "=" * width + "]"

        filled = int((self.current / self.total) * width)
        empty = width - filled
        if filled < width:
            return "[" + "=" * filled + ">" + " " * (empty - 1) + "]"
        return "[" + "=" * width + "]"


def log(message: str, level: str = "INFO"):
    """Print timestamped log message."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    prefix = {
        "INFO": "ℹ️ ",
        "OK": "✅",
        "ERR": "❌",
        "WARN": "⚠️ ",
        "SKIP": "⏭️ ",
    }.get(level, "  ")
    print(f"[{timestamp}] {prefix} {message}")


def parse_nsns(args: argparse.Namespace) -> List[str]:
    """Parse NSNs from command line arguments or file."""
    nsns = []

    if args.nsns:
        nsns = [nsn.strip() for nsn in args.nsns.split(",") if nsn.strip()]

    elif args.file:
        file_path = Path(args.file)
        if not file_path.exists():
            log(f"File not found: {args.file}", "ERR")
            sys.exit(1)

        with open(file_path, "r") as f:
            nsns = [line.strip() for line in f if line.strip()]

    return nsns


def load_processed_nsns(csv_path: Path) -> Set[str]:
    """Load already-processed NSNs from existing CSV file."""
    if not csv_path.exists():
        return set()

    processed = set()
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if 'NSN' in row:
                    processed.add(row['NSN'])
    except Exception as e:
        log(f"Warning: Could not read existing CSV: {e}", "WARN")
        return set()

    return processed


def append_to_csv(rows: List[dict], filepath: Path) -> None:
    """Append rows to CSV file (create with header if new)."""
    file_exists = filepath.exists() and filepath.stat().st_size > 0

    with open(filepath, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)

        # Write header if new file
        if not file_exists:
            writer.writerow(["NSN", "Open Status", "Supplier Name", "CAGE Code", "Email", "Phone"])

        # Write data rows
        for row in rows:
            writer.writerow([
                row["nsn"],
                row["open_status"],
                row["supplier_name"],
                row["cage_code"],
                row["email"],
                row["phone"]
            ])


def update_json(new_rows: List[dict], filepath: Path, summary: dict) -> None:
    """Update JSON file with new results (append to existing)."""
    existing = {"results": [], "summary": {}, "last_updated": None}

    # Load existing data if file exists
    if filepath.exists():
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                existing = json.load(f)
        except (json.JSONDecodeError, Exception):
            existing = {"results": [], "summary": {}, "last_updated": None}

    # Append new rows
    existing["results"].extend(new_rows)
    existing["summary"] = summary
    existing["last_updated"] = datetime.now().isoformat()

    # Save updated data
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(existing, f, indent=2, ensure_ascii=False)


def create_output_dir() -> Path:
    """Create output directory if it doesn't exist."""
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)
    return output_dir


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="RFQ Automation CLI - Batch process NSNs with resume capability",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 cli.py --file nsns.txt                    # Process NSNs (auto-resume if interrupted)
  python3 cli.py --file nsns.txt --force            # Start fresh, ignore existing progress
  python3 cli.py --file nsns.txt --output-name run1 # Custom output file name
  python3 cli.py --nsns "1234567890123,9876543210987"
        """
    )

    parser.add_argument("--nsns", help="Comma-separated NSNs to process")
    parser.add_argument("--file", help="File containing NSNs (one per line)")
    parser.add_argument("--output-name", default="batch_results",
                        help="Base name for output files (default: batch_results)")
    parser.add_argument("--force", action="store_true",
                        help="Start fresh, overwrite existing files")
    parser.add_argument("--quiet", action="store_true",
                        help="Minimal output")

    args = parser.parse_args()

    if not args.nsns and not args.file:
        parser.error("Either --nsns or --file is required")

    # Create output directory and determine file paths
    output_dir = create_output_dir()
    csv_path = output_dir / f"{args.output_name}.csv"
    json_path = output_dir / f"{args.output_name}.json"

    # Handle --force flag
    if args.force:
        if csv_path.exists():
            csv_path.unlink()
            log(f"Deleted existing: {csv_path}", "INFO")
        if json_path.exists():
            json_path.unlink()
            log(f"Deleted existing: {json_path}", "INFO")

    # Parse all NSNs
    all_nsns = parse_nsns(args)

    if not all_nsns:
        log("No valid NSNs found", "ERR")
        sys.exit(1)

    # Load already-processed NSNs (resume logic)
    processed_nsns = load_processed_nsns(csv_path)

    # Filter to remaining NSNs (format with dashes for comparison)
    remaining_nsns = []
    for nsn in all_nsns:
        formatted = format_nsn_with_dashes(nsn)
        if formatted not in processed_nsns:
            remaining_nsns.append(nsn)

    # Print header
    print("\n" + "=" * 60)
    print("  RFQ AUTOMATION - BATCH PROCESSOR")
    print("=" * 60)

    log(f"Total NSNs in input: {len(all_nsns)}")
    if processed_nsns:
        log(f"Already processed: {len(processed_nsns)}", "SKIP")
    log(f"Remaining to process: {len(remaining_nsns)}")

    if not remaining_nsns:
        log("All NSNs already processed! Use --force to reprocess.", "OK")
        print("=" * 60 + "\n")
        sys.exit(0)

    if processed_nsns:
        log(f"Resuming from NSN {len(processed_nsns) + 1}...", "INFO")

    print("-" * 60)

    # Initialize progress tracker
    tracker = ProgressTracker(len(remaining_nsns), len(processed_nsns))

    # Track cumulative stats for JSON summary
    cumulative_stats = {
        "total_nsns_in_file": len(all_nsns),
        "processed": len(processed_nsns),
        "successful": len(processed_nsns),  # Assume existing are successful
        "failed": 0,
        "total_rows": 0
    }

    # Count existing rows in CSV for accurate total
    if csv_path.exists():
        with open(csv_path, 'r') as f:
            cumulative_stats["total_rows"] = sum(1 for _ in f) - 1  # -1 for header

    # Progress callback
    def progress_callback(current: int, total: int, message: str):
        tracker.update(current)

        if "Step" in message:
            parts = message.split(" - ")
            if len(parts) >= 2:
                nsn_part = parts[0]
                step_part = parts[1] if len(parts) > 1 else ""

                if "Step 1" in step_part:
                    status = "🔍 SCRAPING"
                elif "Step 2" in step_part:
                    status = "📇 CONTACTS"
                elif "Step 3" in step_part:
                    status = "📦 BUILDING"
                else:
                    status = "🔄 WORKING"

                progress_bar = tracker.get_progress_bar(20)
                percentage = (current / total) * 100 if total > 0 else 0
                eta = tracker.get_eta()
                elapsed = tracker.get_elapsed()

                # Show overall progress including already processed
                overall = len(processed_nsns) + current
                overall_total = len(all_nsns)

                print(f"\r{progress_bar} {percentage:5.1f}% | {nsn_part} | {status} | Elapsed: {elapsed} | ETA: {eta} | Overall: {overall}/{overall_total}    ", end="", flush=True)
        else:
            progress_bar = tracker.get_progress_bar(20)
            percentage = (current / total) * 100 if total > 0 else 0
            print(f"\r{progress_bar} {percentage:5.1f}% | {message}    ", end="", flush=True)

    # Batch status callback - save incrementally after each NSN
    def batch_status_callback(nsn_index: int, nsn_result):
        if nsn_result.status == "success" and nsn_result.result:
            tracker.successful += 1
            cumulative_stats["successful"] += 1
            cumulative_stats["processed"] += 1

            # Flatten and save immediately
            rows = flatten_to_rows(nsn_result.result)
            append_to_csv(rows, csv_path)
            cumulative_stats["total_rows"] += len(rows)

            # Update JSON
            update_json(rows, json_path, {
                "total_nsns_in_input": len(all_nsns),
                "processed": cumulative_stats["processed"],
                "successful": cumulative_stats["successful"],
                "failed": cumulative_stats["failed"],
                "total_rows": cumulative_stats["total_rows"],
                "success_rate": f"{(cumulative_stats['successful'] / cumulative_stats['processed'] * 100):.1f}%" if cumulative_stats["processed"] > 0 else "0%"
            })

            if not args.quiet:
                supplier_count = len(nsn_result.result.suppliers) if nsn_result.result else 0
                status = "OPEN" if (nsn_result.result and nsn_result.result.has_open_rfq) else "CLOSED"
                overall_idx = len(processed_nsns) + nsn_index
                print(f"\n✅ [{overall_idx}/{len(all_nsns)}] {nsn_result.nsn} - {status} - {supplier_count} supplier(s) [SAVED]")

        elif nsn_result.status == "error":
            tracker.failed += 1
            cumulative_stats["failed"] += 1
            cumulative_stats["processed"] += 1

            overall_idx = len(processed_nsns) + nsn_index
            print(f"\n❌ [{overall_idx}/{len(all_nsns)}] {nsn_result.nsn} - ERROR: {nsn_result.error_message}")

    # Run batch scrape
    try:
        batch_result = asyncio.run(
            scrape_batch(remaining_nsns, progress_callback=progress_callback, batch_status_callback=batch_status_callback)
        )
    except KeyboardInterrupt:
        print("\n")
        log("Process interrupted by user", "WARN")
        log(f"Progress saved! Run again to resume from NSN {cumulative_stats['processed'] + 1}", "INFO")
        sys.exit(1)
    except Exception as e:
        print("\n")
        log(f"Fatal error: {str(e)}", "ERR")
        log(f"Progress saved! Run again to resume.", "INFO")
        sys.exit(1)

    # Final summary
    print("\n")
    print("-" * 60)

    elapsed = tracker.get_elapsed()
    success_rate = (cumulative_stats["successful"] / cumulative_stats["processed"] * 100) if cumulative_stats["processed"] > 0 else 0

    print("\n📊 FINAL SUMMARY")
    print("-" * 60)
    print(f"  Total NSNs in input:   {len(all_nsns)}")
    print(f"  ✅ Successful:         {cumulative_stats['successful']}")
    print(f"  ❌ Failed:             {cumulative_stats['failed']}")
    print(f"  📈 Success rate:       {success_rate:.1f}%")
    print(f"  📄 Total supplier rows: {cumulative_stats['total_rows']}")
    print(f"  ⏱️  Session time:       {elapsed}")
    print("-" * 60)

    log(f"CSV: {csv_path}", "OK")
    log(f"JSON: {json_path}", "OK")

    print("-" * 60)
    log("Batch processing complete!", "OK")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
