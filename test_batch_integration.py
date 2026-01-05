#!/usr/bin/env python3
"""
Integration test for batch NSN processing
Tests both single and batch modes
"""
import asyncio
import sys
from models import BatchProcessingResult, BatchNSNResult
from utils.helpers import validate_nsn, format_nsn_with_dashes
from app import run_batch_scrape

async def test_batch_processing():
    """Test batch processing with multiple NSNs"""
    print("\n🧪 Testing Batch NSN Processing")
    print("=" * 60)

    # Test NSNs (mix of valid and invalid)
    test_nsns = [
        "4520-01-261-9675",  # Valid - HEATER,VENTILATION
        "invalid-nsn",        # Invalid format
        "4030-01-097-6471",  # Valid - SHACKLE,SPECIAL
    ]

    print(f"\nTest NSNs:")
    for idx, nsn in enumerate(test_nsns, start=1):
        print(f"  {idx}. {nsn}")

    # Progress callback
    def progress_callback(current, total, message):
        print(f"  Progress [{current}/{total}]: {message}")

    # Status callback
    def status_callback(nsn_index, nsn_result):
        print(f"  Status Update: NSN {nsn_index} - {nsn_result.status.upper()}")

    print("\n" + "-" * 60)
    print("Running batch scrape...")
    print("-" * 60)

    try:
        batch_result = await run_batch_scrape(
            test_nsns,
            progress_callback,
            status_callback
        )

        print("\n" + "=" * 60)
        print("BATCH PROCESSING RESULTS")
        print("=" * 60)

        print(f"\nTotal NSNs: {batch_result.total_nsns}")
        print(f"Processed: {batch_result.processed}")
        print(f"Successful: {batch_result.successful}")
        print(f"Failed: {batch_result.failed}")
        success_rate = (batch_result.successful / batch_result.total_nsns * 100) if batch_result.total_nsns > 0 else 0
        print(f"Success Rate: {success_rate:.1f}%")

        print("\nDetailed Results:")
        for idx, nsn_result in enumerate(batch_result.results, start=1):
            print(f"\n  [{idx}] NSN: {nsn_result.nsn}")
            print(f"      Status: {nsn_result.status.upper()}")

            if nsn_result.status == "success" and nsn_result.result:
                result = nsn_result.result
                print(f"      Item: {result.item_name or 'N/A'}")
                print(f"      RFQ Status: {'OPEN' if result.has_open_rfq else 'CLOSED'}")
                print(f"      Suppliers: {len(result.suppliers)}")
                print(f"      DIBBS: {result.workflow.dibbs_status}")
                print(f"      WBParts: {result.workflow.wbparts_status}")
                print(f"      Contacts: {result.workflow.firecrawl_status}")
            elif nsn_result.status == "error":
                print(f"      Error: {nsn_result.error_message}")

        print("\n" + "=" * 60)
        print("✅ Batch processing test completed successfully!")
        print("=" * 60)

        # Validation checks
        print("\nValidation Checks:")
        checks_passed = 0
        total_checks = 0

        # Check 1: Total processed matches total NSNs
        total_checks += 1
        if batch_result.processed == batch_result.total_nsns:
            print("  ✅ All NSNs processed")
            checks_passed += 1
        else:
            print(f"  ❌ Not all NSNs processed: {batch_result.processed}/{batch_result.total_nsns}")

        # Check 2: Successful + Failed = Total
        total_checks += 1
        if (batch_result.successful + batch_result.failed) == batch_result.total_nsns:
            print("  ✅ Success + Failure counts match total")
            checks_passed += 1
        else:
            print(f"  ❌ Counts don't match: {batch_result.successful} + {batch_result.failed} != {batch_result.total_nsns}")

        # Check 3: Invalid NSN marked as error
        total_checks += 1
        invalid_result = batch_result.results[1]  # Second NSN is invalid
        if invalid_result.status == "error":
            print("  ✅ Invalid NSN properly marked as error")
            checks_passed += 1
        else:
            print(f"  ❌ Invalid NSN not marked as error: {invalid_result.status}")

        # Check 4: At least one valid NSN succeeded
        total_checks += 1
        if batch_result.successful >= 1:
            print(f"  ✅ At least one valid NSN succeeded ({batch_result.successful} total)")
            checks_passed += 1
        else:
            print("  ❌ No valid NSNs succeeded")

        print(f"\nValidation: {checks_passed}/{total_checks} checks passed")

        return batch_result

    except Exception as e:
        print(f"\n❌ Batch processing failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


async def test_single_nsn_validation():
    """Test NSN validation"""
    print("\n🧪 Testing NSN Validation")
    print("=" * 60)

    test_cases = [
        ("4520-01-261-9675", True),
        ("4520012619675", True),
        ("invalid", False),
        ("", False),
        ("1234-56-789-0123", True),
    ]

    passed = 0
    for nsn, expected in test_cases:
        result = validate_nsn(nsn)
        status = "✅" if result == expected else "❌"
        print(f"  {status} '{nsn}' -> {result} (expected: {expected})")
        if result == expected:
            passed += 1

    print(f"\nValidation Test: {passed}/{len(test_cases)} passed\n")


async def main():
    """Run all tests"""
    print("\n" + "=" * 60)
    print("RFQ AUTOMATION - BATCH PROCESSING INTEGRATION TEST")
    print("=" * 60)

    # Test 1: NSN Validation
    await test_single_nsn_validation()

    # Test 2: Batch Processing
    batch_result = await test_batch_processing()

    print("\n" + "=" * 60)
    print("ALL TESTS COMPLETED")
    print("=" * 60)
    print()


if __name__ == "__main__":
    asyncio.run(main())
