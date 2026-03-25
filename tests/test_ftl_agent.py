# tests/test_ftl_agent.py
# Lance l'agent email hunter sur les leads en base

import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from memory.storage import get_all_leads
from agents.email_hunter import find_emails_for_leads

# Charge les leads qualifiés sans email vérifié
leads = get_all_leads(status="qualified")

print(f"\n[*] Found {len(leads)} qualified leads")
print("[*] Starting FindThatLead search...\n")

results = find_emails_for_leads(leads)

print("\n" + "="*55)
print("  RESULTS")
print("="*55)
for r in results:
    status = "✓" if r["found"] else "✗"
    print(f"  {status} {r['name']} @ {r['company']}")
    print(f"    Email : {r['email'] or 'not found'}")