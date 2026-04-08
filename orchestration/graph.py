import json
import re
from typing import TypedDict, Optional

from langgraph.graph import StateGraph, END

from memory.storage import save_leads, update_lead_qualification, save_enrichment_results, init_db
from tools.prompt_parser import parse_campaign_prompt
from agents.collector_node import run_collector
from agents.qualifier_node import run_qualifier
from agents.enricher_node import run_enricher
from agents.writer_node import run_email_generator
from utils.json_utils import extract_json_list


# ── Pipeline state ────────────────────────────────────────────────────────────

class LeadPipelineState(TypedDict):
    campaign_prompt: str
    criteria:        dict
    raw_leads_json:  str
    raw_leads:       list
    save_summary:    dict
    qualified_leads: list
    enriched_leads:  list
    skipped_agents:  list
    error:           Optional[str]


# ── Fallback helpers ──────────────────────────────────────────────────────────

def _promote_raw_leads(raw_leads: list) -> list:
    """When qualifier fails, promote all raw leads to WARM so Agents 3+4 still run."""
    promoted = []
    for lead in raw_leads:
        lead = dict(lead)
        lead.setdefault("score", 50)
        lead.setdefault("segment", "warm")
        lead.setdefault("keep", True)
        lead.setdefault("reason", "Auto-promoted: qualifier was skipped.")
        promoted.append(lead)
    return promoted


# ── Nodes ─────────────────────────────────────────────────────────────────────

def parse_campaign_node(state: LeadPipelineState) -> dict:
    print("\n[*] Parsing campaign brief...")
    criteria = parse_campaign_prompt(state["campaign_prompt"])
    print(f"[*] Criteria: {criteria.get('job_titles')} in {criteria.get('location')}\n")
    return {"criteria": criteria, "error": None, "skipped_agents": []}


def collect_leads_node(state: LeadPipelineState) -> dict:
    print("\n[AGENT 1] Starting lead collection...")
    try:
        raw_leads_json = run_collector(state["campaign_prompt"], state["criteria"])
        print("[Agent 1] Collection complete.")
        return {"raw_leads_json": raw_leads_json}
    except Exception as exc:
        print(f"[!] Agent 1 failed: {exc}")
        return {"raw_leads_json": "", "error": str(exc)}


def save_raw_leads_node(state: LeadPipelineState) -> dict:
    raw_leads = extract_json_list(state.get("raw_leads_json", ""), context="save_raw_leads")
    if not raw_leads:
        print("[Storage] ⚠ No leads parsed from Agent 1 output.")
        return {"raw_leads": [], "save_summary": {}}
    summary = save_leads(raw_leads, state["campaign_prompt"])
    print(f"\n[Agent 1] Processed {summary['total']} leads "
          f"({summary['added']} new, {summary['duplicates']} duplicates)")
    return {"raw_leads": raw_leads, "save_summary": summary}


def qualify_leads_node(state: LeadPipelineState) -> dict:
    print("\n[AGENT 2] Starting lead qualification...")
    try:
        result_json = run_qualifier(state["campaign_prompt"], state["raw_leads_json"])
        qualified   = extract_json_list(result_json, context="qualify_leads")
        if qualified:
            return {"qualified_leads": qualified}
        raise ValueError("Qualifier returned empty list")
    except Exception as exc:
        print(f"[!] Agent 2 failed: {exc}")
        print("[!] FALLBACK → Promoting all raw leads as WARM so pipeline continues.")
        raw_leads = state.get("raw_leads", [])
        if not raw_leads:
            raw_leads = extract_json_list(state.get("raw_leads_json", ""), context="qualifier_fallback")
        promoted = _promote_raw_leads(raw_leads)
        skipped  = state.get("skipped_agents", []) + ["qualifier"]
        return {"qualified_leads": promoted, "skipped_agents": skipped, "error": None}


def save_qualified_leads_node(state: LeadPipelineState) -> dict:
    qualified = state.get("qualified_leads", [])
    if not qualified:
        return {}
    if "qualifier" not in state.get("skipped_agents", []):
        update_lead_qualification(qualified)
    hot  = [l for l in qualified if l.get("segment") == "hot"]
    warm = [l for l in qualified if l.get("segment") == "warm"]
    cold = [l for l in qualified if l.get("segment") == "cold"]
    print(f"\n[Agent 2] Results: HOT={len(hot)}  WARM={len(warm)}  COLD={len(cold)}")
    return {}


