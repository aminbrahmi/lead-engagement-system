# tools/email_finder.py
import os
import re
import requests
import smtplib
from crewai.tools import BaseTool
from typing import Type
from pydantic import BaseModel, Field

class EmailFinderInput(BaseModel):
    query: str = Field(description="Format: 'FirstName LastName | domain.com'")

class EmailFinderTool(BaseTool):
    name: str = "email_finder"
    description: str = (
        "Find the professional email of a person given their full name "
        "and company domain. Input format: 'FirstName LastName | domain.com'"
    )
    args_schema: Type[BaseModel] = EmailFinderInput

    def _run(self, query: str) -> str:
        parts = query.split("|")
        if len(parts) < 2:
            return "Invalid format. Use: 'Full Name | domain.com'"

        name   = parts[0].strip()
        domain = parts[1].strip().replace("https://", "").replace("www.", "").strip("/")
        domain = domain.split("/")[0]

        # Method 1 — FindThatLead (verified, 99% confidence)
        ftl = self._findthatlead(name, domain)
        if ftl:
            return f"Email found (FindThatLead, verified): {ftl}"

        # Method 2 — Apollo
        apollo = self._apollo(name, domain)
        if apollo:
            return f"Email found (Apollo, verified): {apollo}"

        # Method 3 — SMTP verify on patterns
        patterns = self._patterns(name, domain)
        verified = self._smtp_verify(patterns)
        if verified:
            return f"Email found (pattern+smtp): {verified}"

        # Method 4 — Scraping contact page
        scraped = self._scrape(domain)
        if scraped:
            return f"Email found (scraping): {scraped}"

        # Method 5 — Pattern fallback
        return f"Possible emails (unverified): {', '.join(patterns[:3])}"

    def _findthatlead(self, name: str, domain: str) -> str:
        token = os.getenv("FTL_TOKEN")
        if not token:
            return None
        try:
            parts = name.split()
            first = parts[0]
            last  = parts[-1] if len(parts) > 1 else parts[0]

            resp = requests.post(
                "https://app-back-qa.findthatlead.com/search/lead",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type":  "application/json",
                    "Origin":        "https://dashboard.findthatlead.com",
                    "Referer":       "https://dashboard.findthatlead.com/"
                },
                json={
                    "get_linkedin_url": True,
                    "name":    first,
                    "surname": last,
                    "domain":  domain,
                    "enrich":  True
                },
                timeout=10
            )

            if resp.status_code == 200:
                data   = resp.json()
                emails = data.get("data", {}).get("emails", [])
                for email_obj in emails:
                    if email_obj.get("valid") and email_obj.get("confidence", 0) >= 70:
                        email = email_obj.get("email")
                        conf  = email_obj.get("confidence")
                        print(f"[FTL] Found: {email} (confidence: {conf}%)")
                        return email
            elif resp.status_code == 401:
                print("[FTL] Token expired — update FTL_TOKEN in .env")

        except Exception as e:
            print(f"[FTL] Error: {e}")
        return None

    def _apollo(self, name: str, domain: str) -> str:
        api_key = os.getenv("APOLLO_API_KEY")
        if not api_key:
            return None
        try:
            parts = name.split()
            first = parts[0]
            last  = parts[-1] if len(parts) > 1 else parts[0]
            resp  = requests.post(
                "https://api.apollo.io/api/v1/people/match",
                headers={
                    "Content-Type": "application/json",
                    "X-Api-Key":    api_key
                },
                json={
                    "first_name": first,
                    "last_name":  last,
                    "domain":     domain,
                    "reveal_personal_emails": False
                },
                timeout=5
            )
            email = resp.json().get("person", {}).get("email")
            if email and "@" in email:
                return email
        except:
            pass
        return None

    def _patterns(self, name: str, domain: str) -> list:
        parts = name.lower().split()
        if len(parts) < 2:
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

    def _scrape(self, domain: str) -> str:
        SKIP = [
            "sentry", "wix", "wixpress", "noreply", "no-reply",
            "mailer", "bounce", "postmaster", "admin",
            "support", "info@", "hello@", "contact@"
        ]
        try:
            for path in ["/contact", "/about", "/team"]:
                resp = requests.get(
                    f"https://{domain}{path}", timeout=5,
                    headers={"User-Agent": "Mozilla/5.0"}
                )
                if resp.status_code == 200:
                    emails = re.findall(
                        r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
                        resp.text
                    )
                    for email in emails:
                        local   = email.split("@")[0]
                        is_hash = len(local) >= 20 and all(
                            c in "0123456789abcdef" for c in local
                        )
                        if is_hash:
                            continue
                        if any(s in email.lower() for s in SKIP):
                            continue
                        return email
        except:
            pass
        return None