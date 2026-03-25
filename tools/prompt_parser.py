from groq import Groq
import os, json, re
from dotenv import load_dotenv
load_dotenv()

def parse_campaign_prompt(campaign_prompt: str) -> dict:
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    try:
        response = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[{"role": "user", "content": f"""Extract structured information from this sales campaign brief.

Campaign brief: "{campaign_prompt}"

Return ONLY valid JSON:
{{"job_titles": ["exact title"], "location": "exact location", "industry": "exact industry", "company_type": "startup|scale-up|enterprise", "min_employees": null, "filters": ["filter1"], "search_queries": ["4-8 word query 1", "query 2", "query 3", "query 4", "query 5"]}}"""}],
            temperature=0
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
        print(f"[Parser] {result}")
        return result
    except Exception as e:
        print(f"[Parser] Failed: {e} — using fallback")
        words    = campaign_prompt.lower().split()
        role     = next((w.upper() for w in words if w in ["cto","ceo","cmo","cfo","vp","founder"]), "CEO")
        location = next((w.capitalize() for w in words if w in ["paris","london","berlin","tunis","dubai"]), "")
        industry = next((w for w in words if w in ["healthtech","fintech","saas","ai","tech"]), "tech")
        return {
            "job_titles": [role], "location": location, "industry": industry,
            "filters": [],
            "search_queries": [
                f"{role} {industry} {location} startup funding",
                f"{location} {industry} {role} raised funds",
                f"{role} {industry} startup founder name",
                f"{location} {industry} company {role}",
                f"{industry} startup {role} Berlin funding"
            ]
        }