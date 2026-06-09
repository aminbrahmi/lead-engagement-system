"""
qualifier_node.py — concurrent enrichment → single LLM scoring call (patched).
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
from utils.json_utils import extract_json_list, detect_truncation


# ──────────────────────────────────────────────────────────────────────────────
# INIT
# ──────────────────────────────────────────────────────────────────────────────

_name_enricher = NameEnricherTool()
_email_finder  = EmailFinderTool()

TRUSTED_SOURCES = {"findthatlead", "hunter", "apollo", "google", "ftl"}


def is_auto_verified(email_source: str) -> bool:
    return (email_source or "").lower().strip() in TRUSTED_SOURCES


# ──────────────────────────────────────────────────────────────────────────────
# DOMAIN RESOLUTION
# ──────────────────────────────────────────────────────────────────────────────

def _resolve_company_domain(company: str) -> str:
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

    return slug + ".com"


# ──────────────────────────────────────────────────────────────────────────────
# STEP 1 — NAME ENRICHMENT
# ──────────────────────────────────────────────────────────────────────────────

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
            print(f"[Qualifier] OK Name found: {lead['name']} @ {lead.get('company')}")
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


# ──────────────────────────────────────────────────────────────────────────────
# STEP 2 — EMAIL FINDING
# ──────────────────────────────────────────────────────────────────────────────

def _find_email(lead: dict) -> dict:
    name    = lead.get("name", "")
    company = lead.get("company", "")

    if not name or name.lower() == "unknown":
        return lead

    domain = _resolve_company_domain(company)
    query  = f"{name} | {domain} | {company}"

    try:
        raw  = _email_finder._run(query)
        data = json.loads(raw)

        email = data.get("email")

        if email:
            lead = dict(lead)
            lead["email"]        = email
            lead["email_source"] = data.get("source")
            lead["email_conf"]   = data.get("confidence", 0)

            # ✅ VERIFIED LOGIC — email_finder returns {"status": "verified"/"unverified"}
            lead["email_verified"] = (
                data.get("status") == "verified"
                or is_auto_verified(lead["email_source"])
            )

            print(f"[Qualifier] OK Email found: {email} ({data.get('source')}) @ {company}")

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


# ──────────────────────────────────────────────────────────────────────────────
# STEP 3 — SCORING
# ──────────────────────────────────────────────────────────────────────────────

def _compact_lead(lead: dict) -> dict:
    return {
        "name":         lead.get("name", "unknown"),
        "company":      lead.get("company", ""),
        "role":         lead.get("role", ""),
        "location":     lead.get("location", ""),
        "email":        lead.get("email"),
        "email_source": lead.get("email_source"),
        "notes":        (lead.get("notes") or "")[:120],
    }


def _scoring_prompt(campaign_prompt: str, leads: list) -> str:
    compact = [_compact_lead(l) for l in leads]
    leads_json = json.dumps(compact, ensure_ascii=False)

    return f"""Campaign: "{campaign_prompt}"

Leads:
{leads_json}

Score each lead 0-99. Criteria: role match(0-30), location(0-20), company fit(0-20), funding(0-20), data quality(0-10).
Unverified/pattern email → max 72, segment=warm. No email → max 40, segment=cold.
Verified email + score>=75 → hot.
Score 45-74 → warm. Score<45 → cold.

Return ONLY JSON array:
[{{"name":"...","company":"...","role":"...","location":"...","source_url":"...","email":"...","email_source":"...","score":N,"segment":"hot|warm|cold","reason":"short","keep":true/false}}]"""


def _default_score_leads(leads: list) -> list:
    scored = []

    for lead in leads:
        lead = dict(lead)

        has_email = bool(lead.get("email"))
        verified  = lead.get("email_verified", False)

        if not has_email:
            lead["score"]   = 30
            lead["segment"] = "cold"
            lead["keep"]    = True
        elif verified:
            lead["score"]   = 75
            lead["segment"] = "hot"
            lead["keep"]    = True
        else:
            lead["score"]   = 55
            lead["segment"] = "warm"
            lead["keep"]    = True

        lead["reason"] = "Default score — LLM unavailable."
        scored.append(lead)

    return scored


# ──────────────────────────────────────────────────────────────────────────────
# PATCH — NO EMAIL CLASSIFICATION
# ──────────────────────────────────────────────────────────────────────────────

def classify_no_email_leads(leads: list) -> list:
    for lead in leads:
        if not lead.get("email"):
            lead["segment"] = "cold"
            lead["status"] = "not_qualified"
            lead["score"] = min(lead.get("score", 0), 20)
            lead["reason"] = (
                (lead.get("reason", "") + " | No email found — not qualified")
                .strip(" |")
            )
            lead["keep"] = True
    return leads


# ──────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ──────────────────────────────────────────────────────────────────────────────

def run_qualifier(campaign_prompt: str, raw_leads_json: str) -> str:
    raw_leads = extract_json_list(raw_leads_json, context="Qualifier input")

    if not raw_leads:
        print("[Qualifier] No leads to qualify.")
        return "[]"

    print(f"[Qualifier] Processing {len(raw_leads)} leads…")

    leads = _enrich_names_parallel(raw_leads)
    leads = _find_emails_parallel(leads)

    # ✅ Only reject if NO NAME
    scoreable = []
    rejected  = []

    for lead in leads:
        name = lead.get("name", "unknown") or "unknown"

        if name.lower() == "unknown":
            rejected.append({
                **lead,
                "score":    0,
                "segment":  "cold",
                "reason":   "Auto-rejected: missing name.",
                "keep":     False,
            })
            print(f"[Qualifier] ✗ Auto-rejected (no name): {lead.get('company')}")
        else:
            scoreable.append(lead)

    if not scoreable:
        print("[Qualifier] No scoreable leads.")
        return json.dumps(rejected)

    # ── LLM scoring
    try:
        messages = [
            SystemMessage(content=QUALIFIER_SYSTEM),
            HumanMessage(content=_scoring_prompt(campaign_prompt, scoreable)),
        ]

        print(f"[Qualifier] Calling LLM for scoring ({len(scoreable)} leads)…")

        response = get_qualifier_llm().invoke(messages)
        content = response.content

        if isinstance(content, list):
            content = "\n".join(
                b["text"] for b in content
                if isinstance(b, dict) and b.get("type") == "text"
            )

        if detect_truncation(content or "", context="Qualifier scoring"):
            print("[Qualifier] ⚠ Truncated response")

        parsed = extract_json_list(content or "", context="Qualifier output")

        if parsed:
            print(f"[Qualifier] ✓ Parsed {len(parsed)} leads")

            all_leads = parsed + rejected
            all_leads = classify_no_email_leads(all_leads)

            return json.dumps(all_leads)

    except Exception as exc:
        print(f"[Qualifier] LLM failed: {exc}")

    # ── FALLBACK
    scored = _default_score_leads(scoreable)
    all_leads = scored + rejected
    all_leads = classify_no_email_leads(all_leads)

    return json.dumps(all_leads)