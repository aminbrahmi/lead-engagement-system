"""
collector_node.py — fast path: parallel Tavily searches → single LLM extraction.
"""

import json
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from langchain_core.messages import HumanMessage, SystemMessage

from agents.llm_factory import get_collector_llm
from orchestration.prompts import COLLECTOR_SYSTEM
from utils.json_utils import detect_truncation, extract_json_list


# ── Anti-hallucination guard ──────────────────────────────────────────────────

def _norm(s: str) -> str:
    """Lowercase, strip accents, keep letters/spaces — for robust text matching."""
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z ]+", " ", s.lower()).strip()


def _name_grounded(name: str, blob_norm: str) -> bool:
    """True if the person's name is actually present in the search results.
    Requires every significant token (esp. the surname) to appear — this catches
    names the LLM invented or copied from another company."""
    n = _norm(name)
    if not n or n == "unknown":
        return True
    if n in blob_norm:
        return True
    toks = [t for t in n.split() if len(t) > 1]
    return bool(toks) and all(t in blob_norm for t in toks)


def _validate_leads(content: str, search_blob: str) -> str:
    """Post-process the LLM extraction: drop hallucinated names.

    1. A name that doesn't appear in the search results → 'unknown'.
    2. The same person reused across different companies → 'unknown' on the extras
       (classic LLM hallucination — it latches onto one plausible name).
    The company/email are kept; only the fabricated name is cleared.
    """
    leads = extract_json_list(content, context="Collector validation")
    if not leads:
        return content
    blob_norm = _norm(search_blob)
    seen = {}          # normalized name -> normalized company it first appeared with
    cleared = 0
    for lead in leads:
        name = (lead.get("name") or "").strip()
        if not name or name.lower() == "unknown":
            continue
        if not _name_grounded(name, blob_norm):
            lead["name"] = "unknown"; cleared += 1; continue
        key, company = _norm(name), _norm(lead.get("company"))
        if key in seen and seen[key] != company:
            lead["name"] = "unknown"; cleared += 1      # same person, other company
        else:
            seen[key] = company
    if cleared:
        print(f"[Collector] ⚠ Grounding guard cleared {cleared} hallucinated name(s) → 'unknown'")
    return json.dumps(leads, ensure_ascii=False)


# ── Tavily parallel search ────────────────────────────────────────────────────

def _tavily_search(query: str, api_key: str, max_results: int = 5) -> list[dict]:
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
- The "name" MUST appear verbatim in the search results above, next to that
  company. If no person is named for a company, use "name": "unknown".
- NEVER invent a name, and NEVER reuse the same person for two companies.
- No platform names as companies (LinkedIn, Crunchbase, etc.).
- source_url must be a real article — never a search/social feed URL.
- Minimum 5 leads, aim for 10.
- Raw JSON only."""


# ── Public entry point ────────────────────────────────────────────────────────

def run_collector(campaign_prompt: str, criteria: dict) -> str:
    queries = criteria.get("search_queries", [campaign_prompt])
    print(f"[Collector] Running {len(queries)} searches in parallel…")

    search_blob = _run_parallel_searches(queries)

    if len(search_blob.strip()) < 100:
        print(f"[Collector] ⚠ Very little search content ({len(search_blob)} chars)")

    llm = get_collector_llm()
    messages = [
        SystemMessage(content=COLLECTOR_SYSTEM),
        HumanMessage(content=_extraction_prompt(campaign_prompt, criteria, search_blob)),
    ]

    # Try up to 2 times — LLMs sometimes return empty or malformed on first try
    for attempt in range(1, 3):
        print(f"[Collector] Calling LLM for extraction (attempt {attempt})…")
        response = llm.invoke(messages)

        content = response.content
        if isinstance(content, list):
            content = "\n".join(
                b["text"] for b in content
                if isinstance(b, dict) and b.get("type") == "text"
            )

        # Debug: show what came back
        content_len = len(content or "")
        preview = (content or "")[:300].replace("\n", " ")
        print(f"[Collector] LLM response: {content_len} chars, preview: {preview}")
        
        # Show last 100 chars to see if truncated
        if content_len > 300:
            tail = content[-100:].replace("\n", " ")
            print(f"[Collector] Response tail: ...{tail}")

        if detect_truncation(content or "", context="Collector LLM extraction"):
            print("[Collector] ⚠ Response may be incomplete — attempting recovery.")

        # Quick check: does it contain a JSON array?
        if content and ("[" in content):
            # Try to parse immediately to verify it's valid
            test_parse = extract_json_list(content, context=f"Collector attempt {attempt}")
            if test_parse:
                print(f"[Collector] ✓ Extracted {len(test_parse)} leads")
                return _validate_leads(content, search_blob)
            else:
                print(f"[Collector] ⚠ Found '[' but extraction failed")
                if attempt < 2:
                    continue  # Try again
                else:
                    return content  # Return anyway, let downstream handle it

        print(f"[Collector] ⚠ No JSON array found in response (attempt {attempt})")

    # Return whatever we got — downstream will handle parse failure
    return content or ""