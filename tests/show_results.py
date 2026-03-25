# tests/show_results.py
# Affiche tous les leads qualifiés avec leurs scores et emails
# de façon lisible dans le terminal

import sqlite3
import json
import os

DB_PATH    = "data/leads.db"
EMAIL_PATH = "data/emails_generated.json"

print("\n" + "="*65)
print("  LEADS QUALIFIÉS — SCORES & EMAILS")
print("="*65)

# Charge les leads depuis SQLite
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
leads = conn.execute(
    "SELECT * FROM leads ORDER BY score DESC"
).fetchall()
conn.close()

# Charge les emails générés si disponibles
emails_map = {}
if os.path.exists(EMAIL_PATH):
    with open(EMAIL_PATH, "r", encoding="utf-8") as f:
        emails = json.load(f)
    for e in emails:
        emails_map[e.get("lead_name", "")] = e

# Affiche chaque lead
for i, lead in enumerate(leads, 1):
    score   = lead["score"]
    segment = lead["segment"] or "unknown"
    status  = lead["status"]
    name    = lead["name"]
    company = lead["company"]
    email   = lead["email"] or "not found"

    # Couleur selon segment
    seg_icon = {"hot": "🔥", "warm": "🟡", "cold": "🧊"}.get(segment, "⚪")

    print(f"\n{i}. {seg_icon} {name} @ {company}")
    print(f"   Score   : {score}/100 — {segment.upper()}")
    print(f"   Status  : {status}")
    print(f"   Role    : {lead['role']} | {lead['location']}")
    print(f"   Email   : {email}")
    if lead["reason"]:
        print(f"   Reason  : {lead['reason']}")
    if lead["source_url"]:
        print(f"   Source  : {lead['source_url'][:70]}")

    # Affiche l'email généré si disponible
    if name in emails_map:
        e = emails_map[name]
        print(f"\n   📧 EMAIL GÉNÉRÉ:")
        print(f"   Subject : {e.get('subject','')}")
        print(f"   Body    :")
        for line in e.get("body","").split("\n"):
            if line.strip():
                print(f"     {line}")

print("\n" + "="*65)
print("  RÉSUMÉ")
print("="*65)

hot  = sum(1 for l in leads if l["segment"] == "hot")
warm = sum(1 for l in leads if l["segment"] == "warm")
cold = sum(1 for l in leads if l["segment"] == "cold")
qualified = sum(1 for l in leads if l["status"] in ["qualified","email_ready"])

print(f"  Total leads     : {len(leads)}")
print(f"  HOT  (>70)      : {hot}")
print(f"  WARM (40-70)    : {warm}")
print(f"  COLD (<40)      : {cold}")
print(f"  Qualifiés       : {qualified}")
print(f"  Emails générés  : {len(emails_map)}")

# Leads avec email trouvé
with_email = sum(1 for l in leads if l["email"] and "@" in str(l["email"]))
print(f"  Avec email      : {with_email}")