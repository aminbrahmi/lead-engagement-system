# tests/test_agents.py
import sys, os, json, re
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)

from agents.collector_node import run_collector
from agents.qualifier_node import run_qualifier
from dotenv import load_dotenv
load_dotenv()

criteria = {
    "job_titles": ["CTO"],
    "location": "Berlin",
    "industry": "AI SaaS",
    "search_queries": [
        "CTO AI startup Berlin funding 2024",
        "Berlin AI SaaS CTO founder raised"
    ]
}
campaign = "Find Berlin AI CTOs"

print("\n===== AGENT 1 =====")
raw = run_collector(campaign, criteria)
print(raw[:600] if raw else "⚠️  Empty")

print("\n===== AGENT 2 =====")
if not raw:
    print("⚠️  Skipping — no input")
else:
    # ← send max 3 leads to Agent 2 to stay within iteration limit
    match = re.search(r'\[.*\]', raw, re.DOTALL)
    if match:
        leads = json.loads(match.group(0))
        raw_trimmed = json.dumps(leads[:3], ensure_ascii=False)
        print(f"[Test] Sending {len(leads[:3])} leads to Agent 2")
    else:
        raw_trimmed = raw

    qualified = run_qualifier(campaign, raw_trimmed)
    print(qualified[:800] if qualified else "⚠️  Empty — see DEBUG above")