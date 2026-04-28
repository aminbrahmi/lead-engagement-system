"""
email_finder.py — exhaustive multi-source email finder.

Instead of returning on the first hit, ALL sources run and collect candidates.
Each candidate gets a confidence score. The highest-confidence SMTP-verified
email wins; if nothing verifies, the highest raw score wins.
"""

import os
import re
import json
import socket
import logging
import smtplib
import requests
from typing import Type, Optional, List
from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

# ── Junk domains — never valid company emails ─────────────────────────────────
_JUNK_DOMAINS = {
    # Social / video
    "youtube.com","twitter.com","x.com","facebook.com","instagram.com",
    "linkedin.com","tiktok.com","vimeo.com",
    # News / tech media / aggregators
    "crunchbase.com","techcrunch.com","techfundingnews.com","heise.de",
    "trendingtopics.eu","vestbee.com","cybernewscentre.com","mezha.net",
    "eu-startups.com","sifted.eu","wired.com","forbes.com",
    "businessinsider.com","venturebeat.com","zdnet.com","cnet.com",
    "thenextweb.com","siliconrepublic.com","techradar.com","theverge.com",
    "musicbusinessworldwide.com","billboard.com","variety.com",
    "reuters.com","bloomberg.com","ft.com","wsj.com","nytimes.com",
    "handelsblatt.com","gruenderszene.de","deutsche-startups.de",
    # Events / community
    "hyperight.com","eventbrite.com","meetup.com","lu.ma",
    # Publishing / hosting
    "medium.com","substack.com","wordpress.com","ghost.io",
    "github.com","gitlab.com","notion.so","airtable.com",
}


class EmailFinderInput(BaseModel):
    query: str = Field(description="Format: 'Full Name | domain.com | Company'")


