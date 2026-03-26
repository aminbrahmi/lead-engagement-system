# tools/contact_finder.py
import os
import re
import requests
import smtplib
import logging
import time
from crewai.tools import BaseTool
from typing import Type
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

class UnifiedEmailInput(BaseModel):
    query: str = Field(description="Format: 'Full Name | domain.com | Company Name'")

class UnifiedEmailFinderTool(BaseTool):
    name: str = "unified_email_finder"
    description: str = (
        "Find professional email using cascade: FTL → Apollo → Google → Scraping → SMTP → Pattern. "
        "Input format: 'Full Name | domain.com | Company Name'"
    )
    args_schema: Type[BaseModel] = UnifiedEmailInput

    def _run(self, query: str) -> str:
        parts = query.split("|")
        name = parts[0].strip()
        
        # Nettoyer le domaine
        domain = ""
        if len(parts) > 1:
            domain_raw = parts[1].strip()
            domain = self._clean_domain(domain_raw)
        
        company = parts[2].strip() if len(parts) > 2 else ""
        
        # Si le domaine est vide, essayer de l'inférer
        if not domain and company:
            domain = self._infer_domain(company)
        
        # Si le nom est "unknown", essayer de trouver le vrai nom d'abord
        if name == "unknown" or name == "":
            name = self._find_real_name(company, domain)
            if not name:
                return f"Contact not found: unknown name for {company}"
        
        print(f"[Unified] Searching for {name} @ {domain}")

        email = None
        e_src = None

        # Méthode 1: FindThatLead (plus fiable)
        if name and domain:
            ftl = self._ftl(name, domain)
            if ftl:
                email = ftl
                e_src = "findthatlead"
                print(f"[Unified] FTL found: {email}")

        # Méthode 2: Apollo
        if not email and name and domain:
            apollo = self._apollo(name, domain)
            if apollo:
                email = apollo
                e_src = "apollo"
                print(f"[Unified] Apollo found: {email}")

        # Méthode 3: Google via Tavily
        if not email:
            google = self._google(name, domain, company)
            if google:
                email = google
                e_src = "google"
                print(f"[Unified] Google found: {email}")

        # Méthode 4: Scraping du site web
        if not email and domain:
            scraped = self._scrape_website(domain)
            if scraped:
                email = scraped
                e_src = "scraping"
                print(f"[Unified] Scraped: {email}")

        # Méthode 5: SMTP verification sur patterns
        if not email and domain and name:
            patterns = self._patterns(name, domain)
            verified = self._smtp_verify(patterns)
            if verified:
                email = verified
                e_src = "smtp"
                print(f"[Unified] SMTP verified: {email}")

        # Méthode 6: Pattern fallback
        if not email and domain and name:
            patterns = self._patterns(name, domain)
            if patterns:
                email = patterns[0]
                e_src = "pattern"
                print(f"[Unified] Pattern fallback: {email}")

        if not email:
            return f"Contact not found for {name} @ {domain}"

        return f"email:{email} | email_source:{e_src}"

    def _clean_domain(self, domain_raw: str) -> str:
        """Nettoie le domaine"""
        domain_raw = domain_raw.replace("https://", "").replace("http://", "")
        domain_raw = domain_raw.replace("www.", "")
        domain_raw = domain_raw.strip("/").split("/")[0]
        return domain_raw.lower()

    def _infer_domain(self, company: str) -> str:
        """Infère un domaine à partir du nom de l'entreprise"""
        import dns.resolver
        
        # Nettoyer le nom
        company_clean = company.lower().strip()
        company_clean = re.sub(r'[^a-z0-9]', '', company_clean)
        
        # TLDs à essayer dans l'ordre de probabilité
        tlds = ['.com', '.ai', '.io', '.co', '.tech', '.app', '.de']
        
        for tld in tlds:
            test_domain = f"{company_clean}{tld}"
            try:
                dns.resolver.resolve(test_domain, 'A')
                print(f"[Unified] Found domain: {test_domain}")
                return test_domain
            except:
                continue
        
        return f"{company_clean}.com"

    def _find_real_name(self, company: str, domain: str) -> str:
        """Trouve le vrai nom du CTO/founder"""
        tavily_key = os.getenv("TAVILY_API_KEY")
        if not tavily_key:
            return None
        
        try:
            resp = requests.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": tavily_key,
                    "query": f"{company} CTO founder name",
                    "max_results": 3,
                    "include_answer": True
                },
                timeout=10
            )
            
            if resp.status_code == 200:
                content = resp.json().get("answer", "")
                for r in resp.json().get("results", []):
                    content += r.get("content", "") + " "
                
                # Chercher des noms
                name_pattern = r'\b([A-Z][a-z]+\s[A-Z][a-z]+)\b'
                names = re.findall(name_pattern, content)
                
                if names:
                    return names[0]
        except:
            pass
        
        return None

    def _ftl(self, name: str, domain: str) -> str:
        """FindThatLead avec retry"""
        token = os.getenv("FTL_TOKEN")
        if not token:
            return None
        
        parts = name.split()
        first = parts[0]
        last = parts[-1] if len(parts) > 1 else parts[0]
        
        for attempt in range(2):
            try:
                resp = requests.post(
                    "https://app-back-qa.findthatlead.com/search/lead",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                        "Origin": "https://dashboard.findthatlead.com",
                        "Referer": "https://dashboard.findthatlead.com/"
                    },
                    json={
                        "get_linkedin_url": True,
                        "name": first,
                        "surname": last,
                        "domain": domain,
                        "enrich": True
                    },
                    timeout=12
                )
                
                if resp.status_code == 200:
                    person = resp.json().get("data", {})
                    
                    for e in person.get("emails", []):
                        if e.get("valid") and e.get("confidence", 0) >= 70:
                            return e["email"]
                    return None
                    
            except requests.exceptions.Timeout:
                print(f"[FTL] Timeout attempt {attempt + 1}")
                if attempt < 1:
                    time.sleep(2)
                continue
            except Exception as e:
                print(f"[FTL] Error: {e}")
                return None
        
        return None

    def _apollo(self, name: str, domain: str) -> str:
        """Apollo.io search"""
        api_key = os.getenv("APOLLO_API_KEY")
        if not api_key:
            return None
        
        try:
            parts = name.split()
            first = parts[0]
            last = parts[-1] if len(parts) > 1 else parts[0]
            
            resp = requests.post(
                "https://api.apollo.io/api/v1/people/match",
                headers={
                    "Content-Type": "application/json",
                    "X-Api-Key": api_key
                },
                json={
                    "first_name": first,
                    "last_name": last,
                    "domain": domain,
                    "reveal_personal_emails": False
                },
                timeout=8
            )
            
            if resp.status_code == 200:
                email = resp.json().get("person", {}).get("email")
                if email and "@" in email:
                    return email
        except Exception as e:
            print(f"[Apollo] Error: {e}")
        
        return None

    def _google(self, name: str, domain: str, company: str) -> str:
        """Google search via Tavily"""
        tavily_key = os.getenv("TAVILY_API_KEY")
        if not tavily_key:
            return None
        
        queries = [
            f'"{name}" email {company}',
            f'"{name}" {domain}',
            f'{company} cto email',
            f'"{name}" contact {domain}'
        ]
        
        for query in queries[:3]:
            try:
                resp = requests.post(
                    "https://api.tavily.com/search",
                    json={
                        "api_key": tavily_key,
                        "query": query,
                        "max_results": 5,
                        "include_answer": True
                    },
                    timeout=10
                )
                
                if resp.status_code == 200:
                    content = resp.json().get("answer", "") + " "
                    for r in resp.json().get("results", []):
                        content += r.get("content", "") + " "
                    
                    emails = re.findall(
                        r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
                        content
                    )
                    
                    SKIP = ["noreply", "sentry", "wix", "example", "support",
                            "info@", "hello@", "tavily", "google", "linkedin"]
                    
                    for email in emails:
                        if any(s in email.lower() for s in SKIP):
                            continue
                        if domain and domain in email:
                            return email
                        # Si on trouve un email plausible, on le garde
                        if not any(s in email.lower() for s in SKIP):
                            return email
                        
            except Exception as e:
                print(f"[Google] Error: {e}")
                continue
        
        return None

    def _scrape_website(self, domain: str) -> str:
        """Scrape le site web pour trouver des emails"""
        SKIP = [
            "sentry", "wix", "wixpress", "noreply", "no-reply",
            "mailer", "bounce", "postmaster", "admin",
            "support", "info@", "hello@", "contact@", "careers@", "jobs@"
        ]
        
        paths = ["/contact", "/about", "/team", "/company", "/leadership"]
        
        for path in paths:
            try:
                url = f"https://{domain}{path}"
                resp = requests.get(url, timeout=5, headers={"User-Agent": "Mozilla/5.0"})
                
                if resp.status_code == 200:
                    emails = re.findall(
                        r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
                        resp.text
                    )
                    
                    for email in emails:
                        local = email.split("@")[0]
                        # Skip les emails hashés
                        is_hash = len(local) >= 20 and all(c in "0123456789abcdef" for c in local)
                        if is_hash:
                            continue
                        # Skip les emails génériques
                        if any(s in email.lower() for s in SKIP):
                            continue
                        # Skip si le domaine ne correspond pas
                        email_domain = email.split("@")[1]
                        if domain not in email_domain:
                            continue
                        return email
            except:
                continue
        
        return None

    def _patterns(self, name: str, domain: str) -> list:
        """Génère des patterns d'emails"""
        parts = name.lower().split()
        if not parts:
            return []
        
        if len(parts) == 1:
            return [f"{parts[0]}@{domain}"]
        
        first, last = parts[0], parts[-1]
        
        patterns = [
            f"{first}.{last}@{domain}",
            f"{first}{last}@{domain}",
            f"{first[0]}{last}@{domain}",
            f"{first[0]}.{last}@{domain}",
            f"{first}@{domain}",
            f"{last}@{domain}",
            f"{first}-{last}@{domain}",
            f"{first}_{last}@{domain}",
        ]
        
        return list(set(patterns))

    def _smtp_verify(self, emails: list) -> str:
        """Vérification SMTP"""
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
                    smtp.connect(mx, 25)
                    smtp.helo("verify.com")
                    smtp.mail("verify@verify.com")
                    code, _ = smtp.rcpt(email)
                    if code == 250:
                        return email
            except:
                continue
        
        return None