def enrich_leads_node(state: LeadPipelineState) -> dict:
    print("\n[AGENT 3] Starting lead enrichment...")
    qualified = state.get("qualified_leads", [])
    if not qualified:
        return {"enriched_leads": []}
    try:
        enriched = run_enricher(qualified)
        done    = sum(1 for l in enriched if l.get("insights_quality") == "ok")
        skipped = sum(1 for l in enriched if l.get("insights_quality") != "ok")
        print(f"[Agent 3] Enrichment done: {done} enriched, {skipped} skipped/empty")
        return {"enriched_leads": enriched}
    except Exception as exc:
        print(f"[!] Agent 3 failed: {exc}")
        print("[!] FALLBACK → Passing leads without insights. Agent 4 will write generic emails.")
        skipped = state.get("skipped_agents", []) + ["enricher"]
        return {"enriched_leads": qualified, "skipped_agents": skipped}


def generate_emails_node(state: LeadPipelineState) -> dict:
    print("\n[AGENT 4] Generating personalized emails...")
    enriched = state.get("enriched_leads", [])
    if not enriched:
        return {}

    skipped_agents = state.get("skipped_agents", [])
    if skipped_agents:
        print(f"[Agent 4] ⚠ Running with degraded data (skipped: {', '.join(skipped_agents)})")

    try:
        with_emails = run_email_generator(enriched, state["campaign_prompt"])
        save_enrichment_results(with_emails)

        generated = [l for l in with_emails if l.get("draft_email")]
        skipped   = [l for l in with_emails if not l.get("draft_email")]
        print(f"\n[Agent 4] Emails: {len(generated)} generated, {len(skipped)} skipped")

        if generated:
            print("\n" + "="*60)
            print("  DRAFT EMAILS SUMMARY")
            print("="*60)
            for lead in generated:
                draft = lead.get("draft_email", {})
                seg   = (lead.get("segment") or "?").upper()
                print(f"  [{seg}] {lead.get('company','?'):<20} → {draft.get('subject','')}")

        return {"enriched_leads": with_emails}
    except Exception as exc:
        print(f"[!] Agent 4 failed: {exc}")
        print("[!] FALLBACK → Saving leads without draft emails.")
        save_enrichment_results(enriched)
        skipped = state.get("skipped_agents", []) + ["writer"]
        return {"skipped_agents": skipped}


# ── Routing ───────────────────────────────────────────────────────────────────

def _after_collect(state: LeadPipelineState) -> str:
    if state.get("error") or not state.get("raw_leads_json"):
        return "abort"
    return "continue"


# ── Graph assembly ────────────────────────────────────────────────────────────

def build_pipeline():
    init_db()

    g = StateGraph(LeadPipelineState)

    g.add_node("parse_campaign",       parse_campaign_node)
    g.add_node("collect_leads",        collect_leads_node)
    g.add_node("save_raw_leads",       save_raw_leads_node)
    g.add_node("qualify_leads",        qualify_leads_node)
    g.add_node("save_qualified_leads", save_qualified_leads_node)
    g.add_node("enrich_leads",         enrich_leads_node)
    g.add_node("generate_emails",      generate_emails_node)

    g.set_entry_point("parse_campaign")
    g.add_edge("parse_campaign", "collect_leads")

    g.add_conditional_edges(
        "collect_leads",
        _after_collect,
        {"continue": "save_raw_leads", "abort": END},
    )

    g.add_edge("save_raw_leads",       "qualify_leads")
    g.add_edge("qualify_leads",        "save_qualified_leads")
    g.add_edge("save_qualified_leads", "enrich_leads")
    g.add_edge("enrich_leads",         "generate_emails")
    g.add_edge("generate_emails",      END)

    return g.compile()


def run_lead_pipeline(campaign_prompt: str) -> dict:
    pipeline = build_pipeline()
    result   = pipeline.invoke({"campaign_prompt": campaign_prompt})

    skipped = result.get("skipped_agents", [])
    if skipped:
        print(f"\n[⚠ DEGRADED RUN] Skipped agents: {', '.join(skipped)}")
        print("   Results may be less accurate. Re-run to retry failed agents.")

    return result