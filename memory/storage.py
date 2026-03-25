import sqlite3
import json
import os
import hashlib
from datetime import datetime

DATA_DIR  = os.path.join(os.path.dirname(__file__), "..", "data")
DB_PATH   = os.path.join(DATA_DIR, "leads.db")
JSON_PATH = os.path.join(DATA_DIR, "leads_raw.json")

def _ensure_dirs():
    os.makedirs(DATA_DIR, exist_ok=True)

def init_db():
    _ensure_dirs()
    conn   = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id           TEXT PRIMARY KEY,
            name         TEXT,
            company      TEXT,
            role         TEXT,
            location     TEXT,
            source_url   TEXT,
            notes        TEXT,
            email        TEXT,
            email_source TEXT,
            phone        TEXT,
            phone_source TEXT,
            campaign     TEXT,
            status       TEXT DEFAULT 'collected',
            score        INTEGER DEFAULT 0,
            segment      TEXT DEFAULT 'unknown',
            reason       TEXT,
            created_at   TEXT,
            updated_at   TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS campaigns (
            id          TEXT PRIMARY KEY,
            prompt      TEXT,
            leads_count INTEGER,
            created_at  TEXT
        )
    """)
    conn.commit()
    conn.close()

def _generate_id(name: str, company: str) -> str:
    """
    Stable ID keyed on company name only.

    ROOT CAUSE FIX for "Updated 0 leads":
    Agent 1 saves leads with name="unknown", company="Parloa" → id = md5("parloa").
    Agent 2 returns name="Maximilian Gross", company="Parloa".
    Old code: id = md5("maximilian gross_parloa") ≠ md5("unknown_parloa") → 0 matches.
    New code: id = md5("parloa") in both cases → always matches.
    """
    raw = company.lower().strip()
    return hashlib.md5(raw.encode()).hexdigest()[:12]

def _is_valid_lead(lead: dict) -> bool:
    url = lead.get("source_url", "")
    fake_domains = ["example.com", "placeholder", "fake", "test.com", "domain.com"]
    if any(d in url for d in fake_domains):
        return False
    if not url or url == "":
        return False
    return True

def save_leads(leads: list, campaign_prompt: str) -> dict:
    _ensure_dirs()
    init_db()

    campaign_id = hashlib.md5(
        f"{campaign_prompt}{datetime.now().isoformat()}".encode()
    ).hexdigest()[:8]

    now        = datetime.now().isoformat()
    added      = 0
    duplicates = 0

    # ── Filter invalid leads ──
    valid_leads   = [l for l in leads if _is_valid_lead(l)]
    invalid_count = len(leads) - len(valid_leads)
    if invalid_count > 0:
        print(f"[Storage] Rejected {invalid_count} leads with fake/missing URLs")

    leads = valid_leads
    print(f"[Storage] Processing {len(leads)} valid leads...")

    if not leads:
        print("[Storage] ⚠ No valid leads to save — check source_url values in agent output")
        return {"campaign_id": campaign_id, "added": 0, "duplicates": 0, "total": 0}

    # ── 1. SQLite ──
    try:
        conn   = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        for lead in leads:
            lead_id = _generate_id(
                lead.get("name", "unknown"),
                lead.get("company", "unknown")
            )
            cursor.execute("SELECT id FROM leads WHERE id = ?", (lead_id,))
            existing = cursor.fetchone()

            if existing:
                cursor.execute(
                    "UPDATE leads SET updated_at = ? WHERE id = ?",
                    (now, lead_id)
                )
                duplicates += 1
                print(f"[Storage] Duplicate skipped: {lead.get('company')}")
            else:
                cursor.execute("""
                    INSERT INTO leads
                    (id, name, company, role, location, source_url, notes,
                     campaign, status, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'collected', ?, ?)
                """, (
                    lead_id,
                    lead.get("name", "unknown"),
                    lead.get("company", "unknown"),
                    lead.get("role", ""),
                    lead.get("location", ""),
                    lead.get("source_url", ""),
                    lead.get("notes", ""),
                    campaign_id,
                    now, now
                ))
                added += 1
                print(f"[Storage] ✓ Inserted: {lead.get('company')} / {lead.get('name')}")

        cursor.execute("""
            INSERT OR IGNORE INTO campaigns (id, prompt, leads_count, created_at)
            VALUES (?, ?, ?, ?)
        """, (campaign_id, campaign_prompt, added, now))

        conn.commit()
        conn.close()
        print(f"[Storage] SQLite: {added} inserted, {duplicates} duplicates")

    except Exception as e:
        print(f"[Storage] ❌ SQLite error: {e}")
        import traceback; traceback.print_exc()

    # ── 2. JSON (with dedup) ──
    try:
        existing_json = []
        if os.path.exists(JSON_PATH):
            with open(JSON_PATH, "r", encoding="utf-8") as f:
                try:
                    existing_json = json.load(f)
                except Exception as e:
                    print(f"[Storage] JSON parse error (resetting file): {e}")
                    existing_json = []

        existing_ids = {
            _generate_id(l.get("name", ""), l.get("company", ""))
            for l in existing_json
        }

        new_in_json = 0
        for lead in leads:
            lead_id = _generate_id(
                lead.get("name", "unknown"),
                lead.get("company", "unknown")
            )
            if lead_id not in existing_ids:
                lead_copy = dict(lead)
                lead_copy["campaign_id"]  = campaign_id
                lead_copy["collected_at"] = now
                existing_json.append(lead_copy)
                existing_ids.add(lead_id)
                new_in_json += 1

        with open(JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(existing_json, f, indent=2, ensure_ascii=False)
        print(f"[Storage] JSON: {new_in_json} new entries → {JSON_PATH}")

    except Exception as e:
        print(f"[Storage] ❌ JSON error: {e}")
        import traceback; traceback.print_exc()

    # ── 3. ChromaDB ──
    try:
        import chromadb
        client     = chromadb.PersistentClient(path=os.path.join(DATA_DIR, "chroma"))
        collection = client.get_or_create_collection("leads")
        for lead in leads:
            lead_id = _generate_id(
                lead.get("name", "unknown"),
                lead.get("company", "unknown")
            )
            text = (f"{lead.get('name','')} {lead.get('company','')} "
                    f"{lead.get('role','')} {lead.get('location','')}")
            try:
                collection.add(
                    documents=[text],
                    ids=[lead_id],
                    metadatas=[{
                        "company": lead.get("company", ""),
                        "name":    lead.get("name", "")
                    }]
                )
            except Exception:
                pass  # duplicate in Chroma — expected, ignore silently
    except Exception as e:
        print(f"[Storage] ChromaDB warning: {e}")

    summary = {
        "campaign_id": campaign_id,
        "added":       added,
        "duplicates":  duplicates,
        "total":       added + duplicates
    }
    print(f"[Storage] Done: {added} new leads, {duplicates} duplicates skipped")
    return summary


def get_all_leads(status: str = None) -> list:
    init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    if status:
        cursor.execute("SELECT * FROM leads WHERE status = ?", (status,))
    else:
        cursor.execute("SELECT * FROM leads ORDER BY created_at DESC")
    leads = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return leads


def get_campaign_leads(campaign_id: str) -> list:
    init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM leads WHERE campaign = ?", (campaign_id,))
    leads = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return leads


def is_duplicate(name: str, company: str) -> bool:
    init_db()
    lead_id = _generate_id(name, company)
    conn    = sqlite3.connect(DB_PATH)
    cursor  = conn.cursor()
    cursor.execute("SELECT id FROM leads WHERE id = ?", (lead_id,))
    exists = cursor.fetchone() is not None
    conn.close()
    return exists


def update_lead_qualification(qualified_leads: list) -> int:
    """
    Update score, segment, email, phone for each qualified lead.
    Uses company-only ID — immune to name changes between Agent 1 and Agent 2.
    Also writes the resolved name back (was 'unknown' at collection time).
    """
    init_db()
    conn   = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now    = datetime.now().isoformat()

    updated = 0
    for lead in qualified_leads:
        lead_id = _generate_id(
            lead.get("name", "unknown"),
            lead.get("company", "unknown")
        )
        score   = lead.get("score", 0)
        segment = lead.get("segment", "cold")
        keep    = lead.get("keep", False)
        status  = "qualified" if keep else "rejected"

        cursor.execute("""
            UPDATE leads
            SET name         = ?,
                score        = ?,
                segment      = ?,
                status       = ?,
                email        = ?,
                email_source = ?,
                phone        = ?,
                phone_source = ?,
                reason       = ?,
                updated_at   = ?
            WHERE id = ?
        """, (
            lead.get("name"),
            score,
            segment,
            status,
            lead.get("email"),
            lead.get("email_source"),
            lead.get("phone"),
            lead.get("phone_source"),
            lead.get("reason"),
            now,
            lead_id
        ))

        if cursor.rowcount > 0:
            updated += 1
            print(f"[Storage] ✓ Qualified: {lead.get('company')} → {segment} (score={score})")
        else:
            print(f"[Storage] ⚠ No row found for: {lead.get('company')} (id={lead_id})")
            print(f"           Tip: does this company exist in leads.db from Agent 1?")

    conn.commit()
    conn.close()

    _sync_json_with_qualification(qualified_leads)
    print(f"[Storage] Qualification done: {updated}/{len(qualified_leads)} leads updated")
    return updated


def _sync_json_with_qualification(qualified_leads: list):
    if not os.path.exists(JSON_PATH):
        return
    try:
        with open(JSON_PATH, "r", encoding="utf-8") as f:
            existing = json.load(f)
    except Exception:
        return

    # Index by company-based ID — consistent with _generate_id
    qual_index = {
        _generate_id(l.get("name", "unknown"), l.get("company", "unknown")): l
        for l in qualified_leads
    }

    updated_count = 0
    for entry in existing:
        entry_id = _generate_id(
            entry.get("name", "unknown"),
            entry.get("company", "unknown")
        )
        if entry_id in qual_index:
            q = qual_index[entry_id]
            entry["name"]         = q.get("name", entry.get("name"))
            entry["score"]        = q.get("score", 0)
            entry["segment"]      = q.get("segment", "unknown")
            entry["status"]       = "qualified" if q.get("keep") else "rejected"
            entry["email"]        = q.get("email")
            entry["email_source"] = q.get("email_source")
            entry["phone"]        = q.get("phone")
            entry["phone_source"] = q.get("phone_source")
            entry["reason"]       = q.get("reason")
            entry["qualified_at"] = datetime.now().isoformat()
            updated_count += 1

    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2, ensure_ascii=False)
    print(f"[Storage] JSON synced: {updated_count} leads updated")


def update_email_in_db(name: str, company: str, email: str, source: str):
    init_db()
    conn    = sqlite3.connect(DB_PATH)
    now     = datetime.now().isoformat()
    lead_id = _generate_id(name, company)
    conn.execute("""
        UPDATE leads SET email = ?, email_source = ?, updated_at = ?
        WHERE id = ?
    """, (email, source, now, lead_id))
    conn.commit()
    conn.close()


def update_name_in_db(old_name: str, company: str, new_name: str):
    init_db()
    conn    = sqlite3.connect(DB_PATH)
    cursor  = conn.cursor()
    now     = datetime.now().isoformat()
    lead_id = _generate_id(old_name, company)
    print(f"[DB] Updating name for {company} → {new_name}")
    cursor.execute("""
        UPDATE leads SET name = ?, updated_at = ? WHERE id = ?
    """, (new_name, now, lead_id))
    if cursor.rowcount == 0:
        print(f"[DB] ⚠ No row updated for {company}")
    else:
        print(f"[DB] ✓ Name updated")
    conn.commit()
    conn.close()