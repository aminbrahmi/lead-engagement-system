# tests/test_name_enricher.py
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

from tools.name_enricher import NameEnricherTool

tool = NameEnricherTool()

# Test on unknown leads from our Berlin campaign
UNKNOWNS = [
    "Tower | CTO | Berlin",
    "Cognee | CTO | Berlin",
    "Needle | CTO | Berlin",
    "Peec AI | CTO | Berlin",
    "Parloa | CTO | Berlin",
    # Generic tests — any company/role/location
    "Stripe | CEO | San Francisco",
    "Mistral AI | CTO | Paris",
    "Instadeep | CEO | Tunis",
]

print("\n" + "="*60)
print("  NAME ENRICHER — TEST RESULTS")
print("="*60)

for query in UNKNOWNS:
    company = query.split("|")[0].strip()
    print(f"\n  Query  : {query}")
    result = tool._run(query)
    print(f"  Result : {result}")
    found = "Found:" in result
    print(f"  Status : {'✅ Name found' if found else '❌ Not found'}")