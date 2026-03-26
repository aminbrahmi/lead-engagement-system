# tests/test_unified.py
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

from tools.contact_finder import UnifiedEmailFinderTool

tool = UnifiedEmailFinderTool()

TEST_LEADS = [
    "Florian Wenzel    | mirelo.ai   | Mirelo",
    "Vasilije Markovic | cognee.ai   | Cognee",
    "Onur Eken         | needle.so   | Needle",
    "Alexander Matthey | parloa.com  | Parloa",
    "Tobias Siwonia    | peec.ai     | Peec AI",
    "Adam Bahlke       | motorai.de  | MOTOR Ai",
]

print("\n" + "="*65)
print("  UNIFIED EMAIL FINDER")
print("="*65)

for query in TEST_LEADS:
    name = query.split("|")[0].strip()
    print(f"\n{'─'*65}")
    print(f"  Lead   : {name}")
    result = tool._run(query)
    print(f"  Result : {result}")