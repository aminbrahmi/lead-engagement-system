# tools/email_finder.py

import os
import re
import json
import requests
import logging
import smtplib
from typing import Type, Optional, List, Tuple
from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

# =========================
# INPUT
# =========================
class EmailFinderInput(BaseModel):
    query: str = Field(description="Format: 'Full Name | domain.com | Company'")


# =========================
# TOOL
# =========================
class EmailFinderTool(BaseTool):
    name: str = "email_finder"
    description: str = "Find email using multi-source cascade with SMTP validation"
    args_schema: Type[BaseModel] = EmailFinderInput

    # =========================
    # MAIN
    # =========================
    def _run(self, query: str) -> str:
        name, domain, company = self._parse_query(query)
        session = self._create_session()

        errors = []

        # =========================
        # 1. FTL
        # =========================
        email, conf = self._ftl(session, name, domain)
        if email:
            return self._finalize(email, conf, "findthatlead")

        # =========================
        # 2. HUNTER
        # =========================
        hunter_result = self._hunter(session, name, domain)

        if hunter_result:
            if "error" in hunter_result:
                errors.append(hunter_result["error"])
            else:
                return self._finalize(
                    hunter_result["email"],
                    hunter_result["confidence"],
                    "hunter"
                )

        # =========================
        # 3. APOLLO
        # =========================
        email = self._apollo(session, name, domain)
        if email:
            return self._finalize(email, 85, "apollo")

        # =========================
        # 4. GOOGLE
        # =========================
        email = self._google(session, name, domain, company)
        if email:
            return self._finalize(email, 70, "google")

        # =========================
        # 5. SCRAPING
        # =========================
        email = self._scrape(domain)
        if email:
            return self._finalize(email, 60, "scraping")

        # =========================
        # 6. SMTP via patterns
        # =========================
        patterns = self._patterns(name, domain)
        email = self._smtp_verify(patterns)

        if email:
            return json.dumps({
                "email": email,
                "confidence": 75,
                "source": "smtp",
                "status": "verified"
            })

        # =========================
        # 7. fallback pattern
        # =========================
        if patterns:
            return json.dumps({
                "email": patterns[0],
                "confidence": 40,
                "source": "pattern",
                "status": "guess",
                "warning": "Hunter credits exhausted"
                if "HUNTER_CREDITS_EXCEEDED" in errors else None
            })

        return json.dumps({
            "email": None,
            "confidence": 0,
            "source": None,
            "status": "not_found",
            "errors": errors
        })

    # =========================
    # FINAL VALIDATION
    # =========================
    def _finalize(self, email, confidence, source):
        if not email:
            return None

        valid = self._smtp_verify([email])

        if valid:
            return json.dumps({
                "email": valid,
                "confidence": confidence,
                "source": source,
                "status": "verified"
            })

        return json.dumps({
            "email": email,
            "confidence": max(confidence - 20, 0),
            "source": source,
            "status": "unverified"
        })

    # =========================
    # HELPERS
    # =========================
    def _parse_query(self, query):
        parts = query.split("|")
        name = parts[0].strip()
        domain = parts[1].strip() if len(parts) > 1 else ""
        company = parts[2].strip() if len(parts) > 2 else ""
        domain = self._clean_domain(domain)
        return name, domain, company

    def _clean_domain(self, domain):
        return domain.replace("https://", "").replace("www.", "").split("/")[0]

    def _create_session(self):
        session = requests.Session()
        retries = Retry(total=3, backoff_factor=1,
                        status_forcelist=[429, 500, 502, 503, 504])
        session.mount("https://", HTTPAdapter(max_retries=retries))
        return session

    # =========================
    # FTL
    # =========================
    def _ftl(self, session, name, domain) -> Tuple[Optional[str], int]:
        token = os.getenv("FTL_TOKEN")
        if not token:
            return None, 0

        try:
            first, last = name.split()[0], name.split()[-1]

            resp = session.post(
                "https://app-back-qa.findthatlead.com/search/lead",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json"
                },
                json={
                    "name": first,
                    "surname": last,
                    "domain": domain,
                    "enrich": True
                },
                timeout=15
            )

            if resp.status_code == 200:
                data = resp.json().get("data", {})
                for e in data.get("emails", []):
                    if e.get("valid") and e.get("confidence", 0) >= 70:
                        return e["email"], e["confidence"]

        except Exception as e:
            logger.debug(f"[FTL] {e}")

        return None, 0

    # =========================
    # HUNTER
    # =========================
    def _hunter(self, session, name, domain):
        api_key = os.getenv("HUNTER_API_KEY")
        if not api_key:
            return None

        try:
            parts = name.split()
            first = parts[0]
            last = parts[-1] if len(parts) > 1 else ""

            resp = session.get(
                "https://api.hunter.io/v2/email-finder",
                params={
                    "domain": domain,
                    "first_name": first,
                    "last_name": last,
                    "api_key": api_key
                },
                timeout=10
            )

            data = resp.json()

            if resp.status_code in [401, 429] or data.get("errors"):
                error_msg = data.get("errors", [{}])[0].get("details", "")
                if "limit" in error_msg.lower():
                    return {"error": "HUNTER_CREDITS_EXCEEDED"}

            email = data.get("data", {}).get("email")

            if email:
                return {
                    "email": email,
                    "confidence": data.get("data", {}).get("score", 85)
                }

        except Exception as e:
            logger.debug(f"[Hunter] {e}")

        return None

    # =========================
    # APOLLO
    # =========================
    def _apollo(self, session, name, domain):
        key = os.getenv("APOLLO_API_KEY")
        if not key:
            return None

        try:
            first, last = name.split()[0], name.split()[-1]

            resp = session.post(
                "https://api.apollo.io/api/v1/people/match",
                headers={"X-Api-Key": key},
                json={
                    "first_name": first,
                    "last_name": last,
                    "domain": domain
                },
                timeout=10
            )

            return resp.json().get("person", {}).get("email")

        except:
            return None

    # =========================
    # GOOGLE (FIXED)
    # =========================
    def _google(self, session, name, domain, company):
        key = os.getenv("TAVILY_API_KEY")
        if not key:
            return None

        EMAIL_REGEX = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]+'

        queries = [
            f'"{name}" {domain} email',
            f'"{name}" contact {company}',
            f'{company} email {name}'
        ]

        for q in queries:
            try:
                resp = session.post(
                    "https://api.tavily.com/search",
                    json={"api_key": key, "query": q, "max_results": 5},
                    timeout=10
                )

                content = "".join([r.get("content", "") for r in resp.json().get("results", [])])

                for e in re.findall(EMAIL_REGEX, content):
                    if domain in e:
                        return e

            except:
                continue

        return None

    # =========================
    # SCRAPING (FIXED)
    # =========================
    def _scrape(self, domain):
        EMAIL_REGEX = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]+'

        for path in ["/contact", "/about", "/team"]:
            try:
                resp = requests.get(f"https://{domain}{path}", timeout=5)

                for e in re.findall(EMAIL_REGEX, resp.text):
                    if domain in e:
                        return e

            except:
                continue

        return None

    # =========================
    # PATTERNS
    # =========================
    def _patterns(self, name, domain):
        parts = name.lower().split()
        if len(parts) < 2:
            return []

        first, last = parts[0], parts[-1]

        return list(set([
            f"{first}.{last}@{domain}",
            f"{first}{last}@{domain}",
            f"{first[0]}{last}@{domain}",
            f"{first}@{domain}",
        ]))

    # =========================
    # SMTP VERIFY
    # =========================
    def _smtp_verify(self, emails: List[str]) -> Optional[str]:
        try:
            import dns.resolver
        except ImportError:
            return None

        for email in emails[:3]:
            try:
                domain = email.split("@")[1]
                mx_records = dns.resolver.resolve(domain, "MX")

                if not mx_records:
                    continue

                mx = str(mx_records[0].exchange)

                with smtplib.SMTP(timeout=3) as smtp:
                    smtp.connect(mx)
                    smtp.helo("test.com")
                    smtp.mail("test@test.com")
                    code, _ = smtp.rcpt(email)

                    if code == 250:
                        return email

            except:
                continue

        return None