"""
enricher_node.py — collect rich context for each qualified lead.

For every HOT/WARM lead, runs 4 targeted Tavily searches concurrently:
  1. Recent company news (funding, product, hiring)
  2. Person's public activity (interviews, talks, articles)
  3. Company tech stack / product details
  4. Industry pain points relevant to their space

Then uses an LLM to distill the raw results into structured insights
that the email generator can use directly.
"""

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from langchain_core.messages import HumanMessage, SystemMessage

from agents.llm_factory import get_qualifier_llm


# ── Tavily search ─────────────────────────────────────────────────────────────

def _search(query: str, api_key: str, max_results: int = 5) -> list[dict]:
    try:
        resp = requests.post(
            "https://api.tavily.com/search",
            json={"api_key": api_key, "query": query,
                  "max_results": max_results, "include_answer": True},
            timeout=12,
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
                lines.append(f"ANSWER: {r['answer']}")
            else:
                lines.append(
                    f"- [{r.get('title','')}]({r.get('url','')})\n"
                    f"  {r.get('content','')[:300]}"
                )
    return "\n".join(lines)


# ── LLM distillation ──────────────────────────────────────────────────────────

_SYSTEM = (
    "You are a B2B sales research specialist. "
    "Extract concrete, specific facts from the research text provided. "
    "Use only information present in the research. "
    "For missing fields write exactly: No information found."
)


def _distill_prompt(lead: dict, raw_context: str) -> str:
    return f"""Lead:
  Name:    {lead.get('name')}
  Company: {lead.get('company')}
  Role:    {lead.get('role')}

Raw research (the ONLY source of truth):
{raw_context}

Rules:
1. Use only facts present in the research above — no invention.
2. Do NOT fabricate funding amounts, dates, or investor names not in the research.
3. If a field has no evidence → write: No information found.
4. The icebreaker must reference a real article title, quote, or event from the research.

Return ONLY raw JSON (no fences, no extra text):
{{
  "recent_news":       "1-2 sentences: most recent specific news (funding, product, milestone). If not found: No information found.",
  "person_highlights": "1-2 sentences: something this person said/wrote/did publicly. If not found: No information found.",
  "company_challenge": "1 sentence: main technical or business challenge. If not found: No information found.",
  "tech_stack":        "Key technologies this company uses. If not found: No information found.",
  "icebreaker":        "One specific real fact suitable to open a cold email. If not found: No information found.",
  "value_angle":       "1 sentence: what a vendor could offer based on the challenge. If not found: No information found."
}}"""


def _enrich_one(lead: dict, api_key: str) -> dict:
    name    = lead.get("name", "")
    company = lead.get("company", "")
    role    = lead.get("role", "")

    print(f"[Enricher] Researching {name} @ {company}…")

    queries = [
        # Specific funding / news — include company name + year
        f"{company} raised funding 2024 OR 2025 million startup",
        # Person's public presence — LinkedIn, talks, publications
        f'"{name}" site:linkedin.com OR site:techcrunch.com OR site:eu-startups.com',
        # Company product / tech details
        f"{company} product launch AI platform technology",
        # Recent activity — broader search
        f"{company} {name} news announcement 2025",
    ]

    raw = _parallel_searches(queries, api_key)

    # Debug: show how much content Tavily returned
    raw_len = len(raw.strip())
    if raw_len < 200:
        print(f"[Enricher] ⚠ Very little content from Tavily ({raw_len} chars) — {company}")

    llm      = get_qualifier_llm()
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

    # Flag if research came back empty
    empty_markers = {
        "no information found", "n/a", "not found", "none", "",
        "no recent news found.", "no public statements or articles found.",
        "no specific challenge identified.", "no information on technologies used.",
        "no specific detail available.", "no actionable value angle identified.",
    }
    # Also reject vague sentences that contain the search query verbatim
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

    with ThreadPoolExecutor(max_workers=4) as pool:
        future_map = {
            pool.submit(_enrich_one, l, api_key): i
            for i, l in enumerate(to_enrich)
        }
        for future in as_completed(future_map):
            idx             = future_map[future]
            result_map[idx] = future.result()

    enriched = [result_map[i] for i in sorted(result_map)]
    return enriched + cold_leads