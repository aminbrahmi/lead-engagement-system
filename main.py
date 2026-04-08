import time
from dotenv import load_dotenv
load_dotenv()

from orchestration.graph import run_lead_pipeline


if __name__ == "__main__":
    campaign = input("Describe your campaign : ")

    global_start = time.time()
    print(f"\n[⏱️ GLOBAL START] {time.strftime('%H:%M:%S')}")

    result       = run_lead_pipeline(campaign)
    pipeline_end = time.time()

    print(f"[⏱️ PIPELINE END] {time.strftime('%H:%M:%S')}")
    print(f"[⏱️ PIPELINE TIME] {pipeline_end - global_start:.2f} sec")

    # Show enriched leads (includes draft emails) if available
    enriched  = result.get("enriched_leads", [])
    qualified = result.get("qualified_leads", [])
    leads     = enriched if enriched else qualified

    hot  = [l for l in leads if l.get("segment") == "hot"]
    warm = [l for l in leads if l.get("segment") == "warm"]
    cold = [l for l in leads if l.get("segment") == "cold"]

    print(f"\n===== PIPELINE RESULTS =====")
    print(f"  HOT  : {len(hot)}")
    print(f"  WARM : {len(warm)}")
    print(f"  COLD : {len(cold)}")
    print(f"  TOTAL: {len(leads)}")
    print()

    for lead in leads:
        seg     = (lead.get("segment") or "?").upper()
        company = lead.get("company", "?")
        name    = lead.get("name", "unknown")
        email   = lead.get("email", "no email")
        draft   = lead.get("draft_email", {})
        subject = draft.get("subject", "") if draft else ""

        line = f"  [{seg:4}] {company:<20} {name:<28} {email}"
        if subject:
            line += f"\n         Subject: {subject}"
        print(line)

    global_end = time.time()
    print(f"\n[⏱️ TOTAL TIME] {global_end - global_start:.2f} sec")