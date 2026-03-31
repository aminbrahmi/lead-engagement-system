# main.py
from dotenv import load_dotenv
load_dotenv()

from orchestration.graph import run_lead_pipeline   # ← only import changes

if __name__ == "__main__":
    campaign = input("Describe your campaign : ")
    result   = run_lead_pipeline(campaign)

    print("\n===== LEADS COLLECTÉS =====")
    # result is now the full state dict; qualified_leads holds the final list
    qualified = result.get("qualified_leads", [])
    print(f"{len(qualified)} leads qualified.")
    for lead in qualified:
        print(f"  [{lead.get('segment','?').upper():4}] {lead.get('company')} / {lead.get('name')} — {lead.get('email','no email')}")