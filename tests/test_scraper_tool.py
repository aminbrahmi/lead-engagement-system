# tests/test_scraper_tool.py
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

from tools.search_tool import TavilySearchTool
from tools.scraper_tool import CrawleeTool

search = TavilySearchTool()
scraper = CrawleeTool()

query = "Cognee Berlin startup funding founders"

print("\n" + "="*60)
print("  SEARCH → SCRAPE PIPELINE TEST")
print("="*60)

# Step 1 — Search
results = search._run(query)
print(f"\n🔎 Search Results:\n{results}")

# Step 2 — Extract first URL
import re
urls = re.findall(r'https?://\S+', results)

if urls:
    url = urls[0]
    print(f"\n🌐 Scraping: {url}")

    content = scraper._run(url)
    print(f"\n📄 Scraped Content:\n{content[:1000]}")
else:
    print("\n❌ No URLs found")