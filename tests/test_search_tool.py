# tests/test_search_tool.py
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

from tools.search_tool import TavilySearchTool

tool = TavilySearchTool()

QUERIES = [
    "Berlin AI startups funding 2026",
    "CTO Parloa Berlin",
    "Cognee startup Berlin founders",
]

print("\n" + "="*60)
print("  TAVILY SEARCH TOOL — TEST")
print("="*60)

for q in QUERIES:
    print(f"\n🔎 Query: {q}")
    result = tool._run(q)
    print(f"\n📄 Results:\n{result[:1000]}")