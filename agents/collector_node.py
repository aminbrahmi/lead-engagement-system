"""
collector_node.py — fast path: parallel Tavily searches → single LLM extraction.

Replaces the ReAct agent loop (5 sequential search + LLM round-trips)
with a ThreadPoolExecutor burst (all searches fire at once) followed by
a single LLM call that extracts leads from the combined results.
Typical time: ~8-15 s instead of ~90 s.
"""

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from langchain_core.messages import HumanMessage, SystemMessage

from agents.llm_factory import get_collector_llm
from orchestration.prompts import COLLECTOR_SYSTEM


# ── Tavily parallel search ────────────────────────────────────────────────────

def _tavily_search(query: str, api_key: str, max_results: int = 5) -> list[dict]:
    """Single Tavily call — returns list of {title, url, content}."""
    try:
        resp = requests.post(
            "https://api.tavily.com/search",
            json={
                "api_key":     api_key,
                "query":       query,
                "max_results": max_results,
                "include_answer": False,
            },
            timeout=12,
        )
        return resp.json().get("results", [])
    except Exception as exc:
        print(f"[Collector] Search error for '{query}': {exc}")
        return []


def _run_parallel_searches(queries: list[str], max_workers: int = 5) -> str:
    """Fire all queries concurrently, return combined text blob."""
    api_key = __import__("os").getenv("TAVILY_API_KEY", "")
    results_by_query: dict[str, list] = {}

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_map = {
            pool.submit(_tavily_search, q, api_key): q for q in queries
        }
        for future in as_completed(future_map):
            q       = future_map[future]
            results = future.result()
            results_by_query[q] = results
            print(f"[Collector] ✓ Search done ({len(results)} results): {q[:60]}")

    # Flatten into a text blob the LLM can parse
    lines: list[str] = []
    for query, results in results_by_query.items():
        lines.append(f"\n### Search: {query}")
        for r in results:
            lines.append(
                f"- [{r.get('title','')}]({r.get('url','')})\n"
                f"  {r.get('content','')[:250]}"
            )
    return "\n".join(lines)


# ── Extraction prompt ─────────────────────────────────────────────────────────

def _extraction_prompt(campaign_prompt: str, criteria: dict, search_blob: str) -> str:
    role     = criteria.get("job_titles", ["professional"])[0]
    location = criteria.get("location", "")

    return f"""Campaign: "{campaign_prompt}"

Search results below. Extract 5-10 UNIQUE real B2B leads.

{search_blob}

Return ONLY a raw JSON array (no markdown fences):
[
  {{
    "name": "First Last (or unknown)",
    "company": "Real company name",
    "role": "{role}",
    "location": "{location}",
    "source_url": "exact article URL (never a search engine)",
    "notes": "funding amount, date, company size, vertical"
  }}
]

Rules:
- Each company must be UNIQUE — no duplicates.
- No platform names as companies (LinkedIn, Crunchbase, etc.).
- source_url must be a real article — never a search/social feed URL.
- Minimum 5 leads, aim for 10.
- Raw JSON only."""


# ── Public entry point ────────────────────────────────────────────────────────

def run_collector(campaign_prompt: str, criteria: dict) -> str:
    queries = criteria.get("search_queries", [campaign_prompt])
    print(f"[Collector] Running {len(queries)} searches in parallel…")

    search_blob = _run_parallel_searches(queries)

    llm = get_collector_llm()
    messages = [
        SystemMessage(content=COLLECTOR_SYSTEM),
        HumanMessage(content=_extraction_prompt(campaign_prompt, criteria, search_blob)),
    ]

    print("[Collector] Calling LLM for extraction…")
    response = llm.invoke(messages)

    # Handle both str and list-of-blocks content (Anthropic / Ollama)
    content = response.content
    if isinstance(content, list):
        content = "\n".join(
            b["text"] for b in content
            if isinstance(b, dict) and b.get("type") == "text"
        )
    return content or ""