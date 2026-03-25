# orchestration/crew.py
# On ajoute Agent 2 après Agent 1 dans le pipeline.
# Agent 2 reçoit le résultat d'Agent 1 comme contexte.

from crewai import Crew, Process
from agents.collector import create_collector_agent, MODELS
from agents.qualifier import create_qualifier_agent
from orchestration.tasks import create_collect_task, create_qualify_task
from tools.prompt_parser import parse_campaign_prompt
from memory.storage import save_leads, update_lead_qualification, init_db
from dotenv import load_dotenv
import json, re, time
load_dotenv()

def _parse_json_from_result(result_str: str) -> list:
    # Extrait le tableau JSON du résultat texte de l'agent
    match = re.search(r'\[.*\]', str(result_str), re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except:
            return []
    return []

# In _is_rate_limit() — add Gemini daily limit detection
def _is_rate_limit(error: Exception) -> bool:
    msg = str(error).lower()
    return any(k in msg for k in [
        "rate_limit", "ratelimit", "429",
        "network connection lost", "resource_exhausted",
        "per_day", "daily", "quota"
    ])

# orchestration/crew.py - Updated save_leads handling

def run_lead_pipeline(campaign_prompt: str):
    init_db()

    print("\n[*] Parsing campaign brief...")
    criteria = parse_campaign_prompt(campaign_prompt)
    print(f"[*] Criteria: {criteria.get('job_titles')} in {criteria.get('location')}\n")

    # ── AGENT 1 : Collecte ──────────────────────────────
    print("\n[AGENT 1] Starting lead collection...")
    raw_leads_json = None

    for tier, model_id in MODELS:
        print(f"\n[*] Trying {tier}: {model_id}")
        try:
            collector = create_collector_agent(model_tier=tier)
            collect_task = create_collect_task(collector, campaign_prompt, criteria)

            crew1 = Crew(
                agents=[collector],
                tasks=[collect_task],
                process=Process.sequential,
                verbose=True
            )
            result1 = crew1.kickoff()
            raw_leads_json = str(result1)

            # Sauvegarde les leads bruts
            raw_leads = _parse_json_from_result(raw_leads_json)
            if raw_leads:
                summary = save_leads(raw_leads, campaign_prompt)
                print(f"\n[Agent 1] Processed {summary['total']} leads ({summary['added']} new, {summary['duplicates']} updated)")
            break

        except Exception as e:
            if _is_rate_limit(e):
                print(f"\n[!] {tier} rate limit")
                if tier != MODELS[-1][0]:
                    wait = 30 if "gemini" in model_id else 5
                    print(f"[!] Waiting {wait}s...")
                    time.sleep(wait)  # longer wait for Gemini
            else:
                raise e

    if not raw_leads_json:
        print("\n[!] Agent 1 failed — all models exhausted")
        return None

    # ── AGENT 2 : Qualification ─────────────────────────
    print("\n[AGENT 2] Starting lead qualification...")
    try:
        qualifier = create_qualifier_agent()
        qualify_task = create_qualify_task(
            qualifier,
            campaign_prompt,
            raw_leads_json
        )

        crew2 = Crew(
            agents=[qualifier],
            tasks=[qualify_task],
            process=Process.sequential,
            verbose=True
        )
        result2 = crew2.kickoff()

        # Met à jour les scores dans SQLite
        qualified_leads = _parse_json_from_result(str(result2))
        if qualified_leads:
            update_lead_qualification(qualified_leads)
            hot   = [l for l in qualified_leads if l.get("segment") == "hot"]
            warm  = [l for l in qualified_leads if l.get("segment") == "warm"]
            cold  = [l for l in qualified_leads if l.get("segment") == "cold"]
            print(f"\n[Agent 2] Results:")
            print(f"  HOT  : {len(hot)} leads")
            print(f"  WARM : {len(warm)} leads")
            print(f"  COLD : {len(cold)} leads")

        return result2

    except Exception as e:
        print(f"\n[!] Agent 2 failed: {str(e)[:100]}")
        return raw_leads_json