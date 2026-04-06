"""
qualifier_node.py — concurrent enrichment → single LLM scoring call.
"""

import json
import re
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed

from langchain_core.messages import HumanMessage, SystemMessage

from agents.llm_factory import get_qualifier_llm
from tools.name_enricher import NameEnricherTool
from tools.email_finder  import EmailFinderTool
from orchestration.prompts import QUALIFIER_SYSTEM


_name_enricher = NameEnricherTool()
_email_finder  = EmailFinderTool()


def _extract_json_list(text: str) -> list:
    if not text:
        return []
    # Try direct parse first
    try:
        data = json.loads(text.strip())
        if isinstance(data, list):
            return data
    except Exception:
        pass
    # Extract first [...] block
    match = re.search(r'\[.*\]', str(text), re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            pass
    return []


def _resolve_company_domain(company: str) -> str:
    """
    DNS-based company domain resolution.
    NEVER uses source_url — that's a news article, not the company site.
    """
    slug = re.sub(r'[^a-z0-9]', '', company.lower().split()[0]) if company else ""
    if not slug:
        return f"{company.lower().replace(' ','')}.com"
    for tld in [".ai", ".io", ".com", ".de", ".co", ".tech"]:
        domain = slug + tld
        try:
            socket.gethostbyname(domain)
            return domain
        except OSError:
            continue
    return slug + ".com"   # best guess


# ── Step 1: parallel name enrichment ─────────────────────────────────────────

def _enrich_name(lead: dict) -> dict:
    name = lead.get("name", "unknown")
    if name and name.lower() not in ("", "unknown"):
        return lead
    query = f"{lead.get('company','')} | {lead.get('role','CEO')} | {lead.get('location','')}"
    try:
        result = _name_enricher._run(query)
        if result.startswith("Found: "):
            lead = dict(lead)
            lead["name"] = result[7:].strip()
            print(f"[Qualifier] ✓ Name found: {lead['name']} @ {lead.get('company')}")
    except Exception as exc:
        print(f"[Qualifier] Name enrichment failed for {lead.get('company')}: {exc}")
    return lead


def _enrich_names_parallel(leads: list, max_workers: int = 6) -> list:
    unknown = [l for l in leads if not l.get("name") or l["name"].lower() == "unknown"]
    known   = [l for l in leads if l not in unknown]
    if not unknown:
        return leads
    print(f"[Qualifier] Enriching {len(unknown)} unknown names concurrently…")
    result_map = {}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_map = {pool.submit(_enrich_name, l): i for i, l in enumerate(unknown)}
        for future in as_completed(future_map):
            result_map[future_map[future]] = future.result()
    return known + [result_map[i] for i in sorted(result_map)]


# ── Step 2: parallel email finding ───────────────────────────────────────────

def _find_email(lead: dict) -> dict:
    name    = lead.get("name", "")
    company = lead.get("company", "")

    if not name or name.lower() == "unknown":
        return lead

    # ALWAYS resolve domain from company name via DNS — never from source_url
    domain = _resolve_company_domain(company)

    query = f"{name} | {domain} | {company}"
    try:
        raw  = _email_finder._run(query)
        data = json.loads(raw)
        email  = data.get("email")
        source = data.get("source")
        if email:
            lead = dict(lead)
            lead["email"]        = email
            lead["email_source"] = source
            lead["email_conf"]   = data.get("confidence", 0)
            print(f"[Qualifier] ✓ Email found: {email} ({source}) @ {company}")
    except Exception as exc:
        print(f"[Qualifier] Email finding failed for {company}: {exc}")
    return lead


def _find_emails_parallel(leads: list, max_workers: int = 6) -> list:
    scoreable = [l for l in leads if l.get("name", "").lower() not in ("", "unknown")]
    no_name   = [l for l in leads if l not in scoreable]
    if not scoreable:
        return leads
    print(f"[Qualifier] Finding emails for {len(scoreable)} leads concurrently…")
    result_map = {}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_map = {pool.submit(_find_email, l): i for i, l in enumerate(scoreable)}
        for future in as_completed(future_map):
            result_map[future_map[future]] = future.result()
    return [result_map[i] for i in sorted(result_map)] + no_name


# ── Step 3: single LLM scoring call ──────────────────────────────────────────

def _scoring_prompt(campaign_prompt: str, leads: list) -> str:
    leads_json = json.dumps(leads, indent=2, ensure_ascii=False)
    return f"""Campaign brief: "{campaign_prompt}"

Pre-enriched leads (names and emails already resolved):
{leads_json}

Score ALL {len(leads)} leads. Return a JSON array with exactly {len(leads)} objects.

Scoring (0-100, NEVER 100, NEVER give everyone the same score):
  ROLE MATCH    (0-30): exact title match=30, similar title=20, unrelated=0
  LOCATION      (0-20): exact city=20, same country=10, different country=0
  COMPANY FIT   (0-20): right industry+type=20, industry only=12, type only=8, neither=0
  FUNDING       (0-20): funding confirmed within requested period=20, funding exists but period unclear=10, no funding info=0
  DATA QUALITY  (0-10): SMTP-verified email=10, unverified pattern email=4, no email=1, no name=0

STRICT CALIBRATION — apply these ceilings or scores are wrong:
  - Pattern email (unverified): max score = 75, deduct 6 pts from data quality
  - No funding date found: deduct 10 pts from funding score
  - Name was unknown (enriched): deduct 3 pts from data quality
  - Perfect match all criteria = 85-92 (never above 95)
  - Strong match with unverified email = 65-75
  - Good match but missing funding proof = 50-65
  - Scores must VARY across leads — if all leads score the same you are wrong

Segments:
  score >= 75 AND email is SMTP-verified → segment="hot",  keep=true
  score >= 75 AND email is unverified pattern → segment="warm", keep=true
  score 45-74 → segment="warm", keep=true
  score < 45  → segment="cold", keep=false

CRITICAL email trust rules:
  - email_source="findthatlead" or "hunter" or "apollo" or "smtp" → treat as verified
  - email_source="pattern" or "google" or "scraping" → treat as unverified
  - Unverified email: hard cap score at 72, segment="warm"
  - No email at all: hard cap score at 40, segment="cold", keep=false

Return ONLY a raw JSON array — no markdown, no explanation, no text outside the array:
[
  {{
    "name": "...",
    "company": "...",
    "role": "...",
    "location": "...",
    "source_url": "...",
    "email": null or "...",
    "email_source": null or "...",
    "score": 0-99,
    "segment": "hot|warm|cold",
    "reason": "2-3 sentences covering each scoring category",
    "keep": true or false
  }}
]

CRITICAL: Output the JSON array only. No preamble, no explanation."""


# ── Public entry point ────────────────────────────────────────────────────────

def run_qualifier(campaign_prompt: str, raw_leads_json: str) -> str:
    raw_leads = _extract_json_list(raw_leads_json)
    if not raw_leads:
        print("[Qualifier] No leads to qualify.")
        return "[]"

    print(f"[Qualifier] Processing {len(raw_leads)} leads…")

    leads = _enrich_names_parallel(raw_leads)
    leads = _find_emails_parallel(leads)

    llm      = get_qualifier_llm()
    messages = [
        SystemMessage(content=QUALIFIER_SYSTEM),
        HumanMessage(content=_scoring_prompt(campaign_prompt, leads)),
    ]

    # ── Pre-filter: auto-reject leads with no name or no email ──────────────
    scoreable = []
    rejected  = []
    for lead in leads:
        name  = lead.get("name", "unknown") or "unknown"
        email = lead.get("email")
        if name.lower() == "unknown" or not email:
            rejected.append({
                **lead,
                "score":    0,
                "segment":  "cold",
                "reason":   "Auto-rejected: missing name or email.",
                "keep":     False,
            })
            print(f"[Qualifier] ✗ Auto-rejected (no name/email): {lead.get('company')}")
        else:
            scoreable.append(lead)

    if not scoreable:
        print("[Qualifier] No scoreable leads after filtering.")
        return json.dumps(rejected)

    # Re-build prompt with only scoreable leads
    messages = [
        SystemMessage(content=QUALIFIER_SYSTEM),
        HumanMessage(content=_scoring_prompt(campaign_prompt, scoreable)),
    ]

    print(f"[Qualifier] Calling LLM for scoring ({len(scoreable)} leads)…")
    response = llm.invoke(messages)

    content = response.content
    if isinstance(content, list):
        content = "\n".join(
            b["text"] for b in content
            if isinstance(b, dict) and b.get("type") == "text"
        )

    # Debug — show first 300 chars of LLM response
    preview = (content or "")[:300].replace("\n", " ")
    print(f"[Qualifier] LLM raw response preview: {preview}")

    # If LLM wrapped in markdown fences, strip them
    content = re.sub(r'```json|```', '', content or '').strip()

    parsed = _extract_json_list(content)
    if not parsed:
        print("[Qualifier] ⚠ Could not parse LLM response as JSON array.")
        print(f"[Qualifier] Full response:\n{content[:1000]}")
        parsed = []

    # Merge auto-rejected leads back in so storage sees them all
    all_leads = parsed + rejected
    return json.dumps(all_leads)