class EmailFinderTool(BaseTool):
    name: str        = "email_finder"
    description: str = "Exhaustive multi-source email finder — tries everything, returns best result"
    args_schema: Type[BaseModel] = EmailFinderInput

    def _run(self, query: str) -> str:
        name, domain, company = self._parse_query(query)

        # Resolve real company domain if the passed domain is junk or missing
        if not domain or domain in _JUNK_DOMAINS:
            domain = self._resolve_company_domain(company)

        if not domain:
            return json.dumps({"email": None, "confidence": 0,
                               "source": None, "status": "no_domain"})

        session    = self._make_session()
        candidates = []   # list of {email, confidence, source, verified}

        print(f"[EmailFinder] Searching all sources for {name} @ {domain}…")

        # ── 1. FindThatLead ───────────────────────────────────────────────────
        email, conf = self._ftl(session, name, domain)
        if email:
            candidates.append({"email": email, "confidence": conf,
                                "source": "findthatlead"})
            print(f"[EmailFinder]  FTL      → {email} ({conf}%)")

        # ── 2. Hunter ─────────────────────────────────────────────────────────
        result = self._hunter(session, name, domain)
        if result and "email" in result:
            candidates.append({"email": result["email"],
                                "confidence": result["confidence"],
                                "source": "hunter"})
            print(f"[EmailFinder]  Hunter   → {result['email']} ({result['confidence']}%)")

        # ── 3. Apollo ─────────────────────────────────────────────────────────
        email = self._apollo(session, name, domain)
        if email:
            candidates.append({"email": email, "confidence": 85, "source": "apollo"})
            print(f"[EmailFinder]  Apollo   → {email}")

        # ── 4. Tavily / Google search ─────────────────────────────────────────
        emails = self._tavily(session, name, domain, company)
        for e in emails:
            candidates.append({"email": e, "confidence": 70, "source": "google"})
            print(f"[EmailFinder]  Tavily   → {e}")

        # ── 5. Website scraping ───────────────────────────────────────────────
        emails = self._scrape(domain)
        for e in emails:
            candidates.append({"email": e, "confidence": 60, "source": "scraping"})
            print(f"[EmailFinder]  Scrape   → {e}")

        # ── 6. Pattern generation ─────────────────────────────────────────────
        patterns = self._patterns(name, domain)
        for e in patterns:
            candidates.append({"email": e, "confidence": 35, "source": "pattern"})
        if patterns:
            print(f"[EmailFinder]  Patterns → {patterns}")

        # ── Deduplicate, filter junk ──────────────────────────────────────────
        seen       = set()
        clean      = []
        for c in candidates:
            e = c["email"].lower().strip()
            d = e.split("@")[-1] if "@" in e else ""
            if e in seen or d in _JUNK_DOMAINS:
                continue
            seen.add(e)
            c["email"] = e
            clean.append(c)

        if not clean:
            return json.dumps({"email": None, "confidence": 0,
                               "source": None, "status": "not_found"})

        # ── SMTP verify all candidates (highest confidence first) ─────────────
        clean.sort(key=lambda x: x["confidence"], reverse=True)

        # Only SMTP-verify top 5 by confidence — patterns are low priority
        to_verify = clean[:5]
        print(f"[EmailFinder] SMTP verifying {len(to_verify)}/{len(clean)} candidates…")
        for c in clean:
            c["verified"] = False   # default
        for c in to_verify:
            verified = self._smtp_verify(c["email"])
            c["verified"] = verified
            status = "✅ verified" if verified else "⚠ unverified"
            print(f"[EmailFinder]   {c['email']} [{c['source']}] → {status}")

        # ── Pick winner: verified first, then highest confidence ──────────────
        verified_candidates = [c for c in clean if c["verified"]]
        winner = (
            max(verified_candidates, key=lambda x: x["confidence"])
            if verified_candidates
            else max(clean, key=lambda x: x["confidence"])
        )

        return json.dumps({
            "email":      winner["email"],
            "confidence": winner["confidence"],
            "source":     winner["source"],
            "status":     "verified" if winner.get("verified") else "unverified",
        })

    # ── Domain resolution ─────────────────────────────────────────────────────

    def _resolve_company_domain(self, company: str) -> str:
        """Try common TLDs via DNS; return first that resolves."""
        slug = re.sub(r'[^a-z0-9]', '', company.lower().split()[0]) if company else ""
        if not slug:
            return ""
        for tld in [".ai", ".io", ".com", ".de", ".co", ".tech"]:
            domain = slug + tld
            try:
                socket.gethostbyname(domain)
                print(f"[EmailFinder] Resolved company domain: {domain}")
                return domain
            except OSError:
                continue
        return slug + ".com"

    # ── Session ───────────────────────────────────────────────────────────────

    def _make_session(self):
        s       = requests.Session()
        retries = Retry(total=3, backoff_factor=1,
                        status_forcelist=[429, 500, 502, 503, 504])
        s.mount("https://", HTTPAdapter(max_retries=retries))
        return s

    # ── Parse query ───────────────────────────────────────────────────────────

    def _parse_query(self, query: str):
        parts   = query.split("|")
        name    = parts[0].strip()
        domain  = parts[1].strip() if len(parts) > 1 else ""
        company = parts[2].strip() if len(parts) > 2 else ""
        domain  = domain.replace("https://","").replace("http://","") \
                        .replace("www.","").split("/")[0].strip()
        return name, domain, company

    # ── Source 1: FindThatLead ────────────────────────────────────────────────

    def _ftl(self, session, name: str, domain: str):
        token = os.getenv("FTL_TOKEN")
        if not token:
            return None, 0
        try:
            parts = name.split()
            first, last = parts[0], parts[-1]
            resp = session.post(
                "https://app-back-qa.findthatlead.com/search/lead",
                headers={"Authorization": f"Bearer {token}",
                         "Content-Type": "application/json"},
                json={"name": first, "surname": last,
                      "domain": domain, "enrich": True},
                timeout=45,
            )
            if resp.status_code == 200:
                data = resp.json().get("data", {})
                # Return the highest-confidence valid email
                best = max(
                    (e for e in data.get("emails", []) if e.get("valid")),
                    key=lambda e: e.get("confidence", 0),
                    default=None,
                )
                if best and best.get("confidence", 0) >= 60:
                    return best["email"], best["confidence"]
        except Exception as e:
            logger.debug(f"[FTL] {e}")
        return None, 0

    # ── Source 2: Hunter ──────────────────────────────────────────────────────

    def _hunter(self, session, name: str, domain: str):
        api_key = os.getenv("HUNTER_API_KEY")
        if not api_key:
            return None
        try:
            parts = name.split()
            first, last = parts[0], parts[-1] if len(parts) > 1 else ""
            resp = session.get(
                "https://api.hunter.io/v2/email-finder",
                params={"domain": domain, "first_name": first,
                        "last_name": last, "api_key": api_key},
                timeout=30,
            )
            data  = resp.json()
            email = data.get("data", {}).get("email")
            if email:
                return {"email": email,
                        "confidence": data.get("data", {}).get("score", 80)}
        except Exception as e:
            logger.debug(f"[Hunter] {e}")
        return None

    # ── Source 3: Apollo ──────────────────────────────────────────────────────

    def _apollo(self, session, name: str, domain: str) -> Optional[str]:
        key = os.getenv("APOLLO_API_KEY")
        if not key:
            return None
        try:
            parts = name.split()
            resp  = session.post(
                "https://api.apollo.io/api/v1/people/match",
                headers={"X-Api-Key": key},
                json={"first_name": parts[0], "last_name": parts[-1],
                      "domain": domain},
                timeout=30,
            )
            return resp.json().get("person", {}).get("email")
        except Exception:
            return None

    # ── Source 4: Tavily search ───────────────────────────────────────────────

    def _tavily(self, session, name: str, domain: str, company: str) -> List[str]:
        key = os.getenv("TAVILY_API_KEY")
        if not key:
            return []
        EMAIL_RE = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]+'
        found    = []
        queries  = [
            f'"{name}" {domain} email contact',
            f'"{name}" {company} email',
            f'site:{domain} contact email',
        ]
        for q in queries:
            try:
                resp    = session.post(
                    "https://api.tavily.com/search",
                    json={"api_key": key, "query": q, "max_results": 7},
                    timeout=20,
                )
                content = " ".join(r.get("content", "")
                                   for r in resp.json().get("results", []))
                for e in re.findall(EMAIL_RE, content):
                    d = e.split("@")[-1].lower()
                    if d == domain and e not in found:
                        found.append(e)
            except Exception:
                continue
        return found

    # ── Source 5: Website scraping ────────────────────────────────────────────

    def _scrape(self, domain: str) -> List[str]:
        EMAIL_RE = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]+'
        found    = []
        paths    = ["/contact", "/about", "/team", "/imprint",
                    "/impressum", "/kontakt", "/"]
        headers  = {"User-Agent": "Mozilla/5.0"}
        for path in paths:
            try:
                resp = requests.get(f"https://{domain}{path}",
                                    headers=headers, timeout=10)
                for e in re.findall(EMAIL_RE, resp.text):
                    d = e.split("@")[-1].lower()
                    if d == domain and e not in found:
                        found.append(e)
            except Exception:
                continue
        return found

    # ── Source 6: Pattern generation ─────────────────────────────────────────

    def _patterns(self, name: str, domain: str) -> List[str]:
        parts = name.lower().split()
        if len(parts) < 2:
            return []
        first, last = parts[0], parts[-1]
        return list(dict.fromkeys([
            f"{first}.{last}@{domain}",
            f"{first}{last}@{domain}",
            f"{first[0]}.{last}@{domain}",
            f"{first[0]}{last}@{domain}",
            f"{first}@{domain}",
            f"{last}@{domain}",
        ]))

    # ── SMTP verification ─────────────────────────────────────────────────────

    def _smtp_verify(self, email: str) -> bool:
        """
        Full SMTP handshake to check if the mailbox exists.
        Returns True if server responds 250 to RCPT TO.
        """
        try:
            import dns.resolver
            domain     = email.split("@")[1]
            mx_records = dns.resolver.resolve(domain, "MX")
            if not mx_records:
                return False
            # Try all MX records in priority order
            mx_hosts = sorted(mx_records, key=lambda r: r.preference)
            for mx_record in mx_hosts[:3]:
                mx = str(mx_record.exchange).rstrip(".")
                try:
                    with smtplib.SMTP(timeout=8) as smtp:
                        smtp.connect(mx, 25)
                        smtp.helo("verify.local")
                        smtp.mail("noreply@verify.local")
                        code, _ = smtp.rcpt(email)
                        if code == 250:
                            return True
                        if code == 550:
                            return False   # definitely doesn't exist
                except Exception:
                    continue
        except Exception:
            pass
        return False