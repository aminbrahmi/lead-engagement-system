from crewai import Task

def create_collect_task(collector, campaign_prompt: str, criteria: dict):
    queries = "\n".join([
        f'   - "{q}"' for q in criteria.get("search_queries", [])
    ])
    role     = criteria.get("job_titles", ["professional"])[0]
    location = criteria.get("location", "")
    industry = criteria.get("industry", "")

    return Task(
        description=f"""
        Find 5+ UNIQUE B2B leads for this campaign: "{campaign_prompt}"

        Target profile:
        - Role: {role}
        - Location: {location}
        - Industry: {industry}

        Run these searches one by one with TavilySearchTool:
{queries}

        After each search:
        - Extract PERSON NAMES (first + last name) mentioned
        - Extract COMPANY NAMES in the target location/industry
        - Note any FUNDING information
        - Skip generic articles, keep only real people + companies

        Return a JSON array of 5+ UNIQUE leads:
        [
            {{
                "name": "First Last (or unknown)",
                "company": "Real company name",
                "role": "{role}",
                "location": "{location}",
                "source_url": "exact URL",
                "notes": "funding info, company size, industry"
            }}
        ]
        RULES:
        - Each company must be DIFFERENT
        - No platform names as companies (LinkedIn, Crunchbase, etc.)
        - Only real companies matching the target profile
        - Minimum 5 leads
        """,
        expected_output=f"JSON array of 5+ unique {role} leads from {location} {industry} companies",
        agent=collector
    )


def create_qualify_task(qualifier, campaign_prompt: str, raw_leads: str):
    # raw_leads : le JSON string retourné par Agent 1
    # campaign_prompt : le prompt original pour évaluer le fit

    return Task(
        description=f"""
        Campaign brief: "{campaign_prompt}"

        You receive this list of raw leads collected from the web:
        {raw_leads}

        For EACH lead, do the following in order:

        STEP 1 — SCORE the lead from 0 to 100:
        - Role match (is it exactly the right role?): 0-30 pts
        - Location match (correct city/country?): 0-20 pts
        - Company fit (startup/scale-up, right industry?): 0-20 pts
        - Funding recency (recently funded = better): 0-20 pts
        - Data quality (real name + source URL found?): 0-10 pts

        STEP 2 — FIND EMAIL using EmailFinderTool:
        - Extract the company domain from source_url or company name
        - Call EmailFinderTool with format: "Full Name | domain.com"
        - If name is "unknown", skip email search for that lead

        STEP 3 — CLASSIFY:
        - score >= 70 → segment = "hot"
        - score 40-69 → segment = "warm"
        - score < 40  → segment = "cold", keep = false

        Return ONLY a JSON array with ALL leads scored:
        [
            {{
                "name": "...",
                "company": "...",
                "role": "...",
                "location": "...",
                "source_url": "...",
                "email": "found email or null",
                "email_source": "hunter | scraping | pattern | null",
                "score": 0-100,
                "segment": "hot | warm | cold",
                "reason": "short explanation of the score",
                "keep": true or false
            }}
        ]

        IMPORTANT: Return ALL leads scored, even cold ones (keep=false).
        """,
        expected_output="JSON array of all leads with scores, emails, and segments",
        agent=qualifier
    )