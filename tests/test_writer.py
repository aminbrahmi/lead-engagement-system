"""
test_writer.py — test the email writer using real leads from DB or JSON.
"""

import json
import os
import sys
import sqlite3
from dotenv import load_dotenv
load_dotenv()

DB_PATH   = os.path.join("data", "leads.db")
JSON_PATH = os.path.join("data", "leads_raw.json")
ENRICHER_OUT = os.path.join("data", "enriched_leads.json")

DEFAULT_CAMPAIGN = "Reach out to CTOs of AI startups in Berlin that raised funding in the last 6 months"

# Import writer — tries writer_node first, falls back to email_generator_node
try:
    from agents.writer_node import run_email_generator
    print("[Test] Using agents/writer_node.py")
except ImportError:
    from agents.email_generator_node import run_email_generator
    print("[Test] Using agents/email_generator_node.py")


# ── Loaders ───────────────────────────────────────────────────────────────────

def load_from_db(include_cold: bool = False) -> list:
    if not os.path.exists(DB_PATH):
        print(f"[Test] ✗ DB not found at {DB_PATH}")
        return []
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    if include_cold:
        cursor.execute("SELECT * FROM leads ORDER BY score DESC")
    else:
        cursor.execute("""
            SELECT * FROM leads
            WHERE segment IN ('hot','warm')
            ORDER BY score DESC
        """)
    leads = [dict(row) for row in cursor.fetchall()]
    conn.close()
    for lead in leads:
        for field in ["insights", "draft_email"]:
            if isinstance(lead.get(field), str):
                try:
                    lead[field] = json.loads(lead[field])
                except Exception:
                    pass
    print(f"[Test] Loaded {len(leads)} leads from {DB_PATH}")
    return leads


def load_from_json_file(path: str, include_cold: bool = False) -> list:
    if not os.path.exists(path):
        print(f"[Test] ✗ File not found: {path}")
        return []
    with open(path, "r", encoding="utf-8") as f:
        leads = json.load(f)
    if not include_cold:
        leads = [l for l in leads if l.get("segment") in ("hot", "warm", None, "")]
    print(f"[Test] Loaded {len(leads)} leads from {path}")
    return leads


# ── Display ───────────────────────────────────────────────────────────────────

def print_lead_summary(leads: list):
    print(f"\n  {'Company':<20} {'Name':<25} {'Seg':<6} {'Score':<6} {'Email'}")
    print(f"  {'─'*80}")
    for l in leads:
        has_insights = "✓ insights" if l.get("insights") else "✗ no insights"
        print(f"  {l.get('company','?'):<20} "
              f"{(l.get('name') or 'unknown'):<25} "
              f"{l.get('segment','?'):<6} "
              f"{str(l.get('score','?')):<6} "
              f"{l.get('email') or '—'}  ({has_insights})")
    print()


def print_email(lead: dict):
    draft = lead.get("draft_email", {})
    seg   = (lead.get("segment") or "?").upper()
    print(f"\n{'='*60}")
    print(f"  [{seg}] {lead.get('company')} / {lead.get('name')}")
    print(f"  Score: {lead.get('score')} | Source: {lead.get('email_source','?')}")
    print(f"{'='*60}")
    if not draft:
        print("  (no email — cold / missing insights)")
        return
    print(f"  To:      {lead.get('email','—')}")
    print(f"  Subject: {draft.get('subject', '—')}")
    print(f"  {'─'*40}")
    for line in draft.get("body", "").split("\n"):
        print(f"  {line}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    use_json     = "--json"      in sys.argv
    use_file     = "--from-file" in sys.argv
    include_cold = "--all"       in sys.argv
    limit        = None
    campaign     = DEFAULT_CAMPAIGN

    if "--limit" in sys.argv:
        try:
            limit = int(sys.argv[sys.argv.index("--limit") + 1])
        except (IndexError, ValueError):
            print("[Test] --limit requires a number"); sys.exit(1)

    if "--campaign" in sys.argv:
        try:
            campaign = sys.argv[sys.argv.index("--campaign") + 1]
        except IndexError:
            print("[Test] --campaign requires a string"); sys.exit(1)

    # ── Load leads ────────────────────────────────────────────────────────────
    if use_file:
        leads = load_from_json_file(ENRICHER_OUT, include_cold)
    elif use_json:
        leads = load_from_json_file(JSON_PATH, include_cold)
    else:
        leads = load_from_db(include_cold)

    if not leads:
        print("[Test] No leads found. Run python main.py or test_enricher.py first.")
        sys.exit(1)

    # Filter unnamed
    leads = [l for l in leads if l.get("name") and l["name"].lower() != "unknown"]

    if limit:
        leads = leads[:limit]
        print(f"[Test] Limited to {limit} leads")

    print_lead_summary(leads)

    # ── Check insights ────────────────────────────────────────────────────────
    no_insights = [l for l in leads if not l.get("insights") and l.get("segment") in ("hot","warm")]
    if no_insights:
        print(f"[Test] ⚠  {len(no_insights)} lead(s) have no insights yet:")
        for l in no_insights:
            print(f"       • {l.get('company')} / {l.get('name')}")
        print("\n[Test] Running enricher first to generate insights...\n")
        from agents.enricher_node import run_enricher
        leads = run_enricher(leads)

    # ── Generate emails ───────────────────────────────────────────────────────
    print(f"\n[Test] Campaign: {campaign}")
    result = run_email_generator(leads, campaign)

    # Print emails
    for lead in result:
        print_email(lead)

    # Summary
    generated = [l for l in result if l.get("draft_email")]
    skipped   = [l for l in result if not l.get("draft_email")]

    print(f"\n{'='*60}")
    print(f"  SUMMARY  ({len(generated)} generated, {len(skipped)} skipped)")
    print(f"{'='*60}")
    for lead in generated:
        draft = lead.get("draft_email", {})
        seg   = (lead.get("segment") or "?").upper()
        print(f"  [{seg}] {lead.get('company','?'):<20} → {draft.get('subject','')}")

    # Save output to data/
    os.makedirs("data", exist_ok=True)
    out = os.path.join("data", "emails_draft.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"\n[Test] Output saved to {out}")

    print("\nUsage:")
    print("  python -m tests.test_writer                        # HOT+WARM from DB")
    print("  python -m tests.test_writer --json               # from leads_raw.json")
    print("  python -m tests.test_writer --from-file          # from data/enriched_leads.json")
    print("  python -m tests.test_writer --limit 2            # first 2 leads only")
    print('  python -m tests.test_writer --campaign "My brief" # custom campaign')


if __name__ == "__main__":
    main()