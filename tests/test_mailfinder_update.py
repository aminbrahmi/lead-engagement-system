# tests/test_email_finder.py — version finale complète
import sys, os, re, json
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

from tools.email_finder import EmailFinderTool
from memory.storage import get_all_leads, update_email_in_db
from tools.name_enricher import NameEnricherTool
from memory.storage import update_name_in_db

name_tool = NameEnricherTool()
tool = EmailFinderTool()

# ── Charge les leads depuis la base ──────────────────────
db_leads = get_all_leads()
print(f"\n[*] Found {len(db_leads)} leads in DB")

print("\n" + "="*60)
print("  EMAIL FINDER — TEST RESULTS")
print("="*60)

results = []

for lead in db_leads:
    name    = lead["name"]
    company = lead["company"]
    url     = lead.get("source_url", "")

    if name == "unknown" or not name:
        print(f"\n  Enriching name for {company}...")

        enriched = name_tool._run(f"{company} | CTO | ")

        if "Found:" in enriched:
            new_name = enriched.split("Found:")[1].split("|")[0].strip()

            print(f"  → Found name: {new_name}")

            # Update DB
            update_name_in_db(company, new_name)

            name = new_name
        else:
            print(f"  → Name not found, skipping")
            continue

    # Extrait le domaine depuis source_url
    domain = ""
    if url:
        match = re.search(r'https?://(?:www\.)?([^/]+)', url)
        if match:
            d = match.group(1)
            # Skip plateformes
            skip = ["linkedin", "crunchbase", "venturebeat",
                    "angellist", "eu-startups", "trendingtopics",
                    "instagram", "facebook", "twitter"]
            if not any(s in d for s in skip):
                domain = d

    # Fallback domaine depuis nom entreprise
    if not domain:
        domain = re.sub(r'[^a-z0-9]', '', company.lower()) + ".com"

    print(f"\n  Testing : {name} @ {company}")
    print(f"  Domain  : {domain}")
    print(f"  {'─'*50}")

    result = tool._run(f"{name} | {domain}")
    print(f"  Result  : {result}")

    # Détecte méthode et extrait email
    if "FindThatLead" in result:
        method   = "findthatlead"
        verified = True
        print(f"  Method  : FindThatLead ✓ (verified)")
    elif "Apollo" in result:
        method   = "apollo"
        verified = True
        print(f"  Method  : Apollo ✓ (verified)")
    elif "smtp" in result:
        method   = "smtp"
        verified = True
        print(f"  Method  : SMTP verified")
    elif "scraping" in result:
        method   = "scraping"
        verified = False
        print(f"  Method  : Scraping")
    else:
        method   = "pattern"
        verified = False
        print(f"  Method  : Pattern fallback (unverified)")

    email_match = re.search(
        r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
        result
    )
    email = email_match.group(0) if email_match else None

    results.append({
        "name":     name,
        "company":  company,
        "domain":   domain,
        "email":    email,
        "method":   method,
        "verified": verified
    })

# ── Mise à jour des 3 storages ───────────────────────────
print("\n" + "="*60)
print("  STORAGE UPDATE")
print("="*60)

updated_count = 0

for r in results:
    if not r["email"]:
        print(f"  ⚠ {r['name']} — no email found, skipping")
        continue

    # 1. SQLite
    update_email_in_db(r["name"], r["company"], r["email"], r["method"])
    print(f"  ✓ SQLite : {r['name']} → {r['email']} ({r['method']})")
    updated_count += 1

# 2. JSON — sync leads_raw.json
json_path = "data/leads_raw.json"
if os.path.exists(json_path):
    with open(json_path, "r", encoding="utf-8") as f:
        try:
            json_leads = json.load(f)
        except:
            json_leads = []

    # Crée un index name+company → résultat
    email_map = {}
    for r in results:
        if r["email"]:
            key = f"{r['name'].lower()}_{r['company'].lower()}"
            email_map[key] = r

    json_updated = 0
    for entry in json_leads:
        key = f"{entry.get('name','').lower()}_{entry.get('company','').lower()}"
        if key in email_map:
            r = email_map[key]
            entry["email"]          = r["email"]
            entry["email_source"]   = r["method"]
            entry["email_verified"] = r["verified"]
            json_updated += 1

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(json_leads, f, indent=2, ensure_ascii=False)

    print(f"\n  ✓ JSON  : {json_updated} entries updated in leads_raw.json")
else:
    print(f"  ⚠ JSON  : leads_raw.json not found")

# 3. ChromaDB — pas de mise à jour nécessaire
print(f"  ✓ ChromaDB : no update needed (emails not vectorized)")

# ── Résumé final ─────────────────────────────────────────
print("\n" + "="*60)
print("  FINAL SUMMARY")
print("="*60)
print(f"  {'Name':<25} {'Email':<35} {'Verified'}")
print(f"  {'─'*25} {'─'*35} {'─'*8}")
for r in results:
    icon  = "✅" if r["verified"] else "⚠️"
    email = r["email"] or "not found"
    print(f"  {r['name']:<25} {email:<35} {icon}")

print(f"\n  Total updated : {updated_count} leads")
print(f"  JSON synced   : {os.path.exists(json_path)}")