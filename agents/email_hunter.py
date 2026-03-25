# agents/email_hunter.py — version avec stealth mode
import asyncio
import json
import os
import re
import time
from playwright.async_api import async_playwright
from memory.storage import update_email_in_db
from dotenv import load_dotenv
load_dotenv()

FTL_EMAIL    = os.getenv("FTL_EMAIL")
FTL_PASSWORD = os.getenv("FTL_PASSWORD")

async def login_ftl(page):
    print("[FTL] Navigating to login...")

    # Stealth mode — masque les signatures Playwright
    try:
        from playwright_stealth import stealth_async
        await stealth_async(page)
    except ImportError:
        print("[FTL] Warning: playwright-stealth not installed")

    # Headers humains
    await page.set_extra_http_headers({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    })

    # Va sur la home d'abord comme un humain
    await page.goto("https://findthatlead.com", wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(3)

    # Puis va sur le login
    await page.goto("https://app.findthatlead.com/en/users/sign_in",
                    wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(3)

    print(f"[FTL] Page title: {await page.title()}")
    print(f"[FTL] URL: {page.url}")

    # Screenshot pour debug — voir ce que Playwright voit
    await page.screenshot(path="data/ftl_login_page.png")
    print("[FTL] Screenshot saved to data/ftl_login_page.png")

    # Cherche les champs email et password
    try:
        # Essaie plusieurs selectors possibles
        email_selectors = [
            'input[type="email"]',
            'input[name="email"]',
            'input[id="email"]',
            'input[placeholder*="email" i]',
            '#user_email'
        ]
        password_selectors = [
            'input[type="password"]',
            'input[name="password"]',
            'input[id="password"]',
            '#user_password'
        ]

        email_field = None
        for sel in email_selectors:
            el = await page.query_selector(sel)
            if el:
                email_field = sel
                print(f"[FTL] Found email field: {sel}")
                break

        password_field = None
        for sel in password_selectors:
            el = await page.query_selector(sel)
            if el:
                password_field = sel
                print(f"[FTL] Found password field: {sel}")
                break

        if not email_field or not password_field:
            print("[FTL] Fields not found — dumping page content...")
            content = await page.content()
            # Sauvegarde le HTML pour inspection
            with open("data/ftl_login.html", "w", encoding="utf-8") as f:
                f.write(content)
            print("[FTL] HTML saved to data/ftl_login.html")
            return False

        # Tape comme un humain — lettre par lettre avec délai
        await page.click(email_field)
        await asyncio.sleep(0.5)
        await page.type(email_field, FTL_EMAIL, delay=80)
        await asyncio.sleep(0.8)

        await page.click(password_field)
        await asyncio.sleep(0.5)
        await page.type(password_field, FTL_PASSWORD, delay=80)
        await asyncio.sleep(0.8)

        # Clique sur submit
        submit_selectors = [
            'button[type="submit"]',
            'input[type="submit"]',
            'button:has-text("Sign in")',
            'button:has-text("Log in")',
            'button:has-text("Login")'
        ]
        for sel in submit_selectors:
            el = await page.query_selector(sel)
            if el:
                print(f"[FTL] Clicking submit: {sel}")
                await el.click()
                break

        await page.wait_for_load_state("networkidle", timeout=15000)
        await asyncio.sleep(3)

        print(f"[FTL] After login URL: {page.url}")
        await page.screenshot(path="data/ftl_after_login.png")
        print("[FTL] After-login screenshot saved")
        return True

    except Exception as e:
        print(f"[FTL] Login error: {e}")
        return False

async def find_email_on_ftl(page, first_name: str, last_name: str, domain: str) -> dict:
    result = {"email": None, "found": False}

    try:
        # Va sur le prospector
        await page.goto(
            "https://app.findthatlead.com/en/prospector",
            wait_until="domcontentloaded",
            timeout=20000
        )
        await asyncio.sleep(3)

        # Screenshot pour voir la page
        await page.screenshot(path=f"data/ftl_search_{first_name}.png")

        # Cherche les champs
        first_field = await page.query_selector(
            'input[placeholder*="First"], input[name*="first"], input[id*="first"]'
        )
        last_field = await page.query_selector(
            'input[placeholder*="Last"], input[name*="last"], input[id*="last"]'
        )
        domain_field = await page.query_selector(
            'input[placeholder*="domain"], input[placeholder*="company"], input[name*="domain"]'
        )

        if not all([first_field, last_field, domain_field]):
            print(f"[FTL] Form fields not found for {first_name} {last_name}")
            # Sauvegarde HTML pour debug
            html = await page.content()
            with open(f"data/ftl_search.html", "w", encoding="utf-8") as f:
                f.write(html)
            return result

        # Remplit le formulaire
        await first_field.triple_click()
        await first_field.type(first_name, delay=60)
        await asyncio.sleep(0.5)

        await last_field.triple_click()
        await last_field.type(last_name, delay=60)
        await asyncio.sleep(0.5)

        await domain_field.triple_click()
        await domain_field.type(domain, delay=60)
        await asyncio.sleep(0.5)

        # Submit
        submit = await page.query_selector(
            'button[type="submit"], button:has-text("Search"), button:has-text("Find")'
        )
        if submit:
            await submit.click()
            await asyncio.sleep(5)

        # Extrait l'email du résultat
        content = await page.content()
        emails = re.findall(
            r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
            content
        )
        skip = ["findthatlead", "sentry", "noreply", "example",
                "support", "wix", "amazonaws"]
        for email in emails:
            if not any(s in email.lower() for s in skip):
                result["email"] = email
                result["found"] = True
                break

    except Exception as e:
        print(f"[FTL] Search error: {e}")

    return result

async def run_email_hunter(leads: list) -> list:
    results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,  # visible — important pour debug
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage"
            ]
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            locale="en-US"
        )
        page = await context.new_page()

        # Login
        logged_in = await login_ftl(page)
        if not logged_in:
            print("[FTL] Login failed — check data/ftl_login.html and ftl_login_page.png")
            await browser.close()
            return results

        # Cherche chaque lead
        for lead in leads:
            name    = lead.get("name", "")
            company = lead.get("company", "")

            if name == "unknown" or not name:
                continue

            parts      = name.split()
            first_name = parts[0]
            last_name  = parts[-1] if len(parts) > 1 else parts[0]
            domain     = _extract_domain(lead)

            print(f"\n[FTL] Searching: {name} @ {domain}")
            result = await find_email_on_ftl(page, first_name, last_name, domain)

            lead_result = {
                "name":         name,
                "company":      company,
                "domain":       domain,
                "email":        result["email"],
                "email_source": "findthatlead" if result["found"] else None,
                "found":        result["found"]
            }
            results.append(lead_result)

            if result["found"]:
                print(f"[FTL] ✓ {result['email']}")
                update_email_in_db(name, company, result["email"], "findthatlead")
            else:
                print(f"[FTL] ✗ Not found")

            time.sleep(3)

        await browser.close()

    return results

def _extract_domain(lead: dict) -> str:
    url = lead.get("source_url", "")
    if url:
        match = re.search(r'https?://(?:www\.)?([^/]+)', url)
        if match:
            domain = match.group(1)
            skip = ["linkedin", "crunchbase", "techcrunch",
                    "venturebeat", "eu-startups", "trendingtopics",
                    "angellist", "instagram", "facebook"]
            if not any(s in domain for s in skip):
                return domain
    company = lead.get("company", "").lower()
    company = re.sub(r'[^a-z0-9]', '', company)
    return f"{company}.com"

def find_emails_for_leads(leads: list) -> list:
    return asyncio.run(run_email_hunter(leads))