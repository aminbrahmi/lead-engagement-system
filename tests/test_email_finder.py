# tests/test_email_finder.py
# Tests the EmailFinderTool on real leads from the database
# Shows which method found the email and the result for each

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from tools.email_finder import EmailFinderTool

# Test cases — real leads from our Berlin campaign
TEST_LEADS = [
    {"name": "Florian Wenzel",     "domain": "mirelo.ai"},
    {"name": "Vasilije Markovic",  "domain": "cognee.ai"},
    {"name": "Adam Bahlke",        "domain": "motorai.de"},
    {"name": "Anna Mayer",         "domain": "deepscale.com"},
    {"name": "Thomas Schreiber",   "domain": "neurotech.com"},
]

tool = EmailFinderTool()

print("\n" + "="*60)
print("  EMAIL FINDER — TEST RESULTS")
print("="*60)

for lead in TEST_LEADS:
    name   = lead["name"]
    domain = lead["domain"]
    query  = f"{name} | {domain}"

    print(f"\n  Testing: {name} @ {domain}")
    print(f"  {'─'*50}")

    result = tool._run(query)
    print(f"  Result : {result}")

    # Shows which method was used
    if "FindThatLead" in result:
        print(f"  Method : FindThatLead ✓ (verified)")
    elif "Hunter" in result:
        print(f"  Method : Hunter.io ✓ (verified)")
    elif "Apollo" in result:
        print(f"  Method : Apollo.io ✓ (verified)")
    elif "smtp" in result:
        print(f"  Method : Pattern + SMTP verified")
    elif "scraping" in result:
        print(f"  Method : Web scraping")
    elif "unverified" in result:
        print(f"  Method : Pattern deduction (fallback)")

print("\n" + "="*60)
print("  API KEYS STATUS")
print("="*60)
print(f"  FTL_TOKEN      : {'✓ set' if os.getenv('FTL_TOKEN') else '✗ missing'}")
print(f"  APOLLO_API_KEY : {'✓ set' if os.getenv('APOLLO_API_KEY') else '✗ missing'}")
print(f"  HUNTER_API_KEY : {'✓ set' if os.getenv('HUNTER_API_KEY') else '✗ missing'}")
print(f"  TAVILY_API_KEY : {'✓ set' if os.getenv('TAVILY_API_KEY') else '✗ missing'}")