import os
import json
import re
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

_MODELS = [
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "llama-3.3-70b-versatile",
]

_PROMPT = """Extract structured information from this sales campaign brief.

Campaign brief: "{campaign}"

Return ONLY valid JSON (no markdown fences, no extra text):
{{"job_titles": ["exact title"], "location": "exact location", "industry": "exact industry", "company_type": "startup|scale-up|enterprise", "min_employees": null, "filters": ["filter1"], "search_queries": ["4-8 word query 1", "query 2", "query 3", "query 4", "query 5"]}}"""


# ── Input guard: is this a B2B lead-targeting brief? ─────────────────────────
_ROLE_KW = [
    "ceo", "cto", "cmo", "cfo", "coo", "cio", "vp", "founder", "co-founder",
    "cofounder", "head of", "director", "directeur", "directrice", "manager",
    "décideur", "decideur", "president", "président", "owner", "chief", "c-level",
    "responsable", "gérant", "gerant", "lead ", "leads",
]
_BIZ_KW = [
    "startup", "scale-up", "scaleup", "company", "companies", "entreprise",
    "société", "societe", "b2b", "saas", "fintech", "healthtech", "edtech",
    "proptech", "insurtech", "industry", "industrie", "secteur", "market",
    "marché", "marche", "firm", "business", "funding", "series a", "series b",
    "seed", "raised", "levé", "levée", "leve", "enterprise", "pme", "prospect",
    "prospection", "decision maker", "decision-maker",
]


def is_targeting_brief(prompt: str) -> bool:
    """True if the prompt looks like a B2B prospecting/targeting brief.

    Fast, deterministic keyword pass first (accepts most legitimate briefs with
    no API call). Only genuinely vague prompts trigger a small LLM check, which
    fails OPEN — a guard failure must never block a valid campaign.
    """
    p = (prompt or "").lower()
    if any(k in p for k in _ROLE_KW) or any(k in p for k in _BIZ_KW):
        return True
    try:
        client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        r = client.chat.completions.create(
            model="openai/gpt-oss-20b", temperature=0,
            messages=[{"role": "user", "content":
                "Does this brief describe people or companies to prospect for B2B "
                "sales (a targeting brief with a role, industry or location)? "
                'Answer with a single word: yes or no.\n\nBrief: "%s"' % str(prompt)[:400]}],
        )
        return r.choices[0].message.content.strip().lower().startswith("y")
    except Exception:
        return True   # never block when the guard itself fails


def parse_campaign_prompt(campaign_prompt: str) -> dict:
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    prompt = _PROMPT.format(campaign=campaign_prompt)

    for model in _MODELS:
        try:
            response = client.chat.completions.create(
                model=model,
                temperature=0,
                messages=[{"role": "user", "content": prompt}],
            )
            text  = response.choices[0].message.content.strip()
            text  = re.sub(r'```json|```', '', text).strip()
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                text = match.group(0)
            result = json.loads(text.strip())
            result["search_queries"] = [
                q for q in result.get("search_queries", [])
                if 3 < len(q.split()) <= 10
            ]
            print(f"[Parser] ({model}) {result}")
            return result
        except Exception as e:
            print(f"[Parser] {model} failed: {e}")

    # Hard keyword fallback
    print("[Parser] All models failed — using keyword fallback")
    words    = campaign_prompt.lower().split()
    role     = next(
        (w.rstrip("s").upper() for w in words
         if w.rstrip("s") in ["cto","ceo","cmo","cfo","vp","founder"]),
        "CEO"
    )
    location = next(
        (w.capitalize() for w in words
         if w in ["paris","london","berlin","tunis","dubai","amsterdam","madrid"]),
        ""
    )
    industry = next(
        (w for w in words
         if w in ["healthtech","fintech","saas","ai","tech","edtech","proptech"]),
        "tech"
    )
    return {
        "job_titles":     [role],
        "location":       location,
        "industry":       industry,
        "filters":        [],
        "search_queries": [
            f"{role} {industry} {location} startup funding",
            f"{location} {industry} {role} raised funds",
            f"{role} {industry} startup founder name",
            f"{location} {industry} company {role}",
            f"{industry} startup {role} {location} funding",
        ],
    }