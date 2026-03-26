# tests/show_results.py
import sqlite3
import json
import os

DB_PATH    = "data/leads.db"
EMAIL_PATH = "data/emails_generated.json"

print("\n" + "="*65)
print("  LEADS — SCORES, CONTACTS & EMAILS")
print("="*65)

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
leads = conn.execute(
    "SELECT * FROM leads ORDER BY score DESC"
).fetchall()
conn.close()

# Load generated emails
emails_map = {}
if os.path.exists(EMAIL_PATH):
    with open(EMAIL_PATH, "r", encoding="utf-8") as f:
        emails = json.load(f)
    for e in emails:
        key = e.get("lead_name", "").lower()
        emails_map[key] = e

for i, lead in enumerate(leads, 1):
    score   = lead["score"]
    segment = lead["segment"] or "unknown"
    name    = lead["name"]
    company = lead["company"]
    email   = lead["email"] or "not found"
    phone   = lead["phone"] or "not found"
    seg_icon = {"hot": "🔥", "warm": "🟡", "cold": "🧊"}.get(segment, "⚪")

    print(f"\n{'─'*65}")
    print(f"{i}. {seg_icon} {name} @ {company}")
    print(f"   Score   : {score}/100 — {segment.upper()}")
    print(f"   Status  : {lead['status']}")
    print(f"   Role    : {lead['role']} | {lead['location']}")
    print(f"   Email   : {email} ({lead['email_source'] or 'N/A'})")
    print(f"   Phone   : {phone} ({lead['phone_source'] or 'N/A'})")
    if lead["reason"]:
        print(f"   Reason  : {lead['reason']}")

    # Show generated email if available
    email_data = emails_map.get(name.lower())
    if email_data:
        print(f"\n   📧 GENERATED EMAIL:")
        print(f"   To      : {email_data.get('lead_email') or email}")
        print(f"   Subject : {email_data.get('subject', '')}")
        print(f"   Hook    : {email_data.get('personalization_hook', '')}")
        print(f"   Language: {email_data.get('language', '')}")
        print(f"\n   Body:")
        body = email_data.get("body", "")
        for line in body.split("\n"):
            if line.strip():
                print(f"     {line}")

print(f"\n{'═'*65}")
print(f"  SUMMARY")
print(f"{'─'*65}")

hot        = sum(1 for l in leads if l["score"] >= 70)
warm       = sum(1 for l in leads if 40 <= l["score"] < 70)
cold       = sum(1 for l in leads if l["score"] < 40)
with_email = sum(1 for l in leads if l["email"] and "@" in str(l["email"]))
with_phone = sum(1 for l in leads if l["phone"])

print(f"  Total leads    : {len(leads)}")
print(f"  HOT  (>=70)    : {hot}")
print(f"  WARM (40-69)   : {warm}")
print(f"  COLD (<40)     : {cold}")
print(f"  With email     : {with_email}")
print(f"  With phone     : {with_phone}")
print(f"  Emails written : {len(emails_map)}")