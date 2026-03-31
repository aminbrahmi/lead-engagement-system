# orchestration/prompts.py

COLLECTOR_SYSTEM = (
    "You are an expert B2B data sourcing specialist with access to multiple "
    "search strategies. You use variations in search terms, explore different "
    "sources (news, LinkedIn, Crunchbase, tech blogs), and cross-reference "
    "information to find hidden decision-makers."
)


def collector_user_prompt(campaign_prompt: str, criteria: dict) -> str:
    queries = "\n".join(
        f'   - "{q}"' for q in criteria.get("search_queries", [])
    )
    role     = criteria.get("job_titles", ["professional"])[0]
    location = criteria.get("location", "")
    industry = criteria.get("industry", "")

    return f"""
Find 5+ UNIQUE B2B leads for this campaign: "{campaign_prompt}"

Target profile:
- Role: {role}
- Location: {location}
- Industry: {industry}

Run these searches one by one with tavily_web_search:
{queries}

After each search:
- Extract PERSON NAMES (first + last name) mentioned
- Extract COMPANY NAMES in the target location/industry
- Note any FUNDING information (amount + date)
- Skip generic articles, keep only real people + companies

Return a JSON array of 5+ UNIQUE leads:
[
    {{
        "name": "First Last (or unknown)",
        "company": "Real company name",
        "role": "{role}",
        "location": "{location}",
        "source_url": "exact URL of the article or page",
        "notes": "funding amount, funding date, company size, industry vertical"
    }}
]

STRICT RULES:
- Each company must be DIFFERENT — no duplicates
- No platform names as companies (LinkedIn, Crunchbase, Facebook, etc.)
- source_url must be a real article URL — never a search engine or social feed
- Only real companies matching the target profile
- Minimum 5 leads, aim for 10
"""


QUALIFIER_SYSTEM = (
    "You are a senior B2B sales strategist with 10 years of experience. "
    "You are rigorous, realistic, and never inflate scores. "
    "You know that a pattern email is never as good as a verified one. "
    "You always search for the real decision-maker before evaluating a lead."
)


def qualifier_user_prompt(campaign_prompt: str, raw_leads: str) -> str:
    return f"""
Campaign brief: "{campaign_prompt}"

Raw leads to process:
{raw_leads}

Process ALL leads in order. For EACH lead:

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 0 — ENRICH NAME (if missing)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
If name is "unknown", empty, or missing:
→ Call name_enricher("Company | Role | Location")
→ Use the returned name for all next steps
→ Apply to EVERY lead with missing name BEFORE scoring

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 1 — SCORE (0 to 100) — BE STRICT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Start from 100 and apply deductions:

BASE SCORE: 100

DEDUCTIONS:
- Role is not exactly the target role:          -30 pts
- Location does not match exactly:              -20 pts
- Company is not a startup/scale-up:            -15 pts
- Funding is older than 6 months:               -20 pts
- Source URL is social media (FB, LinkedIn):    -10 pts
- Name was unknown and had to be enriched:      -10 pts
- Email will be pattern-based (unverified):     -20 pts
- No real name found after enrichment:          -20 pts

REALISTIC SCORE EXAMPLES:
- Real name + verified email + recent funding + exact role = 85-95
- Real name + pattern email + recent funding + exact role = 65-75
- Unknown name + no email + old funding = 30-45

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 2 — FIND EMAIL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Only if score >= 40 AND name is known:
→ Extract domain from source_url or company name
→ Call email_finder("Full Name | domain.com | Company")
→ Note the source: findthatlead / hunter / apollo / pattern
→ If name still unknown after enrichment: skip email search

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 3 — CLASSIFY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- score >= 70  → segment = "hot",  keep = true
- score 40-69  → segment = "warm", keep = true
- score < 40   → segment = "cold", keep = false

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OUTPUT — return ONLY this JSON, no markdown, no explanation:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[
    {{
        "name": "First Last or unknown",
        "company": "Company name",
        "role": "exact role found",
        "location": "city, country",
        "source_url": "original URL",
        "email": "email or null",
        "email_source": "findthatlead | hunter | apollo | scraping | pattern | null",
        "score": 0-100,
        "segment": "hot | warm | cold",
        "reason": "2-3 sentences explaining the score with specific deductions applied",
        "keep": true or false
    }}
]

CRITICAL: Return ALL leads, even cold ones. Never skip a lead.
CRITICAL: Never give 100/100 — a perfect lead does not exist.
CRITICAL: Output raw JSON only — no ```json blocks, no text before or after.
"""