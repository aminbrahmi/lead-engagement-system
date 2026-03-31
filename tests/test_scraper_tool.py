# tests/test_scraper.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tools.scraper_tool import CrawleeTool
import time

tool = CrawleeTool()

# URLs variées pour tester différents cas
TEST_URLS = [
    ("Static simple",   "https://example.com"),
    ("Page équipe",     "https://www.parloa.com/about"),
    ("Crunchbase",      "https://www.crunchbase.com/organization/parloa"),
    ("LinkedIn",        "https://www.linkedin.com/company/parloa"),
]

for label, url in TEST_URLS:
    print(f"\n{'='*50}")
    print(f"[TEST] {label}: {url}")
    start = time.time()
    result = tool._run(url)
    elapsed = time.time() - start

    print(f"  ⏱  {elapsed:.1f}s")
    print(f"  📏  {len(result)} chars")
    print(f"  📄  Preview: {result[:200]}")
    
    if "Scraping failed" in result:
        print("  ❌ FAILED")
    elif len(result) < 100:
        print("  ⚠️  TOO SHORT — probably blocked")
    else:
        print("  ✅ OK")