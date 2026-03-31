# orchestration/graph.py
import json
import re
from typing import TypedDict, Optional

from langgraph.graph import StateGraph, END

from memory.storage import save_leads, update_lead_qualification, init_db
from tools.prompt_parser import parse_campaign_prompt
from agents.collector_node import run_collector
from agents.qualifier_node import run_qualifier


# ── Shared pipeline state ────────────────────────────────────────────────────

class LeadPipelineState(TypedDict):
    campaign_prompt: str
    criteria:        dict
    raw_leads_json:  str
    raw_leads:       list
    save_summary:    dict
    qualified_leads: list
    error:           Optional[str]


# ── Helper ───────────────────────────────────────────────────────────────────

def _extract_json_list(text: str) -> list:
    match = re.search(r'\[.*\]', str(text), re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            return []
    return []


# ── Node functions ────────────────────────────────────────────────────────────

def parse_campaign_node(state: LeadPipelineState) -> dict:
    print("\n[*] Parsing campaign brief...")
    criteria = parse_campaign_prompt(state["campaign_prompt"])
    print(f"[*] Criteria: {criteria.get('job_titles')} in {criteria.get('location')}\n")
    return {"criteria": criteria, "error": None}


def collect_leads_node(state: LeadPipelineState) -> dict:
    print("\n[AGENT 1] Starting lead collection...")
    try:
        raw_leads_json = run_collector(state["campaign_prompt"], state["criteria"])
        print("[Agent 1] Collection complete.")
        return {"raw_leads_json": raw_leads_json}
    except Exception as exc:
        print(f"[!] Agent 1 failed — all models exhausted: {exc}")
        return {"raw_leads_json": "", "error": str(exc)}


def save_raw_leads_node(state: LeadPipelineState) -> dict:
    raw_leads = _extract_json_list(state.get("raw_leads_json", ""))
    if not raw_leads:
        print("[Storage] ⚠ No leads parsed from Agent 1 output.")
        return {"raw_leads": [], "save_summary": {}}

    summary = save_leads(raw_leads, state["campaign_prompt"])
    print(
        f"\n[Agent 1] Processed {summary['total']} leads "
        f"({summary['added']} new, {summary['duplicates']} duplicates)"
    )
    return {"raw_leads": raw_leads, "save_summary": summary}


def qualify_leads_node(state: LeadPipelineState) -> dict:
    print("\n[AGENT 2] Starting lead qualification...")
    try:
        result_json   = run_qualifier(state["campaign_prompt"], state["raw_leads_json"])
        qualified     = _extract_json_list(result_json)
        return {"qualified_leads": qualified}
    except Exception as exc:
        print(f"[!] Agent 2 failed: {exc}")
        return {"qualified_leads": [], "error": str(exc)}


def save_qualified_leads_node(state: LeadPipelineState) -> dict:
    qualified = state.get("qualified_leads", [])
    if not qualified:
        return {}

    update_lead_qualification(qualified)

    hot  = [l for l in qualified if l.get("segment") == "hot"]
    warm = [l for l in qualified if l.get("segment") == "warm"]
    cold = [l for l in qualified if l.get("segment") == "cold"]
    print(f"\n[Agent 2] Results:")
    print(f"  HOT  : {len(hot)} leads")
    print(f"  WARM : {len(warm)} leads")
    print(f"  COLD : {len(cold)} leads")
    return {}


# ── Routing ───────────────────────────────────────────────────────────────────

def _after_collect(state: LeadPipelineState) -> str:
    """Skip qualification if collection failed or produced nothing."""
    if state.get("error") or not state.get("raw_leads_json"):
        return "abort"
    return "continue"


# ── Graph assembly ────────────────────────────────────────────────────────────

def build_pipeline():
    init_db()

    g = StateGraph(LeadPipelineState)

    g.add_node("parse_campaign",        parse_campaign_node)
    g.add_node("collect_leads",         collect_leads_node)
    g.add_node("save_raw_leads",        save_raw_leads_node)
    g.add_node("qualify_leads",         qualify_leads_node)
    g.add_node("save_qualified_leads",  save_qualified_leads_node)

    g.set_entry_point("parse_campaign")
    g.add_edge("parse_campaign", "collect_leads")

    g.add_conditional_edges(
        "collect_leads",
        _after_collect,
        {"continue": "save_raw_leads", "abort": END},
    )

    g.add_edge("save_raw_leads",       "qualify_leads")
    g.add_edge("qualify_leads",        "save_qualified_leads")
    g.add_edge("save_qualified_leads", END)

    return g.compile()


def run_lead_pipeline(campaign_prompt: str) -> dict:
    pipeline = build_pipeline()
    return pipeline.invoke({"campaign_prompt": campaign_prompt})