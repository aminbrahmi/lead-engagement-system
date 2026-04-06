import os
import re
import requests
from langchain_core.tools import BaseTool
from typing import Type
from pydantic import BaseModel, Field
from groq import Groq

# For name enrichment: use llama first (high rate limits, fast)
# gpt-oss is saved for the main scoring step
_MODELS = [
    "llama-3.3-70b-versatile",
    "openai/gpt-oss-20b",
    "openai/gpt-oss-120b",
]

_BAD_WORDS = {
    "The","Our","His","Her","This","That","New","Top","About","Berlin",
    "Series","Chief","Open","Source","Long","Term","Memory","Artificial",
    "Intelligence","Technology","Officer","Executive","Research","Engineer",
    "Arc","Institute","Data","Platform","Company","Startup","Founded",
    "Based","German","European","Silicon","Valley","General","Managing",
    "Director","Senior","Junior","Lead","Career","History","Humboldt",
    "University","Customer","Service","Group","Team","Labs","Studio",
    "Solutions","Systems","Digital","Global","International","National",
}


class NameEnricherInput(BaseModel):
    query: str = Field(description="Format: 'CompanyName | Role | Location'")


class NameEnricherTool(BaseTool):
    name: str        = "name_enricher"
    description: str = (
        "Find the real full name of a person given company, role and location. "
        "Input format: 'CompanyName | Role | Location'"
    )
    args_schema: Type[BaseModel] = NameEnricherInput

    def _run(self, query: str) -> str:
        parts   = query.split("|")
        company = parts[0].strip()
        role    = parts[1].strip() if len(parts) > 1 else "CEO"
        city    = parts[2].strip() if len(parts) > 2 else ""

        tavily_key = os.getenv("TAVILY_API_KEY")
        all_content: list[str] = []

        for search_query in [
            f"{company} {role} {city}",
            f"{company} founder team",
            f'"{company}" {role} name',
        ]:
            try:
                resp = requests.post(
                    "https://api.tavily.com/search",
                    json={"api_key": tavily_key, "query": search_query,
                          "max_results": 4, "include_answer": True},
                    timeout=8,
                )
                data = resp.json()
                if data.get("answer"):
                    all_content.append(f"ANSWER: {data['answer']}")
                for r in data.get("results", []):
                    all_content.append(
                        f"[{r.get('title','')}]({r.get('url','')}): "
                        f"{r.get('content','')[:350]}"
                    )
            except Exception:
                continue

        if not all_content:
            return f"Name not found for {company} {role}"

        combined = "\n\n".join(all_content[:5])
        name     = self._llm_extract(combined, company, role)
        print(f"[NameEnricher] LLM response: '{name}'")

        if name and name != "NOT_FOUND":
            extended_bad = _BAD_WORDS | set(company.split())
            words        = name.split()
            # Allow lowercase particles: von, van, de, di, du, der, den, la, le, el
            _PARTICLES = {"von","van","de","di","du","der","den","la","le","el","al","bin"}
            is_valid     = (
                len(words) >= 2
                and all(w[0].isupper() or w in _PARTICLES for w in words if w)
                and not any(w in extended_bad for w in words)
                and len(name) >= 6
            )
            if is_valid:
                return f"Found: {name}"

        return self._regex_fallback(combined, company, role)

    def _llm_extract(self, text: str, company: str, role: str) -> str:
        client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        for model in _MODELS:
            try:
                resp = client.chat.completions.create(
                    model=model,
                    temperature=0,
                    max_tokens=20,
                    messages=[
                        {"role": "system",
                         "content": "Extract person names from text. Reply with ONLY a full name or NOT_FOUND."},
                        {"role": "user",
                         "content": (
                             f"Find the most relevant technical leader at {company}.\n\n"
                             f"Priority: {role} > CTO > Co-founder > Founder > CEO\n\n"
                             f"{text}\n\n"
                             f"Return ONLY a full name or NOT_FOUND.\n\nName:"
                         )},
                    ],
                )
                content = resp.choices[0].message.content
                if content:
                    return content.strip().strip('"').strip("'")
            except Exception as e:
                print(f"[NameEnricher] {model} failed: {e}")
                continue
        return "NOT_FOUND"

    def _regex_fallback(self, text: str, company: str, role: str) -> str:
        extended_bad  = _BAD_WORDS | set(company.split())
        role_keywords = [role, "CTO", "CEO", "co-founder", "founder", "founded by"]
        pattern       = r'\b([A-Z][a-z]{2,15}\s[A-Z][a-z]{2,15})\b'
        candidates    = re.findall(pattern, text)
        scored: list[tuple[str, int]] = []

        for name in candidates:
            words = name.split()
            if any(w in extended_bad for w in words):
                continue
            if any(len(w) < 3 for w in words):
                continue
            for keyword in role_keywords:
                idx_name = text.lower().find(name.lower())
                idx_role = text.lower().find(keyword.lower())
                if idx_name >= 0 and idx_role >= 0 and abs(idx_name - idx_role) < 300:
                    scored.append((name, abs(idx_name - idx_role)))
                    break

        if scored:
            return f"Found: {sorted(scored, key=lambda x: x[1])[0][0]}"
        return f"Name not found for {company} {role}"