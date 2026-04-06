import time
from dotenv import load_dotenv
load_dotenv()

from orchestration.graph import run_lead_pipeline


if __name__ == "__main__":
    campaign = input("Describe your campaign : ")

    # ⏱️ Temps global start
    global_start = time.time()
    print(f"\n[⏱️ GLOBAL START] {time.strftime('%H:%M:%S')}")

    # ⚡ Exécution pipeline
    pipeline_start = time.time()
    result = run_lead_pipeline(campaign)
    pipeline_end = time.time()

    print(f"[⏱️ PIPELINE END] {time.strftime('%H:%M:%S')}")
    print(f"[⏱️ PIPELINE TIME] {pipeline_end - pipeline_start:.2f} sec")

    print("\n===== LEADS COLLECTÉS =====")

    qualified = result.get("qualified_leads", [])
    print(f"{len(qualified)} leads qualified.")

    for lead in qualified:
        print(f"  [{lead.get('segment','?').upper():4}] {lead.get('company')} / {lead.get('name')} — {lead.get('email','no email')}")

    # ⏱️ Temps global end
    global_end = time.time()
    print("\n[⏱️ GLOBAL END]")
    print(f"[⏱️ TOTAL TIME] {global_end - global_start:.2f} sec")