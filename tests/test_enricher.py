"""
test_enricher.py — test enricher using real leads from data/leads.db or data/leads_raw.json
"""

import json
import os
import sys
import sqlite3
from dotenv import load_dotenv
load_dotenv()

DB_PATH   = os.path.join("data", "leads.db")
JSON_PATH = os.path.join("data", "leads_raw.json")


# ── Loaders ───────────────────────────────────────────────────────────────────

def load_from_db(include_cold: bool = False) -> list:
    if not os.path.exists(DB_PATH):
        print(f"[Test] ✗ DB not found at {DB_PATH}")
        return []

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    if include_cold:
        cursor.execute("SELECT * FROM leads ORDER BY score DESC, created_at DESC")
    else:
        cursor.execute("""
            SELECT * FROM leads
            WHERE segment IN ('hot', 'warm')
            ORDER BY score DESC, created_at DESC
        """)

    leads = [dict(row) for row in cursor.fetchall()]
    conn.close()

    # Parse JSON fields if already stored
    for lead in leads:
        for field in ["insights", "draft_email"]:
            if isinstance(lead.get(field), str):
                try:
                    lead[field] = json.loads(lead[field])
                except Exception:
                    pass

    print(f"[Test] Loaded {len(leads)} leads from {DB_PATH}")
    return leads


def load_from_json(include_cold: bool = False) -> list:
    if not os.path.exists(JSON_PATH):
        print(f"[Test] ✗ JSON not found at {JSON_PATH}")
        return []

    with open(JSON_PATH, "r", encoding="utf-8") as f:
        leads = json.load(f)

    if not include_cold:
        leads = [l for l in leads if l.get("segment") in ("hot", "warm", None, "")]

    print(f"[Test] Loaded {len(leads)} leads from {JSON_PATH}")
    return leads


# ── Display ───────────────────────────────────────────────────────────────────

def print_lead_summary(leads: list):
    print(f"\n{'─'*60}")
    print(f"  {'Company':<20} {'Name':<25} {'Seg':<6} {'Score'}")
    print(f"{'─'*60}")
    for l in leads:
        print(f"  {l.get('company','?'):<20} "
              f"{l.get('name','unknown'):<25} "
              f"{l.get('segment','?'):<6} "
              f"{l.get('score', '?')}")
    print(f"{'─'*60}\n")


def print_insights(lead: dict):
    insights = lead.get("insights", {})
    print(f"\n{'='*60}")
    print(f"  {lead.get('company')} / {lead.get('name')}  [{lead.get('segment','?').upper()}]")
    print(f"{'='*60}")
    if not insights:
        print("  (no insights — skipped)")
        return
    for key, val in insights.items():
        label = key.replace("_", " ").title()
        print(f"  {label}:")
        print(f"    {val}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    use_json     = "--json"  in sys.argv
    include_cold = "--all"   in sys.argv
    limit        = None
    if "--limit" in sys.argv:
        try:
            limit = int(sys.argv[sys.argv.index("--limit") + 1])
        except (IndexError, ValueError):
            print("[Test] --limit requires a number, e.g. --limit 3")
            sys.exit(1)

    # Load leads
    leads = load_from_json(include_cold) if use_json else load_from_db(include_cold)

    if not leads:
        print("[Test] No leads found. Run python main.py first to collect leads.")
        sys.exit(1)

    # Filter out leads with no name (nothing to enrich)
    leads = [l for l in leads if l.get("name") and l["name"].lower() != "unknown"]
    print(f"[Test] After filtering unknown names: {len(leads)} leads")

    if limit:
        leads = leads[:limit]
        print(f"[Test] Limited to {limit} leads")

    print_lead_summary(leads)

    # Check for already-enriched leads
    already = [l for l in leads if l.get("insights")]
    if already:
        print(f"[Test] ⚠  {len(already)} lead(s) already have insights in DB.")
        print("       They will be re-enriched and overwritten.\n")

    # Run enricher
    from agents.enricher_node import run_enricher
    enriched = run_enricher(leads)

    # Print results
    for lead in enriched:
        print_insights(lead)

    # Summary
    done    = sum(1 for l in enriched if l.get("insights"))
    skipped = sum(1 for l in enriched if not l.get("insights"))
    print(f"\n[Test] Done: {done} enriched, {skipped} skipped")

    # Save to data/
    os.makedirs("data", exist_ok=True)
    out = os.path.join("data", "enriched_leads.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(enriched, f, indent=2, ensure_ascii=False)
    print(f"[Test] Output saved to {out}")
    print("\nNext step: python -m tests.test_writer --from-file")


if __name__ == "__main__":
    main()