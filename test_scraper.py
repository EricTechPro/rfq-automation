#!/usr/bin/env python3
"""
Quick test script to verify scraping functionality
"""
import asyncio
from scrapers.dibbs import scrape_dibbs
from scrapers.wbparts import scrape_wbparts
from utils.helpers import validate_nsn, format_nsn

async def test_scraper():
    """Test basic scraping functionality"""
    # Test NSN
    test_nsn = "4520-01-261-9675"

    print(f"\n🧪 Testing RFQ Automation Scraper")
    print(f"━" * 50)

    # Validate NSN
    print(f"\n1️⃣  Validating NSN: {test_nsn}")
    if not validate_nsn(test_nsn):
        print(f"❌ Invalid NSN format")
        return

    formatted_nsn = format_nsn(test_nsn)
    print(f"✅ Valid NSN: {formatted_nsn}")

    # Test DIBBS scraper
    print(f"\n2️⃣  Testing DIBBS Scraper...")
    try:
        dibbs_result = await scrape_dibbs(formatted_nsn)
        if dibbs_result.success:
            print(f"✅ DIBBS scrape successful")
            print(f"   - Item: {dibbs_result.data.nomenclature if dibbs_result.data else 'N/A'}")
            print(f"   - Suppliers: {len(dibbs_result.data.approved_sources) if dibbs_result.data else 0}")
            print(f"   - Open RFQs: {dibbs_result.data.has_open_rfqs if dibbs_result.data else False}")
        else:
            print(f"❌ DIBBS scrape failed: {dibbs_result.error}")
    except Exception as e:
        print(f"❌ DIBBS scraper error: {e}")

    # Test WBParts scraper
    print(f"\n3️⃣  Testing WBParts Scraper...")
    try:
        wbparts_result = await scrape_wbparts(formatted_nsn)
        if wbparts_result.success:
            print(f"✅ WBParts scrape successful")
            print(f"   - Item: {wbparts_result.data.item_name if wbparts_result.data else 'N/A'}")
            print(f"   - Manufacturers: {len(wbparts_result.data.manufacturers) if wbparts_result.data else 0}")
        else:
            print(f"❌ WBParts scrape failed: {wbparts_result.error}")
    except Exception as e:
        print(f"❌ WBParts scraper error: {e}")

    print(f"\n{'━' * 50}")
    print(f"✅ Test completed!\n")

if __name__ == "__main__":
    asyncio.run(test_scraper())
