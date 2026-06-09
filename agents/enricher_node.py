"""
enricher_node.py — collect rich context for each qualified lead.

For every HOT/WARM lead, runs 4 targeted Tavily searches concurrently,
then uses an LLM to distill the raw results into structured insights.
"""

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from langchain_core.messages import HumanMessage, SystemMessage

from agents.llm_factory import get_enricher_llm


# ── Tavily search ─────────────────────────────────────────────────────────────

def _search(query: str, api_key: str, max_results: int = 3) -> list[dict]:
    try:
        resp = requests.post(
            "https://api.tavily.com/search",
            json={"api_key": api_key, "query": query,
                  "max_results": max_results, "include_answer": True},
            timeout=15,
        )
        data    = resp.json()
        results = data.get("results", [])
        answer  = data.get("answer", "")
        return [{"answer": answer}] + results if answer else results
    except Exception as e:
        print(f"[Enricher] Search error '{query}': {e}")
        return []


def _parallel_searches(queries: list[str], api_key: str) -> str:
    results_map: dict[str, list] = {}
    with ThreadPoolExecutor(max_workers=len(queries)) as pool:
        future_map = {pool.submit(_search, q, api_key): q for q in queries}
        for future in as_completed(future_map):
            results_map[future_map[future]] = future.result()

    lines = []
    for query, results in results_map.items():
        lines.append(f"\n### {query}")
        for r in results:
            if "answer" in r:
                lines.append(f"ANSWER: {r['answer'][:200]}")
            else:
                lines.append(
                    f"- [{r.get('title','')}]({r.get('url','')})\n"
                    f"  {r.get('content','')[:200]}"
                )
    return "\n".join(lines)


# ── LLM distillation ──────────────────────────────────────────────────────────

_SYSTEM = (
    "You are a B2B sales research specialist. "
    "Extract concrete, specific facts from the research text provided. "
    "Use only information present in the research. "
    "For missing fields write exactly: No information found."
)

# Max chars of raw search context to send to the LLM.
# Keeps requests well under Groq's 8K TPM limit per call.
_MAX_CONTEXT_CHARS = 3000


def _distill_prompt(lead: dict, raw_context: str) -> str:
    # Truncate to stay within token limits
    if len(raw_context) > _MAX_CONTEXT_CHARS:
        raw_context = raw_context[:_MAX_CONTEXT_CHARS] + "\n\n[... truncated for brevity]"

    return f"""Lead:
  Name:    {lead.get('name')}
  Company: {lead.get('company')}
  Role:    {lead.get('role')}

Raw research (the ONLY source of truth):
{raw_context}

Rules:
1. Use only facts present in the research above — no invention.
2. If a field has no evidence → write: No information found.
3. Keep each field to 1 sentence max.

Return ONLY raw JSON (no fences, no extra text):
{{
  "recent_news":       "1 sentence or No information found.",
  "person_highlights": "1 sentence or No information found.",
  "company_challenge": "1 sentence or No information found.",
  "tech_stack":        "Key technologies or No information found.",
  "icebreaker":        "One specific real fact for a cold email opener or No information found.",
  "value_angle":       "1 sentence or No information found."
}}"""


def _enrich_one(lead: dict, api_key: str) -> dict:
    name    = lead.get("name", "")
    company = lead.get("company", "")

    print(f"[Enricher] Researching {name} @ {company}…")

    queries = [
        f"{company} funding 2024 OR 2025 startup",
        f'"{name}" {company} CTO OR founder',
        f"{company} product AI platform technology",
        f"{company} {name} news 2025",
    ]

    raw = _parallel_searches(queries, api_key)

    raw_len = len(raw.strip())
    if raw_len < 200:
        print(f"[Enricher] ⚠ Very little content from Tavily ({raw_len} chars) — {company}")

    try:
        llm      = get_enricher_llm()
        response = llm.invoke([
            SystemMessage(content=_SYSTEM),
            HumanMessage(content=_distill_prompt(lead, raw)),
        ])

        content = response.content
        if isinstance(content, list):
            content = "\n".join(
                b["text"] for b in content
                if isinstance(b, dict) and b.get("type") == "text"
            )

        content = re.sub(r'```json|```', '', content or '').strip()

        try:
            insights = json.loads(content)
        except Exception:
            match = re.search(r'\{.*\}', content, re.DOTALL)
            insights = json.loads(match.group(0)) if match else {}

    except Exception as e:
        print(f"[Enricher] ⚠ LLM call failed for {company}: {e}")
        insights = {}

    # Quality check
    empty_markers = {
        "no information found", "n/a", "not found", "none", "",
        "no recent news found.", "no public statements or articles found.",
        "no specific challenge identified.", "no information on technologies used.",
        "no specific detail available.", "no actionable value angle identified.",
    }
    vague_signals = [
        "funding news 2024", "interview article", "challenge problem",
        "ai technology product", "announced funding news",
        "is dealing with a cto", "leverages ai technology",
        "participated in an interview article titled",
    ]

    def _is_real(v: str) -> bool:
        if not isinstance(v, str): return False
        vl = v.strip().lower()
        if vl in empty_markers or len(vl) < 15: return False
        if any(sig in vl for sig in vague_signals): return False
        return True

    real_values = [v for v in insights.values() if _is_real(v)]

    lead = dict(lead)
    lead["insights"] = insights
    if len(real_values) < 2:
        lead["insights_quality"] = "empty"
        print(f"[Enricher] ⚠ Done (no data found): {company}")
    else:
        lead["insights_quality"] = "ok"
        print(f"[Enricher] ✓ Done: {company}")

    return lead


# ── Public entry point ────────────────────────────────────────────────────────

def run_enricher(qualified_leads: list[dict]) -> list[dict]:
    """Enrich only HOT and WARM leads — skip COLD."""
    import os
    api_key    = os.getenv("TAVILY_API_KEY", "")
    to_enrich  = [l for l in qualified_leads if l.get("segment") in ("hot", "warm")]
    cold_leads = [l for l in qualified_leads if l.get("segment") == "cold"]

    if not to_enrich:
        print("[Enricher] No HOT/WARM leads to enrich.")
        return qualified_leads

    print(f"[Enricher] Enriching {len(to_enrich)} leads concurrently…")
    result_map: dict[int, dict] = {}

    # Process max 2 at a time to avoid Groq TPM limits
    with ThreadPoolExecutor(max_workers=2) as pool:
        future_map = {
            pool.submit(_enrich_one, l, api_key): i
            for i, l in enumerate(to_enrich)
        }
        for future in as_completed(future_map):
            idx = future_map[future]
            try:
                result_map[idx] = future.result()
            except Exception as e:
                # Per-lead error handling — don't kill the whole batch
                print(f"[Enricher] ⚠ Lead {idx} failed: {e}")
                lead = dict(to_enrich[idx])
                lead["insights"] = {}
                lead["insights_quality"] = "error"
                result_map[idx] = lead

    enriched = [result_map[i] for i in sorted(result_map)]
    return enriched + cold_leads