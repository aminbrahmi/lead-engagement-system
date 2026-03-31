# tools/name_enricher.py
import os
import re
import requests
from langchain_core.tools import BaseTool
from typing import Type
from pydantic import BaseModel, Field

class NameEnricherInput(BaseModel):
    query: str = Field(description="Format: 'CompanyName | Role | Location'")

class NameEnricherTool(BaseTool):
    name: str = "name_enricher"
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
        groq_key   = os.getenv("GROQ_API_KEY")

        all_content = []
        for search_query in [
            f"{company} {role} {city}",
            f"{company} founder team",
            f'"{company}" {role} name',
        ][:3]:
            try:
                resp = requests.post(
                    "https://api.tavily.com/search",
                    json={"api_key": tavily_key, "query": search_query,
                          "max_results": 5, "include_answer": True},
                    timeout=10
                )
                data   = resp.json()
                answer = data.get("answer", "")
                if answer:
                    all_content.append(f"ANSWER: {answer}")
                for r in data.get("results", []):
                    all_content.append(
                        f"[{r.get('title','')}]({r.get('url','')}): {r.get('content','')[:400]}"
                    )
            except:
                continue

        if not all_content:
            return f"Name not found for {company} {role}"

        combined = "\n\n".join(all_content[:6])
        name     = self._llm_extract(combined, company, role, groq_key)
        print(f"[NameEnricher] LLM response: '{name}'")

        if name and name != "NOT_FOUND":
            BAD = {"The","Our","This","That","Chief","Technology","Officer",
                   "Executive","Research","Engineer","Not","Found","Arc",
                   "Institute","Career","History","Humboldt","University"}
            words    = name.split()
            is_valid = (len(words) >= 2
                       and all(w[0].isupper() for w in words if w)
                       and not any(w in BAD for w in words)
                       and len(name) >= 6)
            if is_valid:
                return f"Found: {name}"

        return self._regex_fallback(combined, company, role)

    def _llm_extract(self, text: str, company: str, role: str, groq_key: str) -> str:
        if not groq_key:
            return "NOT_FOUND"
        try:
            resp = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {groq_key}",
                         "Content-Type": "application/json"},
                json={
                    "model": "llama-3.3-70b-versatile",
                    "temperature": 0,
                    "max_tokens": 20,
                    "messages": [
                        {"role": "system",
                         "content": "Extract person names from text. Reply with ONLY a full name or NOT_FOUND."},
                        {"role": "user",
                         "content": (
                            f"Find the most relevant technical leader at {company}.\n\n"
                            f"Priority order:\n"
                            f"1. {role}\n"
                            f"2. CTO\n"
                            f"3. Co-founder\n"
                            f"4. Founder\n"
                            f"5. CEO\n\n"
                            f"If {role} is not explicitly mentioned, return the closest match.\n\n"
                            f"{text}\n\n"
                            f"Return ONLY a full name or NOT_FOUND.\n\nName:"
                        )}
                    ]
                },
                timeout=15
            )
            if resp.status_code == 200:
                content = resp.json()["choices"][0]["message"]["content"]
                return content.strip().strip('"').strip("'")
        except Exception as e:
            print(f"[NameEnricher] LLM error: {e}")
        return "NOT_FOUND"

    def _regex_fallback(self, text: str, company: str, role: str) -> str:
        NOT_NAMES = {
            "The","Our","His","Her","This","That","New","Top","About","Berlin",
            "Series","Chief","Open","Source","Long","Term","Memory","Artificial",
            "Intelligence","Technology","Officer","Executive","Research","Engineer",
            "Arc","Institute","Data","Platform","Company","Startup","Founded",
            "Based","German","European","Silicon","Valley","General","Managing",
            "Director","Senior","Junior","Lead","Career","History","Humboldt","University"
        }
        role_keywords = [role, "CTO", "CEO", "co-founder", "founder", "founded by"]
        pattern       = r'\b([A-Z][a-z]{2,15}\s[A-Z][a-z]{2,15})\b'
        candidates    = re.findall(pattern, text)
        scored        = []
        for name in candidates:
            words = name.split()
            if any(w in NOT_NAMES for w in words):
                continue
            if any(len(w) < 3 for w in words):
                continue
            for keyword in role_keywords:
                idx_name = text.lower().find(name.lower())
                idx_role = text.lower().find(keyword.lower())
                if idx_name >= 0 and idx_role >= 0:
                    distance = abs(idx_name - idx_role)
                    if distance < 300:
                        scored.append((name, distance))
                        break
        if scored:
            best = sorted(scored, key=lambda x: x[1])[0][0]
            return f"Found: {best}"
        return f"Name not found for {company} {role}"