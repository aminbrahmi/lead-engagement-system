import os
import re
import requests
import smtplib
from crewai.tools import BaseTool
from typing import Type
from pydantic import BaseModel, Field

class ContactFinderInput(BaseModel):
    query: str = Field(description="Format: 'Full Name | domain.com | Company Name'")

class ContactFinderTool(BaseTool):
    name: str = "contact_finder"
    description: str = (
        "Find email AND phone using cascade: FTL → Google → SMTP → Pattern. "
        "Input format: 'Full Name | domain.com | Company Name'"
    )
    args_schema: Type[BaseModel] = ContactFinderInput

    def _run(self, query: str) -> str:
        parts   = query.split("|")
        name    = parts[0].strip()
        domain  = parts[1].strip().replace("https://","").replace("www.","").strip("/").split("/")[0] if len(parts)>1 else ""
        company = parts[2].strip() if len(parts) > 2 else ""

        email  = None
        phone  = None
        e_src  = None
        p_src  = None

        # Step 1 — FTL
        if name and name != "unknown":
            ftl = self._ftl(name, domain)
            if ftl.get("email"):
                email = ftl["email"]
                e_src = "findthatlead"
            if ftl.get("phone"):
                phone = ftl["phone"]
                p_src = "findthatlead"

        # Step 2 — Google Search
        google = self._google(name, domain, company)
        if not email and google.get("email"):
            email = google["email"]
            e_src = "google"
        if not phone and google.get("phone"):
            phone = google["phone"]
            p_src = "google"

        # Step 3 — SMTP verify
        if not email and domain and name and name != "unknown":
            patterns = self._patterns(name, domain)
            verified = self._smtp_verify(patterns)
            if verified:
                email = verified
                e_src = "smtp"

        # Step 4 — Pattern fallback
        if not email and domain and name and name != "unknown":
            patterns = self._patterns(name, domain)
            if patterns:
                email = patterns[0]
                e_src = "pattern"

        if not email and not phone:
            return f"Contact not found for {name}"

        parts_out = []
        if email:
            parts_out.append(f"email:{email}")
            parts_out.append(f"email_source:{e_src}")
        if phone:
            parts_out.append(f"phone:{phone}")
            parts_out.append(f"phone_source:{p_src}")
        return " | ".join(parts_out)

    def _ftl(self, name: str, domain: str) -> dict:
        token = os.getenv("FTL_TOKEN")
        if not token:
            return {}
        try:
            parts = name.split()
            first = parts[0]
            last  = parts[-1] if len(parts) > 1 else parts[0]
            resp  = requests.post(
                "https://app-back-qa.findthatlead.com/search/lead",
                headers={"Authorization": f"Bearer {token}",
                         "Content-Type": "application/json",
                         "Origin": "https://dashboard.findthatlead.com",
                         "Referer": "https://dashboard.findthatlead.com/"},
                json={"get_linkedin_url": True, "name": first,
                      "surname": last, "domain": domain, "enrich": True},
                timeout=10
            )
            if resp.status_code == 200:
                person = resp.json().get("data", {})
                result = {}
                for e in person.get("emails", []):
                    if e.get("valid") and e.get("confidence", 0) >= 70:
                        result["email"] = e["email"]
                        break
                phones = person.get("phones", [])
                if phones:
                    result["phone"] = phones[0].get("phone")
                return result
            elif resp.status_code == 401:
                print("[FTL] Token expired")
        except Exception as e:
            print(f"[FTL] Error: {e}")
        return {}

    def _google(self, name: str, domain: str, company: str) -> dict:
        tavily_key = os.getenv("TAVILY_API_KEY")
        if not tavily_key:
            return {}
        result  = {"email": None, "phone": None}
        queries = [
            f'"{name}" "@{domain}"',
            f'"{name}" contact email {company}',
            f'"{name}" phone {company}',
        ]
        for query in queries[:3]:
            try:
                resp = requests.post(
                    "https://api.tavily.com/search",
                    json={"api_key": tavily_key, "query": query,
                          "max_results": 5, "include_answer": True},
                    timeout=10
                )
                content = resp.json().get("answer", "") + " "
                for r in resp.json().get("results", []):
                    content += r.get("content", "") + " "

                if not result["email"]:
                    emails = re.findall(
                        r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', content)
                    SKIP = ["noreply","sentry","wix","example","support",
                            "info@","hello@","tavily","google","linkedin"]
                    for email in emails:
                        if not any(s in email.lower() for s in SKIP):
                            if domain and domain in email:
                                result["email"] = email
                                break
                            elif not result["email"]:
                                result["email"] = email

                if not result["phone"]:
                    for pat in [
                        r'\+\d{1,3}[\s\-\.]?\(?\d{2,4}\)?[\s\-\.]?\d{2,4}[\s\-\.]?\d{2,8}',
                        r'\+49[\s\-\.]?\d{2,4}[\s\-\.]?\d{4,8}',
                    ]:
                        phones = re.findall(pat, content)
                        if phones:
                            result["phone"] = phones[0].strip()
                            break

                if result["email"] and result["phone"]:
                    break
            except:
                continue
        return result

    def _patterns(self, name: str, domain: str) -> list:
        parts = name.lower().split()
        if not parts:
            return []
        if len(parts) == 1:
            return [f"{parts[0]}@{domain}"]
        first, last = parts[0], parts[-1]
        return [
            f"{first}.{last}@{domain}",
            f"{first}@{domain}",
            f"{first[0]}.{last}@{domain}",
            f"{first}{last}@{domain}",
            f"{last}@{domain}",
        ]

    def _smtp_verify(self, emails: list) -> str:
        try:
            import dns.resolver
        except ImportError:
            return None
        for email in emails:
            domain = email.split("@")[1]
            try:
                mx = str(dns.resolver.resolve(domain, "MX")[0].exchange)
                with smtplib.SMTP(timeout=5) as smtp:
                    smtp.connect(mx, 25)
                    smtp.helo("verify.com")
                    smtp.mail("verify@verify.com")
                    code, _ = smtp.rcpt(email)
                    if code == 250:
                        return email
            except:
                continue
        return None