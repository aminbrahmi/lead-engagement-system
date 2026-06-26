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

# APIs whose emails are reliable without an SMTP check.
# (Web/Google & scraping are NOT here — they must be SMTP-verified to be trusted.)
TRUSTED_SOURCES = {"findthatlead", "hunter", "apollo", "ftl"}


def is_auto_verified(email_source: str) -> bool:
    return (email_source or "").lower().strip() in TRUSTED_SOURCES


# ──────────────────────────────────────────────────────────────────────────────
# NAME VALIDATION — reject job titles / places / generic junk as person names
# ──────────────────────────────────────────────────────────────────────────────

# Tokens that never appear in a real person's name (lowercased)
_NON_PERSON_TOKENS = {
    "job", "jobs", "career", "careers", "hiring", "vacancy", "vacancies",
    "recruit", "recruitment", "apply", "salary", "remote", "internship",
    "listing", "listings", "opening", "openings", "position", "positions",
    "gmbh", "ltd", "inc", "llc", "corp", "company", "team", "staff",
    "department", "news", "press", "blog", "about", "contact", "support",
    "admin", "info", "startup", "startups", "ventures", "capital", "fund",
    "group", "solutions", "services", "technologies", "unknown", "n/a", "none",
}


def _looks_like_person_name(name: str, location: str = "") -> bool:
    """Heuristic: does this string look like a real person's name?
    Rejects digits, job/listing keywords, and names equal to the location."""
    if not name:
        return False
    n = name.strip()
    low = n.lower()
    if low in ("", "unknown", "n/a", "none"):
        return False
    if any(ch.isdigit() for ch in n):          # names never contain digits
        return False

    words = [w.strip(".,") for w in re.split(r"\s+", low) if w]
    if not words:
        return False
    # Any junk token present → not a person ("Germany job", "Sales team", ...)
    if any(w in _NON_PERSON_TOKENS for w in words):
        return False
    # Name equal to or built around the location ("Germany", "Berlin")
    loc = (location or "").lower().strip()
    if loc and (low == loc or loc in words):
        return False
    return True


def _normalize_bad_names(leads: list) -> list:
    """Set obviously-invalid names to 'unknown' so they go through name
    enrichment (and get auto-rejected if no real name can be found)."""
    out = []
    for lead in leads:
        name = lead.get("name", "")
        if not _looks_like_person_name(name, lead.get("location", "")):
            if name and name.lower() != "unknown":
                print(f"[Qualifier] ⚠ Invalid name '{name}' → unknown ({lead.get('company')})")
            lead = dict(lead)
            lead["name"] = "unknown"
        out.append(lead)
    return out


# ──────────────────────────────────────────────────────────────────────────────
# DOMAIN RESOLUTION
# ──────────────────────────────────────────────────────────────────────────────

def _resolve_company_domain(company: str) -> str:
    comp = (company or "").lower().strip()
    if comp in ("", "unknown", "n/a", "none", "null"):
        return ""   # no real company → never fabricate a domain
    slug = re.sub(r'[^a-z0-9]', '', comp.split()[0]) if comp else ""
    if not slug:
        return ""

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
# COMPANY ENRICHMENT — find the employer from the person's name (reverse lookup)
# ──────────────────────────────────────────────────────────────────────────────

def find_company(lead: dict) -> dict:
    """Find the employer company for a lead that has a name but no company.
    Uses a Tavily web search + LLM extraction. Returns the lead (company filled
    if found, otherwise unchanged)."""
    import os
    import requests

    name = (lead.get("name") or "").strip()
    if not name or name.lower() == "unknown":
        return lead

    api_key = os.getenv("TAVILY_API_KEY", "")
    if not api_key:
        return lead

    role     = (lead.get("role") or "").strip()
    location = (lead.get("location") or "").strip()
    query = f'"{name}" {role} {location} company employer LinkedIn'.strip()

    try:
        resp = requests.post(
            "https://api.tavily.com/search",
            json={"api_key": api_key, "query": query,
                  "max_results": 5, "include_answer": True},
            timeout=15,
        )
        data = resp.json()
        context = data.get("answer", "") or ""
        for r in data.get("results", []):
            context += f"\n{r.get('title','')} — {r.get('content','')[:200]}"
    except Exception as e:
        print(f"[Qualifier] Company search failed for {name}: {e}")
        return lead

    if not context.strip():
        return lead

    from agents.llm_factory import get_qualifier_llm
    from langchain_core.messages import HumanMessage, SystemMessage

    prompt = f"""From the research below, identify the CURRENT employer company of {name}{f' ({role})' if role else ''}.

Research:
{context[:2000]}

Return ONLY the company name — nothing else. If you cannot determine it confidently, return exactly: unknown"""

    try:
        out = get_qualifier_llm().invoke([
            SystemMessage(content="You extract a person's current employer company from research text. Be precise — return only the company name."),
            HumanMessage(content=prompt),
        ]).content
        if isinstance(out, list):
            out = " ".join(b.get("text", "") for b in out if isinstance(b, dict))
        company = (out or "").strip().splitlines()[0].strip().strip('".\'')

        # Validate: must look like a company name, not a sentence or junk
        low = company.lower()
        if (company and low not in ("unknown", "n/a", "none", "")
                and len(company) <= 60 and len(company.split()) <= 6
                and "cannot" not in low and "not " not in low):
            lead = dict(lead)
            lead["company"] = company
            print(f"[Qualifier] [OK] Company found for {name}: {company}")
        else:
            print(f"[Qualifier] [--] Company not determined for {name}")
    except Exception as e:
        print(f"[Qualifier] Company extraction failed for {name}: {e}")

    return lead


