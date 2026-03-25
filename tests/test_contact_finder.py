# tests/test_contact_finder.py
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

from tools.contact_finder import ContactFinderTool

tool = ContactFinderTool()

TEST_LEADS = [
    "Florian Wenzel    | mirelo.ai   | Mirelo",
    "Vasilije Markovic | cognee.ai   | Cognee",
    "Onur Eken         | needle.so   | Needle",
    "Alexander Matthey | parloa.com  | Parloa",
    "Tobias Siwonia    | peec.ai     | Peec AI",
    "Adam Bahlke       | motorai.de  | MOTOR Ai",
]

print("\n" + "="*65)
print("  CONTACT FINDER — COMBINED PIPELINE RESULTS")
print("="*65)

for query in TEST_LEADS:
    name = query.split("|")[0].strip()
    print(f"\n{'─'*65}")
    print(f"  Lead   : {name}")
    result = tool._run(query)

    # Parse result
    parts  = result.split(" | ")
    email  = next((p.replace("email:", "") for p in parts if p.startswith("email:")), None)
    phone  = next((p.replace("phone:", "") for p in parts if p.startswith("phone:")), None)
    e_src  = next((p.replace("email_source:", "") for p in parts if p.startswith("email_source:")), None)
    p_src  = next((p.replace("phone_source:", "") for p in parts if p.startswith("phone_source:")), None)

    print(f"  Email  : {email or '❌ not found'} {f'({e_src})' if e_src else ''}")
    print(f"  Phone  : {phone or '❌ not found'} {f'({p_src})' if p_src else ''}")

print(f"\n{'═'*65}")
print(f"  API STATUS")
print(f"{'─'*65}")
print(f"  FTL_TOKEN      : {'✓' if os.getenv('FTL_TOKEN') else '✗ missing'}")
print(f"  TAVILY_API_KEY : {'✓' if os.getenv('TAVILY_API_KEY') else '✗ missing'}")
print(f"  APOLLO_API_KEY : {'✓' if os.getenv('APOLLO_API_KEY') else '✗ missing'}")