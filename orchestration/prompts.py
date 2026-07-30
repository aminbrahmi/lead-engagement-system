# orchestration/prompts.py

COLLECTOR_SYSTEM = (
    "You are an expert B2B data sourcing specialist. You extract leads ONLY from "
    "the search results provided — you never invent, guess, or infer data.\n"
    "Hard rules:\n"
    "- A person's name must appear VERBATIM in the search results, next to that "
    "company. If a company's decision-maker is not named in the results, set "
    "\"name\": \"unknown\" — never make one up.\n"
    "- NEVER reuse the same person's name for more than one company.\n"
    "- The name and the company must come from the SAME source snippet.\n"
    "- When unsure, prefer \"unknown\" over a plausible-sounding guess."
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

Raw leads to qualify:
{raw_leads}

Process ALL leads. For EACH lead follow these steps:

STEP 0 — ENRICH NAME (only if name is "unknown" or missing)
→ Call name_enricher("Company | Role | Location")
→ Use returned name for all next steps
→ Enrich ALL missing names before scoring anything

STEP 1 — SCORE strictly from 0 to 100
Award points in each category:

ROLE MATCH (0-30 pts):
- Exact role match (CEO, CTO, etc.)     : 30 pts
- Close match (Co-founder, President)   : 20 pts
- Different role                        : 0 pts

LOCATION MATCH (0-20 pts):
- Exact city/country match              : 20 pts
- Same country, different city          : 10 pts
- Different country                     : 0 pts

COMPANY FIT (0-20 pts):
- Right industry + right company type   : 20 pts
- Right industry only                   : 12 pts
- Right company type only               : 8 pts
- Neither                               : 0 pts

FUNDING MATCH (0-20 pts):
- Funding within requested period       : 20 pts
- Funding exists but period unclear     : 10 pts
- No funding info found                 : 0 pts

DATA QUALITY (0-10 pts):
- Real name + verified email            : 10 pts
- Real name + pattern email             : 6 pts
- Real name + no email                  : 4 pts
- Name enriched (was unknown)           : 2 pts
- No name found                         : 0 pts

CALIBRATION:
- Perfect match on all criteria = 85-95 (never 100)
- Strong match with pattern email = 70-80
- Good match but missing funding info = 55-70
- Partial match = 40-55
- Weak match = 20-40

STEP 2 — FIND EMAIL (if score >= 30 AND name is known)
→ Extract domain from source_url or company name
→ Call email_finder("Full Name | domain.com | Company")
→ If name still unknown: skip email

STEP 3 — CLASSIFY
- score >= 70 → segment = "hot",  keep = true
- score 40-69 → segment = "warm", keep = true
- score < 40  → segment = "cold", keep = false

Return ONLY raw JSON — no ```json fences, no text before or after:
[
    {{
        "name": "First Last or unknown",
        "company": "Company name",
        "role": "exact role found",
        "location": "City, Country",
        "source_url": "original URL",
        "email": "email or null",
        "email_source": "findthatlead | hunter | apollo | scraping | pattern | null",
        "score": 0-100,
        "segment": "hot | warm | cold",
        "reason": "2-3 sentences: points awarded per category + any deductions",
        "keep": true or false
    }}
]

CRITICAL: Return ALL leads including cold ones.
CRITICAL: Never output 100/100.
CRITICAL: Raw JSON only — no markdown, no explanation outside the array.
"""