# ──────────────────────────────────────────────────────────────────────────────
# STEP 3 — SCORING
# ──────────────────────────────────────────────────────────────────────────────

def _compact_lead(lead: dict) -> dict:
    return {
        "name":           lead.get("name", "unknown"),
        "company":        lead.get("company", ""),
        "role":           lead.get("role", ""),
        "location":       lead.get("location", ""),
        "email":          lead.get("email"),
        "email_source":   lead.get("email_source"),
        "email_verified": bool(lead.get("email_verified")),
        "notes":          (lead.get("notes") or "")[:120],
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


def is_reliable_email(lead: dict) -> bool:
    """An email is reliable if:
      • SMTP-confirmed, OR
      • from a trusted API (FindThatLead / Hunter / Apollo), OR
      • a generic company mailbox (contact@/info@…) — acceptable last resort.
    Guessed nominative patterns / unverified web emails are NOT reliable."""
    if not lead.get("email"):
        return False
    if lead.get("email_verified"):
        return True
    src = (lead.get("email_source") or "").lower().strip()
    if is_auto_verified(src):
        return True
    if src == "generic":
        return True   # contact@/info@ on the company domain — low bounce risk
    return False


def apply_segment_rules(lead: dict) -> dict:
    """Canonical segmentation — single source of truth used at collection AND
    re-enrichment. Only a RELIABLE email can be warm/hot; unverified guesses
    stay cold so we never auto-email a made-up address.
        no email / unreliable email → cold
        reliable + score >= 75       → hot
        reliable + score 45-74       → warm
        reliable + score < 45        → cold
    """
    score = int(lead.get("score") or 0)
    if not is_reliable_email(lead):
        lead["score"]   = min(score, 20 if not lead.get("email") else 40)
        lead["segment"] = "cold"
        return lead
    if score >= 75:
        lead["segment"] = "hot"
    elif score >= 45:
        lead["segment"] = "warm"
    else:
        lead["segment"] = "cold"
    lead["score"] = score
    return lead


# ──────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ──────────────────────────────────────────────────────────────────────────────

def run_qualifier(campaign_prompt: str, raw_leads_json: str) -> str:
    raw_leads = extract_json_list(raw_leads_json, context="Qualifier input")

    if not raw_leads:
        print("[Qualifier] No leads to qualify.")
        return "[]"

    print(f"[Qualifier] Processing {len(raw_leads)} leads…")

    # Reject junk names (job titles, places, generic terms) → 'unknown'
    raw_leads = _normalize_bad_names(raw_leads)

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

            # Carry SMTP/API verification status from the pre-scored leads
            # (the LLM output doesn't include email_verified / email_source).
            meta = {l["email"].lower(): (bool(l.get("email_verified")), l.get("email_source"))
                    for l in scoreable if l.get("email")}
            for l in parsed:
                if l.get("email") and l["email"].lower() in meta:
                    ev, es = meta[l["email"].lower()]
                    l["email_verified"] = ev
                    if not l.get("email_source"):
                        l["email_source"] = es

            all_leads = parsed + rejected
            all_leads = classify_no_email_leads(all_leads)
            all_leads = [apply_segment_rules(l) for l in all_leads]   # strict segmentation

            return json.dumps(all_leads)

    except Exception as exc:
        print(f"[Qualifier] LLM failed: {exc}")

    # ── FALLBACK
    scored = _default_score_leads(scoreable)
    all_leads = scored + rejected
    all_leads = classify_no_email_leads(all_leads)
    all_leads = [apply_segment_rules(l) for l in all_leads]           # strict segmentation

    return json.dumps(all_leads)