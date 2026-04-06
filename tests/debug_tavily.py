"""
debug_tavily.py — teste directement l'API Tavily avec des requêtes simples.

Run:
  python -m tests.debug_tavily
  python -m tests.debug_tavily --company Parloa --name "Alexander Matthey"
"""

import os, sys, json, requests
from dotenv import load_dotenv
load_dotenv()

API_KEY = os.getenv("TAVILY_API_KEY", "")
COMPANY = "Mirelo"
NAME    = "Florian Wenzel"
ROLE    = "CTO"

if "--company" in sys.argv:
    COMPANY = sys.argv[sys.argv.index("--company") + 1]
if "--name" in sys.argv:
    NAME = sys.argv[sys.argv.index("--name") + 1]


def search(query: str, max_results: int = 3) -> dict:
    if not API_KEY:
        return {"error": "TAVILY_API_KEY not set"}
    try:
        resp = requests.post(
            "https://api.tavily.com/search",
            json={"api_key": API_KEY, "query": query, "max_results": max_results},
            timeout=12,
        )
        if resp.status_code != 200:
            return {"error": f"HTTP {resp.status_code}: {resp.text[:100]}"}
        return resp.json()
    except Exception as e:
        return {"error": str(e)}


# Simple queries — no OR, no site:, no quotes
QUERIES = [
    f"{COMPANY} Berlin AI startup",
    f"{COMPANY} funding",
    f"{NAME} {COMPANY}",
    f"{NAME} CTO startup",
    f"{COMPANY} AI product",
]

print(f"\nDEBUG TAVILY — {COMPANY} / {NAME}")
print(f"API key: {'SET (' + API_KEY[:8] + '...)' if API_KEY else 'NOT SET ⚠'}")
print("="*60)

total_content = 0
for q in QUERIES:
    print(f"\nQuery: {q}")
    print("-"*50)
    data = search(q)

    if "error" in data:
        print(f"  ERROR: {data['error']}")
        continue

    answer  = data.get("answer", "")
    results = data.get("results", [])

    if answer:
        print(f"  ANSWER: {answer[:200]}")

    if not results:
        print("  (no results)")
    for r in results:
        title   = r.get("title", "")
        url     = r.get("url", "")
        content = r.get("content", "")
        total_content += len(content)
        print(f"  [{title[:65]}]")
        print(f"   {url[:70]}")
        print(f"   {content[:120]}")

print(f"\n{'='*60}")
print(f"Total content: {total_content} chars")

if not API_KEY:
    print("⛔ TAVILY_API_KEY is not set in .env — fix this first")
elif total_content == 0:
    print("⚠  Zero results for all queries.")
    print()
    print("  Likely cause: Tavily free tier may have hit its monthly limit.")
    print("  Check your quota at: https://app.tavily.com")
    print()
    print("  Quick test — run this to verify the API key works at all:")
    print('  curl -X POST https://api.tavily.com/search \\')
    print('    -H "Content-Type: application/json" \\')
    print(f'    -d \'{{"api_key":"{API_KEY[:8]}...","query":"OpenAI","max_results":1}}\'')
elif total_content < 500:
    print("⚠  Very little content — company may not be well indexed.")
else:
    print("✓  Good content — enrichment should work.")