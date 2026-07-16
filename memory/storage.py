# memory/storage.py — PostgreSQL version
import json
import os
import re
import hashlib
from datetime import datetime
from contextlib import contextmanager

import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor

from dotenv import load_dotenv
load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL is not set")

DATA_DIR  = os.path.join(os.path.dirname(__file__), "..", "data")
JSON_PATH = os.path.join(DATA_DIR, "leads_raw.json")

# ── Connection pool ───────────────────────────────────────────────────────────

_pool = None

def _get_pool():
    global _pool
    if _pool is None:
        _pool = pool.ThreadedConnectionPool(
            minconn=2,
            maxconn=10,
            dsn=DATABASE_URL,
        )
    return _pool


@contextmanager
def get_conn():
    """Get a connection from the pool, auto-commit on success, rollback on error."""
    p = _get_pool()
    conn = p.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        p.putconn(conn)


def _ensure_dirs():
    os.makedirs(DATA_DIR, exist_ok=True)


# ── Schema ────────────────────────────────────────────────────────────────────

def _safe_index(cursor, sql: str):
    """Create index using a savepoint so a privilege error doesn't abort the transaction."""
    try:
        cursor.execute("SAVEPOINT _idx")
        cursor.execute(sql)
        cursor.execute("RELEASE SAVEPOINT _idx")
    except Exception:
        cursor.execute("ROLLBACK TO SAVEPOINT _idx")


def init_db():
    _ensure_dirs()
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id            SERIAL PRIMARY KEY,
                email         TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                name          TEXT,
                created_at    TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS leads (
                id               VARCHAR(12) PRIMARY KEY,
                name             TEXT,
                company          TEXT,
                role             TEXT,
                location         TEXT,
                source_url       TEXT,
                notes            TEXT,
                email            TEXT,
                email_source     TEXT,
                email_verified   BOOLEAN DEFAULT FALSE,
                campaign         VARCHAR(12),
                status           VARCHAR(20) DEFAULT 'collected',
                score            INTEGER DEFAULT 0,
                segment          VARCHAR(10) DEFAULT 'unknown',
                reason           TEXT,
                insights         TEXT,
                draft_email      TEXT,
                draft_emails     TEXT,
                insights_quality VARCHAR(10),
                created_at       TIMESTAMPTZ,
                updated_at       TIMESTAMPTZ
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS campaigns (
                id          VARCHAR(12) PRIMARY KEY,
                prompt      TEXT,
                criteria    TEXT,
                status      VARCHAR(20) DEFAULT 'pending',
                leads_count INTEGER DEFAULT 0,
                created_at  TIMESTAMPTZ,
                updated_at  TIMESTAMPTZ
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS campaign_events (
                id          SERIAL PRIMARY KEY,
                campaign_id VARCHAR(12) REFERENCES campaigns(id),
                agent       VARCHAR(30),
                event_type  VARCHAR(30),
                message     TEXT,
                metadata    TEXT,
                created_at  TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS exclusion_list (
                id         SERIAL PRIMARY KEY,
                value      TEXT NOT NULL,
                type       VARCHAR(20) NOT NULL,
                reason     TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sender_config (
                id         SERIAL PRIMARY KEY,
                name       TEXT NOT NULL,
                email      TEXT NOT NULL,
                title      TEXT,
                company    TEXT,
                signature  TEXT,
                is_default BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS email_sequences (
                id            SERIAL PRIMARY KEY,
                lead_id       VARCHAR(12) REFERENCES leads(id),
                campaign_id   VARCHAR(12) REFERENCES campaigns(id),
                step          INTEGER NOT NULL,
                variant       VARCHAR(10),
                subject       TEXT NOT NULL,
                body          TEXT NOT NULL,
                cc            TEXT,
                status        VARCHAR(20) DEFAULT 'scheduled',
                scheduled_for TIMESTAMPTZ NOT NULL,
                sent_at       TIMESTAMPTZ,
                message_id    TEXT,
                error_message TEXT,
                created_at    TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                id          SERIAL PRIMARY KEY,
                campaign_id VARCHAR(12),
                lead_id     VARCHAR(12),
                type        VARCHAR(30) NOT NULL,
                message     TEXT,
                metadata    JSONB,
                read        BOOLEAN DEFAULT FALSE,
                created_at  TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS lead_notifications (
                id          SERIAL PRIMARY KEY,
                campaign_id VARCHAR(12),
                lead_id     VARCHAR(12),
                type        VARCHAR(30) NOT NULL,
                message     TEXT,
                metadata    TEXT,
                read        BOOLEAN DEFAULT FALSE,
                created_at  TIMESTAMPTZ DEFAULT NOW()
            )
        """)

        # Indexes
        _safe_index(cursor, "CREATE INDEX IF NOT EXISTS idx_leads_campaign ON leads(campaign)")
        _safe_index(cursor, "CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status)")
        _safe_index(cursor, "CREATE INDEX IF NOT EXISTS idx_leads_segment ON leads(segment)")
        _safe_index(cursor, "CREATE INDEX IF NOT EXISTS idx_events_campaign ON campaign_events(campaign_id)")
        _safe_index(cursor, "CREATE INDEX IF NOT EXISTS idx_exclusion_type ON exclusion_list(type)")
        _safe_index(cursor, "CREATE INDEX IF NOT EXISTS idx_sequences_lead ON email_sequences(lead_id)")
        _safe_index(cursor, "CREATE INDEX IF NOT EXISTS idx_sequences_status ON email_sequences(status)")
        _safe_index(cursor, "CREATE INDEX IF NOT EXISTS idx_sequences_scheduled ON email_sequences(scheduled_for)")
        _safe_index(cursor, "CREATE INDEX IF NOT EXISTS idx_notif_lead ON notifications(lead_id)")
        _safe_index(cursor, "CREATE INDEX IF NOT EXISTS idx_notif_read ON notifications(read)")

        # ── RGPD migration: cascade lead deletion to child rows (Art. 17) ─────
        # Without ON DELETE CASCADE, deleting a contacted lead fails on FK and
        # leaves personal data behind. Recreate the FKs with CASCADE.
        _safe_index(cursor, "ALTER TABLE email_sequences DROP CONSTRAINT IF EXISTS email_sequences_lead_id_fkey")
        _safe_index(cursor, "ALTER TABLE email_sequences ADD CONSTRAINT email_sequences_lead_id_fkey "
                            "FOREIGN KEY (lead_id) REFERENCES leads(id) ON DELETE CASCADE")
        _safe_index(cursor, "ALTER TABLE discussions DROP CONSTRAINT IF EXISTS discussions_lead_id_fkey")
        _safe_index(cursor, "ALTER TABLE discussions ADD CONSTRAINT discussions_lead_id_fkey "
                            "FOREIGN KEY (lead_id) REFERENCES leads(id) ON DELETE CASCADE")

        # ── Migrations: ajouter colonnes manquantes ──────────────────────────

        cursor.execute("ALTER TABLE leads ADD COLUMN IF NOT EXISTS last_sent_at TIMESTAMPTZ")
        cursor.execute("ALTER TABLE sender_config ADD COLUMN IF NOT EXISTS company_description TEXT")
        cursor.execute("ALTER TABLE sender_config ADD COLUMN IF NOT EXISTS company_location TEXT")
        cursor.execute("ALTER TABLE sender_config ADD COLUMN IF NOT EXISTS company_size TEXT")
        cursor.execute("ALTER TABLE sender_config ADD COLUMN IF NOT EXISTS company_url TEXT")
        cursor.execute("ALTER TABLE sender_config ADD COLUMN IF NOT EXISTS smtp_host TEXT")
        cursor.execute("ALTER TABLE sender_config ADD COLUMN IF NOT EXISTS smtp_port INTEGER")
        cursor.execute("ALTER TABLE sender_config ADD COLUMN IF NOT EXISTS smtp_user TEXT")
        cursor.execute("ALTER TABLE sender_config ADD COLUMN IF NOT EXISTS smtp_pass TEXT")
        cursor.execute("ALTER TABLE email_sequences ADD COLUMN IF NOT EXISTS campaign VARCHAR(255)")
        cursor.execute("ALTER TABLE email_sequences ADD COLUMN IF NOT EXISTS scheduled_at TIMESTAMPTZ")
        # User profile (feeds email generation) + email verification
        for col, typ in [
            ("role", "TEXT"), ("company", "TEXT"), ("company_description", "TEXT"),
            ("company_url", "TEXT"), ("company_location", "TEXT"), ("company_size", "TEXT"),
            ("signature", "TEXT"), ("photo_url", "TEXT"),
            ("email_verified", "BOOLEAN DEFAULT FALSE"), ("verification_token", "TEXT"),
        ]:
            cursor.execute(f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {col} {typ}")

        # Multi-tenant ownership
        cursor.execute("ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS user_id INTEGER")
        cursor.execute("ALTER TABLE leads ADD COLUMN IF NOT EXISTS user_id INTEGER")
        _safe_index(cursor, "CREATE INDEX IF NOT EXISTS idx_campaigns_user ON campaigns(user_id)")
        _safe_index(cursor, "CREATE INDEX IF NOT EXISTS idx_leads_user ON leads(user_id)")
        cursor.execute("ALTER TABLE email_sequences ADD COLUMN IF NOT EXISTS opened_at TIMESTAMPTZ")
        cursor.execute("ALTER TABLE email_sequences ADD COLUMN IF NOT EXISTS clicked_at TIMESTAMPTZ")
        cursor.execute("ALTER TABLE email_sequences ADD COLUMN IF NOT EXISTS recipient_email TEXT")
        # Engagement intensity: total open/click events (incremented on every hit)
        cursor.execute("ALTER TABLE email_sequences ADD COLUMN IF NOT EXISTS open_count INTEGER DEFAULT 0")
        cursor.execute("ALTER TABLE email_sequences ADD COLUMN IF NOT EXISTS click_count INTEGER DEFAULT 0")

        cursor.execute("""
            UPDATE email_sequences
            SET campaign = campaign_id
            WHERE campaign IS NULL AND campaign_id IS NOT NULL
        """)
        cursor.execute("""
            UPDATE email_sequences
            SET scheduled_at = scheduled_for
            WHERE scheduled_at IS NULL AND scheduled_for IS NOT NULL
        """)

        # ── discussions / messages tables ────────────────────────────────────
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS discussions (
                id              SERIAL PRIMARY KEY,
                lead_id         VARCHAR(12) REFERENCES leads(id),
                campaign_id     VARCHAR(12),
                subject         TEXT,
                status          VARCHAR(20) DEFAULT 'active',
                has_reply       BOOLEAN DEFAULT FALSE,
                last_message_at TIMESTAMPTZ DEFAULT NOW(),
                created_at      TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id            SERIAL PRIMARY KEY,
                discussion_id INTEGER REFERENCES discussions(id) ON DELETE CASCADE,
                lead_id       VARCHAR(12),
                direction     VARCHAR(10) NOT NULL,
                subject       TEXT,
                body          TEXT,
                from_email    TEXT,
                sequence_id   INTEGER,
                message_id    TEXT,
                in_reply_to   TEXT,
                sentiment     VARCHAR(30),
                created_at    TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        _safe_index(cursor, "CREATE INDEX IF NOT EXISTS idx_disc_lead ON discussions(lead_id)")
        _safe_index(cursor, "CREATE INDEX IF NOT EXISTS idx_msg_disc ON messages(discussion_id)")

# ── Helpers ───────────────────────────────────────────────────────────────────

_COMPANY_STOPWORDS = {
    "the", "group", "holding", "holdings", "inc", "llc", "ltd", "limited",
    "sa", "spa", "srl", "gmbh", "co", "corp", "corporation", "company",
    "net", "porter", "a", "and", "&",
}


def _company_key(company: str) -> str:
    """Normalize a company name to a stable key so name variants collapse:
    'Yoox', 'Yoox Net-a-Porter Group' → 'yoox'. Uses the first significant token."""
    c = re.sub(r"[^a-z0-9 ]", " ", (company or "unknown").lower())
    tokens = [t for t in c.split() if t and t not in _COMPANY_STOPWORDS]
    return tokens[0] if tokens else (c.replace(" ", "") or "unknown")


def _generate_id(name: str, company: str, user_id=None) -> str:
    # user_id scopes the id per user → two users collecting the same company
    # get different lead ids (no cross-user collision).
    raw = _company_key(company)
    if user_id is not None:
        raw = f"u{user_id}:{raw}"
    return hashlib.md5(raw.encode()).hexdigest()[:12]


# ── Users (authentication) ────────────────────────────────────────────────────

_USER_PROFILE_FIELDS = (
    "name", "role", "company", "company_description", "company_url",
    "company_location", "company_size", "signature", "photo_url",
)


def create_user(email: str, password_hash: str, profile: dict = None,
                verification_token: str = None) -> dict | None:
    init_db()
    profile = profile or {}
    with get_conn() as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        try:
            cursor.execute("""
                INSERT INTO users (email, password_hash, name, role, company,
                    company_description, company_url, company_location, company_size,
                    signature, photo_url, verification_token)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, email, name
            """, (
                email.lower().strip(), password_hash,
                profile.get("name"), profile.get("role"), profile.get("company"),
                profile.get("company_description"), profile.get("company_url"),
                profile.get("company_location"), profile.get("company_size"),
                profile.get("signature"), profile.get("photo_url"), verification_token,
            ))
            return dict(cursor.fetchone())
        except Exception as e:
            print(f"[Storage] create_user error: {e}")
            return None   # duplicate email (UNIQUE) or other error


def _public_user(row: dict) -> dict:
    """User dict without sensitive fields (password_hash, token)."""
    if not row:
        return None
    d = dict(row)
    d.pop("password_hash", None)
    d.pop("verification_token", None)
    if d.get("created_at") and hasattr(d["created_at"], "isoformat"):
        d["created_at"] = d["created_at"].isoformat()
    return d


def get_user_by_email(email: str) -> dict | None:
    with get_conn() as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT * FROM users WHERE email = %s", (email.lower().strip(),))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_user_by_id(user_id: int, public: bool = True) -> dict | None:
    with get_conn() as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return _public_user(row) if public else dict(row)


def update_user(user_id: int, fields: dict) -> dict | None:
    """Update editable profile fields."""
    allowed = {k: v for k, v in (fields or {}).items() if k in _USER_PROFILE_FIELDS}
    if not allowed:
        return get_user_by_id(user_id)
    sets = ", ".join(f"{k} = %s" for k in allowed)
    vals = list(allowed.values()) + [user_id]
    with get_conn() as conn:
        conn.cursor().execute(f"UPDATE users SET {sets} WHERE id = %s", vals)
    return get_user_by_id(user_id)


def verify_user_token(token: str) -> bool:
    """Mark a user's email verified from their verification token."""
    if not token:
        return False
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET email_verified = TRUE, verification_token = NULL "
            "WHERE verification_token = %s RETURNING id",
            (token,),
        )
        return cursor.fetchone() is not None


def set_verification_token(user_id: int, token: str):
    with get_conn() as conn:
        conn.cursor().execute(
            "UPDATE users SET verification_token = %s WHERE id = %s", (token, user_id))


def _generate_campaign_id(prompt: str, user_id=None) -> str:
    """Same prompt (per user) always produces the same campaign ID."""
    normalized = prompt.strip().lower()
    if user_id is not None:
        normalized = f"u{user_id}:{normalized}"
    return hashlib.md5(normalized.encode()).hexdigest()[:12]


def _is_valid_lead(lead: dict) -> bool:
    url = lead.get("source_url", "")
    fake_domains = ["example.com", "placeholder", "fake", "test.com", "domain.com"]
    if any(d in url for d in fake_domains):
        return False
    if not url or url == "":
        return False
    return True


# ── Campaign queries ──────────────────────────────────────────────────────────

def get_campaign_by_prompt(prompt: str, user_id=None) -> dict | None:
    """Check if a campaign with this prompt already exists (for this user)."""
    campaign_id = _generate_campaign_id(prompt, user_id)
    with get_conn() as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT * FROM campaigns WHERE id = %s", (campaign_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_all_campaigns(user_id=None) -> list:
    """Return all campaigns with lead count breakdown (scoped to user_id if given)."""
    init_db()
    with get_conn() as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        where = "WHERE c.user_id = %s" if user_id is not None else ""
        params = (user_id,) if user_id is not None else ()
        cursor.execute(f"""
            SELECT
                c.id,
                c.prompt,
                c.created_at,
                c.updated_at,
                COUNT(l.id) AS leads_count,
                COUNT(CASE WHEN l.segment = 'hot' THEN 1 END)  AS hot_count,
                COUNT(CASE WHEN l.segment = 'warm' THEN 1 END) AS warm_count,
                COUNT(CASE WHEN l.segment = 'cold' THEN 1 END) AS cold_count,
                COUNT(CASE WHEN l.draft_email IS NOT NULL THEN 1 END) AS emails_count
            FROM campaigns c
            LEFT JOIN leads l ON l.campaign = c.id
            {where}
            GROUP BY c.id
            ORDER BY COALESCE(c.updated_at, c.created_at) DESC
        """, params)
        return [dict(row) for row in cursor.fetchall()]


# ── Save leads (Agent 1 output) ──────────────────────────────────────────────

def save_leads(leads: list, campaign_prompt: str, user_id=None) -> dict:
    _ensure_dirs()
    init_db()

    campaign_id = _generate_campaign_id(campaign_prompt, user_id)
    now         = datetime.now().isoformat()
    added       = 0
    duplicates  = 0

    valid_leads   = [l for l in leads if _is_valid_lead(l)]
    invalid_count = len(leads) - len(valid_leads)
    if invalid_count > 0:
        print(f"[Storage] Rejected {invalid_count} leads with fake/missing URLs")

    leads = valid_leads
    print(f"[Storage] Processing {len(leads)} valid leads...")

    if not leads:
        print("[Storage] ⚠ No valid leads to save — check source_url values in agent output")
        return {"campaign_id": campaign_id, "added": 0, "duplicates": 0, "total": 0}

    # ── 1. PostgreSQL ──
    try:
        with get_conn() as conn:
            cursor = conn.cursor()

            for lead in leads:
                lead_id = _generate_id(
                    lead.get("name", "unknown"),
                    lead.get("company", "unknown"),
                    user_id,
                )
                cursor.execute("SELECT id FROM leads WHERE id = %s", (lead_id,))
                existing = cursor.fetchone()

                if existing:
                    cursor.execute(
                        "UPDATE leads SET updated_at = %s, campaign = %s, user_id = %s WHERE id = %s",
                        (now, campaign_id, user_id, lead_id)
                    )
                    duplicates += 1
                    print(f"[Storage] Duplicate updated: {lead.get('company')}")
                else:
                    cursor.execute("""
                        INSERT INTO leads
                        (id, name, company, role, location, source_url, notes,
                         campaign, user_id, status, created_at, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'collected', %s, %s)
                    """, (
                        lead_id,
                        lead.get("name", "unknown"),
                        lead.get("company", "unknown"),
                        lead.get("role", ""),
                        lead.get("location", ""),
                        lead.get("source_url", ""),
                        lead.get("notes", ""),
                        campaign_id,
                        user_id,
                        now, now
                    ))
                    added += 1
                    print(f"[Storage] ✓ Inserted: {lead.get('company')} / {lead.get('name')}")

            # Upsert campaign — create if new, update if exists
            cursor.execute("""
                INSERT INTO campaigns (id, prompt, user_id, leads_count, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    leads_count = (
                        SELECT COUNT(*) FROM leads WHERE campaign = %s
                    ),
                    updated_at = %s
            """, (campaign_id, campaign_prompt, user_id, added, now, now, campaign_id, now))

            print(f"[Storage] PostgreSQL: {added} inserted, {duplicates} duplicates")

    except Exception as e:
        print(f"[Storage] ❌ PostgreSQL error: {e}")
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
                pass
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


# ── Read queries ──────────────────────────────────────────────────────────────

def get_all_leads(status: str = None, user_id=None) -> list:
    init_db()
    clauses, params = [], []
    if status:
        clauses.append("status = %s"); params.append(status)
    if user_id is not None:
        clauses.append("user_id = %s"); params.append(user_id)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    with get_conn() as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute(f"SELECT * FROM leads {where} ORDER BY created_at DESC", tuple(params))
        return [dict(row) for row in cursor.fetchall()]


def get_campaign_leads(campaign_id: str, user_id=None) -> list:
    init_db()
    with get_conn() as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        if user_id is not None:
            cursor.execute("SELECT * FROM leads WHERE campaign = %s AND user_id = %s ORDER BY score DESC",
                           (campaign_id, user_id))
        else:
            cursor.execute("SELECT * FROM leads WHERE campaign = %s ORDER BY score DESC", (campaign_id,))
        return [dict(row) for row in cursor.fetchall()]


def is_duplicate(name: str, company: str) -> bool:
    init_db()
    lead_id = _generate_id(name, company)
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM leads WHERE id = %s", (lead_id,))
        return cursor.fetchone() is not None


# ── Update qualification (Agent 2 output) ─────────────────────────────────────

def update_lead_qualification(qualified_leads: list, user_id=None) -> int:
    init_db()
    now = datetime.now().isoformat()
    updated = 0

    with get_conn() as conn:
        cursor = conn.cursor()

        for lead in qualified_leads:
            lead_id = _generate_id(
                lead.get("name", "unknown"),
                lead.get("company", "unknown"),
                user_id,
            )
            lead["id"] = lead_id   # ensure frontend can reference the DB id
            score   = lead.get("score", 0)
            segment = lead.get("segment", "cold")
            keep    = lead.get("keep", False)
            status  = "qualified" if keep else "rejected"

            cursor.execute("""
                UPDATE leads
                SET name         = %s,
                    score        = %s,
                    segment      = %s,
                    status       = %s,
                    email        = %s,
                    email_source = %s,
                    reason       = %s,
                    updated_at   = %s
                WHERE id = %s
            """, (
                lead.get("name"),
                score,
                segment,
                status,
                lead.get("email"),
                lead.get("email_source"),
                lead.get("reason"),
                now,
                lead_id
            ))

            if cursor.rowcount > 0:
                updated += 1
                print(f"[Storage] ✓ Qualified: {lead.get('company')} → {segment} (score={score})")
            else:
                print(f"[Storage] ⚠ No row found for: {lead.get('company')} (id={lead_id})")

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
            entry["reason"]       = q.get("reason")
            entry["qualified_at"] = datetime.now().isoformat()
            updated_count += 1

    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2, ensure_ascii=False)
    print(f"[Storage] JSON synced: {updated_count} leads updated")


# ── Save enrichment results (Agent 3 + 4 output) ─────────────────────────────

def save_enrichment_results(enriched_leads: list, user_id=None) -> int:
    """Persist insights and draft_email for each lead to PostgreSQL and JSON."""
    init_db()
    now = datetime.now().isoformat()
    updated = 0

    with get_conn() as conn:
        cursor = conn.cursor()

        for lead in enriched_leads:
            # Prefer the lead's existing id — recomputing from name+company breaks
            # when the company was enriched/changed (the row id stays the original).
            lead_id = lead.get("id") or _generate_id(
                lead.get("name", "unknown"),
                lead.get("company", "unknown"),
                user_id,
            )
            lead["id"] = lead_id   # ensure frontend can reference the DB id

            insights_json    = json.dumps(lead.get("insights", {}), ensure_ascii=False) \
                               if lead.get("insights") else None
            draft_email_json = json.dumps(lead.get("draft_email", {}), ensure_ascii=False) \
                               if lead.get("draft_email") else None
            draft_emails_json = json.dumps(lead.get("draft_emails", {}), ensure_ascii=False) \
                                if lead.get("draft_emails") else None
            insights_quality = lead.get("insights_quality")
            email_verified   = lead.get("email_verified", False)

            cursor.execute("""
                UPDATE leads
                SET insights         = %s,
                    draft_email      = %s,
                    draft_emails     = %s,
                    insights_quality = %s,
                    email_verified   = %s,
                    status           = %s,
                    updated_at       = %s
                WHERE id = %s
            """, (
                insights_json,
                draft_email_json,
                draft_emails_json,
                insights_quality,
                email_verified,
                "enriched" if draft_email_json else "qualified",
                now,
                lead_id,
            ))

            if cursor.rowcount > 0:
                updated += 1
                has_email = "✉" if draft_email_json else "—"
                has_ins   = "✓" if insights_json else "—"
                print(f"[Storage] ✓ Enrichment saved: {lead.get('company')} "
                      f"[insights={has_ins} email={has_email}]")
            else:
                print(f"[Storage] ⚠ No row found for enrichment: {lead.get('company')} (id={lead_id})")

    _sync_json_with_enrichment(enriched_leads)
    print(f"[Storage] Enrichment persistence done: {updated}/{len(enriched_leads)} leads updated")
    return updated


def _sync_json_with_enrichment(enriched_leads: list):
    """Merge insights + draft_email into leads_raw.json."""
    if not os.path.exists(JSON_PATH):
        return
    try:
        with open(JSON_PATH, "r", encoding="utf-8") as f:
            existing = json.load(f)
    except Exception:
        return

    enrich_index = {
        _generate_id(l.get("name", "unknown"), l.get("company", "unknown")): l
        for l in enriched_leads
    }

    updated_count = 0
    for entry in existing:
        entry_id = _generate_id(
            entry.get("name", "unknown"),
            entry.get("company", "unknown")
        )
        if entry_id in enrich_index:
            src = enrich_index[entry_id]
            if src.get("insights"):
                entry["insights"] = src["insights"]
                entry["insights_quality"] = src.get("insights_quality")
            if src.get("draft_email"):
                entry["draft_email"] = src["draft_email"]
                entry["status"]      = "enriched"
            entry["enriched_at"] = datetime.now().isoformat()
            updated_count += 1

    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2, ensure_ascii=False)
    print(f"[Storage] JSON enrichment synced: {updated_count} leads updated")


# ── Helpers ───────────────────────────────────────────────────────────────────

def update_email_in_db(name: str, company: str, email: str, source: str):
    init_db()
    now     = datetime.now().isoformat()
    lead_id = _generate_id(name, company)
    with get_conn() as conn:
        conn.cursor().execute("""
            UPDATE leads SET email = %s, email_source = %s, updated_at = %s
            WHERE id = %s
        """, (email, source, now, lead_id))


def update_name_in_db(old_name: str, company: str, new_name: str):
    init_db()
    now     = datetime.now().isoformat()
    lead_id = _generate_id(old_name, company)
    print(f"[DB] Updating name for {company} → {new_name}")
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE leads SET name = %s, updated_at = %s WHERE id = %s
        """, (new_name, now, lead_id))
        if cursor.rowcount == 0:
            print(f"[DB] ⚠ No row updated for {company}")
        else:
            print(f"[DB] ✓ Name updated")


# ── Campaign events ──────────────────────────────────────────────────────────

def log_campaign_event(campaign_id: str, agent: str, event_type: str,
                       message: str, metadata: dict = None):
    """Log a pipeline event for the campaign timeline."""
    try:
        with get_conn() as conn:
            conn.cursor().execute("""
                INSERT INTO campaign_events (campaign_id, agent, event_type, message, metadata)
                VALUES (%s, %s, %s, %s, %s)
            """, (
                campaign_id, agent, event_type, message,
                json.dumps(metadata) if metadata else None,
            ))
    except Exception as e:
        print(f"[Storage] Event log error: {e}")


def get_campaign_events(campaign_id: str) -> list:
    """Get all events for a campaign, ordered chronologically."""
    with get_conn() as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("""
            SELECT * FROM campaign_events
            WHERE campaign_id = %s
            ORDER BY created_at ASC
        """, (campaign_id,))
        rows = cursor.fetchall()
        for r in rows:
            if r.get("created_at") and hasattr(r["created_at"], "isoformat"):
                r["created_at"] = r["created_at"].isoformat()
            if r.get("metadata") and isinstance(r["metadata"], str):
                try:
                    r["metadata"] = json.loads(r["metadata"])
                except Exception:
                    pass
        return [dict(r) for r in rows]


# ── Campaign status ──────────────────────────────────────────────────────────

def update_campaign_status(campaign_id: str, status: str):
    """Update campaign status: pending → collecting → qualifying → enriching → drafts_ready → sending → completed."""
    with get_conn() as conn:
        conn.cursor().execute("""
            UPDATE campaigns SET status = %s, updated_at = %s WHERE id = %s
        """, (status, datetime.now().isoformat(), campaign_id))


def save_campaign_criteria(campaign_id: str, criteria: dict):
    """Save parsed criteria on the campaign for similarity matching."""
    with get_conn() as conn:
        conn.cursor().execute("""
            UPDATE campaigns SET criteria = %s WHERE id = %s
        """, (json.dumps(criteria, ensure_ascii=False), campaign_id))


# ── Similar campaign detection ───────────────────────────────────────────────

def find_similar_campaign(criteria: dict) -> dict | None:
    """Find an existing campaign with matching job_titles + location (Level 3 similarity)."""
    target_roles    = set(r.lower() for r in criteria.get("job_titles", []))
    target_location = (criteria.get("location") or "").lower().strip()

    if not target_roles or not target_location:
        return None

    with get_conn() as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT * FROM campaigns WHERE criteria IS NOT NULL ORDER BY created_at DESC")
        for row in cursor.fetchall():
            try:
                old = json.loads(row["criteria"])
                old_roles    = set(r.lower() for r in old.get("job_titles", []))
                old_location = (old.get("location") or "").lower().strip()

                if old_roles == target_roles and old_location == target_location:
                    return dict(row)
            except Exception:
                continue
    return None


# ── Exclusion list ───────────────────────────────────────────────────────────

def add_exclusion(value: str, exc_type: str, reason: str = None):
    """Add a company or domain to the exclusion list (idempotent).
    exc_type: 'company' | 'domain' | 'email'
    """
    val = value.lower().strip()
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id FROM exclusion_list WHERE type = %s AND value = %s",
            (exc_type, val)
        )
        if cursor.fetchone():
            return  # already excluded — don't duplicate
        cursor.execute("""
            INSERT INTO exclusion_list (value, type, reason)
            VALUES (%s, %s, %s)
        """, (val, exc_type, reason))


def remove_exclusion_by_value(value: str, exc_type: str = None) -> int:
    """Remove all exclusion rows matching a value (optionally typed).
    Returns number of rows deleted."""
    val = value.lower().strip()
    with get_conn() as conn:
        cursor = conn.cursor()
        if exc_type:
            cursor.execute(
                "DELETE FROM exclusion_list WHERE value = %s AND type = %s",
                (val, exc_type)
            )
        else:
            cursor.execute("DELETE FROM exclusion_list WHERE value = %s", (val,))
        return cursor.rowcount


def get_exclusion_list() -> list:
    with get_conn() as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT * FROM exclusion_list ORDER BY created_at DESC")
        rows = cursor.fetchall()
        for r in rows:
            if r.get("created_at") and hasattr(r["created_at"], "isoformat"):
                r["created_at"] = r["created_at"].isoformat()
        return [dict(r) for r in rows]


def remove_exclusion(exclusion_id: int):
    with get_conn() as conn:
        conn.cursor().execute("DELETE FROM exclusion_list WHERE id = %s", (exclusion_id,))


def is_excluded(company: str = None, domain: str = None, email: str = None) -> bool:
    """Check if a company, domain, or email is in the exclusion list."""
    with get_conn() as conn:
        cursor = conn.cursor()
        checks = []
        if company:
            checks.append(("company", company.lower().strip()))
        if domain:
            checks.append(("domain", domain.lower().strip()))
        if email:
            checks.append(("email", email.lower().strip()))

        for exc_type, val in checks:
            cursor.execute(
                "SELECT id FROM exclusion_list WHERE type = %s AND value = %s",
                (exc_type, val)
            )
            if cursor.fetchone():
                return True
    return False


# ── RGPD: complete erasure (Art. 17 — right to be forgotten) ─────────────────

def delete_lead_completely(lead_id: str) -> dict:
    """Erase every trace of a lead's personal data across all stores:
    PostgreSQL (lead + sequences + discussions + messages + notifications),
    the JSON snapshot, and the ChromaDB vector store.

    Returns a summary of what was removed.
    """
    result = {"db": 0, "json": 0, "chroma": False, "name": None, "company": None}

    # ── 1. PostgreSQL — delete child rows first, then the lead ──
    try:
        with get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name, company FROM leads WHERE id = %s", (lead_id,))
            row = cursor.fetchone()
            if row:
                result["name"], result["company"] = row[0], row[1]

            # Child tables with a plain lead_id column (no/partial FK cascade)
            for tbl in ("messages", "email_sequences", "lead_notifications", "notifications"):
                try:
                    cursor.execute(f"DELETE FROM {tbl} WHERE lead_id = %s", (lead_id,))
                except Exception as e:
                    print(f"[Erase] {tbl} cleanup skipped: {e}")
            cursor.execute("DELETE FROM discussions WHERE lead_id = %s", (lead_id,))
            cursor.execute("DELETE FROM leads WHERE id = %s", (lead_id,))
            result["db"] = cursor.rowcount
    except Exception as e:
        print(f"[Erase] PostgreSQL error: {e}")

    # ── 2. JSON snapshot ──
    try:
        if os.path.exists(JSON_PATH):
            with open(JSON_PATH, "r", encoding="utf-8") as f:
                entries = json.load(f)
            kept = [
                e for e in entries
                if _generate_id(e.get("name", "unknown"), e.get("company", "unknown")) != lead_id
            ]
            result["json"] = len(entries) - len(kept)
            with open(JSON_PATH, "w", encoding="utf-8") as f:
                json.dump(kept, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[Erase] JSON error: {e}")

    # ── 3. ChromaDB ──
    try:
        import chromadb
        client = chromadb.PersistentClient(path=os.path.join(DATA_DIR, "chroma"))
        collection = client.get_or_create_collection("leads")
        collection.delete(ids=[lead_id])
        result["chroma"] = True
    except Exception as e:
        print(f"[Erase] ChromaDB error: {e}")

    print(f"[Erase] Lead {lead_id} erased — db={result['db']} json={result['json']} chroma={result['chroma']}")
    return result


# ── Sender config ────────────────────────────────────────────────────────────

def save_sender_config(name, email, title="", company="", signature="",
                       is_default=False, company_description="",
                       company_location="", company_size="", company_url=""):
    with get_conn() as conn:
        cursor = conn.cursor()
        if is_default:
            # Check if a default already exists — update it rather than insert a new row
            cursor.execute("SELECT id FROM sender_config WHERE is_default = TRUE LIMIT 1")
            existing = cursor.fetchone()
            if existing:
                cursor.execute("""
                    UPDATE sender_config
                    SET name=%s, email=%s, title=%s, company=%s, signature=%s,
                        company_description=%s, company_location=%s,
                        company_size=%s, company_url=%s
                    WHERE id=%s
                """, (name, email, title, company, signature,
                      company_description, company_location, company_size,
                      company_url, existing[0]))
                return
            # No default exists yet — clear any non-default and insert
            cursor.execute("UPDATE sender_config SET is_default = FALSE")
        cursor.execute("""
            INSERT INTO sender_config
            (name, email, title, company, signature, is_default,
             company_description, company_location, company_size, company_url)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (name, email, title, company, signature, is_default,
              company_description, company_location, company_size, company_url))


def _sender_from_env() -> dict | None:
    """Build a sender config dict from environment variables."""
    name  = os.getenv("SENDER_NAME", "")
    email = os.getenv("SMTP_USER", "") or os.getenv("SENDER_EMAIL", "")
    if not name and not email:
        return None
    return {
        "name":                name,
        "email":               email,
        "title":               os.getenv("SENDER_TITLE", ""),
        "company":             os.getenv("SENDER_COMPANY", ""),
        "company_description": os.getenv("SENDER_COMPANY_DESC", ""),
        "company_location":    os.getenv("SENDER_COMPANY_LOCATION", ""),
        "company_size":        os.getenv("SENDER_COMPANY_SIZE", ""),
        "company_url":         os.getenv("SENDER_COMPANY_URL", ""),
        "signature":           os.getenv("SENDER_SIGNATURE", ""),
        "smtp_host":           os.getenv("SMTP_HOST", "smtp.gmail.com"),
        "smtp_port":           int(os.getenv("SMTP_PORT", "587")),
        "smtp_user":           os.getenv("SMTP_USER", ""),
        "smtp_pass":           os.getenv("SMTP_PASS", ""),
        "is_default":          True,
    }


def get_sender_config(default_only: bool = True) -> dict | None:
    with get_conn() as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        if default_only:
            cursor.execute("SELECT * FROM sender_config WHERE is_default = TRUE LIMIT 1")
        else:
            cursor.execute("SELECT * FROM sender_config ORDER BY is_default DESC, created_at DESC")
            rows = [dict(r) for r in cursor.fetchall()]
            return rows if rows else ([_sender_from_env()] if _sender_from_env() else [])
        row = cursor.fetchone()
        if row:
            return dict(row)
    # Fallback to environment variables when DB table is empty
    return _sender_from_env()


def update_sender_config(sender_id: int, **fields):
    allowed = {"name", "email", "title", "company", "signature", "is_default"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    with get_conn() as conn:
        cursor = conn.cursor()
        if updates.get("is_default"):
            cursor.execute("UPDATE sender_config SET is_default = FALSE")
        sets   = ", ".join(f"{k} = %s" for k in updates)
        values = list(updates.values()) + [sender_id]
        cursor.execute(f"UPDATE sender_config SET {sets} WHERE id = %s", values)


# ── SMTP verification status ─────────────────────────────────────────────────

def update_email_verification(lead_id: str, verified: bool):
    with get_conn() as conn:
        conn.cursor().execute("""
            UPDATE leads SET email_verified = %s, updated_at = %s WHERE id = %s
        """, (verified, datetime.now().isoformat(), lead_id))


# ── Email Sequence Management ────────────────────────────────────────────────

def create_full_sequence(lead_id: str, campaign_id: str, variant: str,
                        initial_subject: str, initial_body: str,
                        followup_emails: list, cc: str = None) -> list:
    """Create a full 4-step email sequence (initial + 3 follow-ups)."""
    from datetime import timedelta
    
    now = datetime.now()
    sequence_steps = [
        {"step": 0, "delay_days": 0, "subject": initial_subject, "body": initial_body},
        {"step": 1, "delay_days": 3, "subject": followup_emails[0]['subject'], "body": followup_emails[0]['body']},
        {"step": 2, "delay_days": 7, "subject": followup_emails[1]['subject'], "body": followup_emails[1]['body']},
        {"step": 3, "delay_days": 14, "subject": followup_emails[2]['subject'], "body": followup_emails[2]['body']},
    ]
    
    sequence_ids = []
    with get_conn() as conn:
        cursor = conn.cursor()
        for seq in sequence_steps:
            scheduled_for = now + timedelta(days=seq['delay_days'])
            cursor.execute("""
                INSERT INTO email_sequences
                    (lead_id, campaign_id, step, variant, subject, body, cc, status, scheduled_for)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'scheduled', %s)
                RETURNING id
            """, (lead_id, campaign_id, seq['step'], variant, seq['subject'], seq['body'], cc, scheduled_for))
            sequence_ids.append(cursor.fetchone()[0])
    return sequence_ids


def get_due_sequences() -> list:
    """Get email sequences due to be sent."""
    now = datetime.now()
    
    with get_conn() as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("""
            SELECT es.*, l.name, l.company, l.email
            FROM email_sequences es
            JOIN leads l ON es.lead_id = l.id
            WHERE es.status = 'scheduled' AND es.scheduled_for <= %s
            ORDER BY es.scheduled_for
        """, (now,))
        return [dict(row) for row in cursor.fetchall()]


def update_sequence_status(sequence_id: int, status: str,
                          message_id: str = None, error_message: str = None,
                          recipient_email: str = None):
    """Update sequence step status."""
    now = datetime.now()

    with get_conn() as conn:
        cursor = conn.cursor()
        # Preserve sent_at / message_id / recipient_email on status transitions
        # (e.g. 'sent' → 'replied') so we never lose the "was sent" evidence.
        cursor.execute("""
            UPDATE email_sequences
            SET status          = %s,
                sent_at         = CASE WHEN %s = 'sent' THEN %s ELSE sent_at END,
                message_id      = COALESCE(%s, message_id),
                error_message   = %s,
                recipient_email = COALESCE(%s, recipient_email)
            WHERE id = %s
        """, (status, status, now, message_id, error_message,
              recipient_email, sequence_id))


def cancel_remaining_sequence(lead_id: str, reason: str = "Lead replied"):
    """Cancel remaining scheduled emails for a lead."""
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE email_sequences
            SET status = 'cancelled', error_message = %s
            WHERE lead_id = %s AND status = 'scheduled'
        """, (reason, lead_id))


def get_lead_sequence(lead_id: str) -> list:
    """Get full email sequence for a lead."""
    with get_conn() as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("""
            SELECT * FROM email_sequences
            WHERE lead_id = %s
            ORDER BY step
        """, (lead_id,))
        return [dict(row) for row in cursor.fetchall()]


# ── Discussions & Messages ────────────────────────────────────────────────────

def get_or_create_discussion(lead_id: str, campaign_id: str, subject: str) -> int:
    """Return existing discussion_id for a lead+campaign, or create a new one.

    Priority:
      1. Same lead + same campaign  → correct thread
      2. Same lead (any campaign)   → fallback if campaign not found
      3. Create new discussion      → first contact
    """
    with get_conn() as conn:
        cursor = conn.cursor()

        # 1. Best match: same lead AND same campaign
        if campaign_id:
            cursor.execute("""
                SELECT id FROM discussions
                WHERE lead_id = %s AND campaign_id = %s
                ORDER BY created_at DESC LIMIT 1
            """, (lead_id, campaign_id))
            row = cursor.fetchone()
            if row:
                cursor.execute("UPDATE discussions SET last_message_at = NOW() WHERE id = %s", (row[0],))
                return row[0]

        # 2. Fallback: same lead, no campaign filter (e.g. calendar events)
        cursor.execute("""
            SELECT id FROM discussions
            WHERE lead_id = %s
            ORDER BY created_at DESC LIMIT 1
        """, (lead_id,))
        row = cursor.fetchone()
        if row:
            cursor.execute("UPDATE discussions SET last_message_at = NOW() WHERE id = %s", (row[0],))
            return row[0]

        # 3. Create new discussion
        cursor.execute("""
            INSERT INTO discussions (lead_id, campaign_id, subject)
            VALUES (%s, %s, %s) RETURNING id
        """, (lead_id, campaign_id, subject))
        return cursor.fetchone()[0]


def add_message(discussion_id: int, lead_id: str, direction: str,
                subject: str, body: str, from_email: str = None,
                sequence_id: int = None, message_id: str = None,
                in_reply_to: str = None, sentiment: str = None) -> int:
    """Add a sent or received message to a discussion. Returns the new message id."""
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO messages
              (discussion_id, lead_id, direction, subject, body,
               from_email, sequence_id, message_id, in_reply_to, sentiment)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id
        """, (discussion_id, lead_id, direction, subject, body,
              from_email, sequence_id, message_id, in_reply_to, sentiment))
        new_id = cursor.fetchone()[0]
        # Keep discussion.last_message_at fresh
        if direction == "received":
            cursor.execute(
                "UPDATE discussions SET last_message_at = NOW(), has_reply = TRUE WHERE id = %s",
                (discussion_id,)
            )
        return new_id


def get_discussions(campaign_id: str = None, limit: int = 100) -> list:
    """Return discussions with lead info and last message preview."""
    with get_conn() as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        if campaign_id:
            cursor.execute("""
                SELECT d.*, l.name AS lead_name, l.company, l.email AS lead_email,
                       l.segment,
                       (SELECT body FROM messages WHERE discussion_id = d.id
                        ORDER BY created_at DESC LIMIT 1) AS last_body,
                       (SELECT direction FROM messages WHERE discussion_id = d.id
                        ORDER BY created_at DESC LIMIT 1) AS last_direction,
                       (SELECT COUNT(*) FROM messages WHERE discussion_id = d.id
                        AND direction = 'received') AS reply_count
                FROM discussions d
                JOIN leads l ON l.id = d.lead_id
                WHERE d.campaign_id = %s
                ORDER BY d.last_message_at DESC
                LIMIT %s
            """, (campaign_id, limit))
        else:
            cursor.execute("""
                SELECT d.*, l.name AS lead_name, l.company, l.email AS lead_email,
                       l.segment,
                       (SELECT body FROM messages WHERE discussion_id = d.id
                        ORDER BY created_at DESC LIMIT 1) AS last_body,
                       (SELECT direction FROM messages WHERE discussion_id = d.id
                        ORDER BY created_at DESC LIMIT 1) AS last_direction,
                       (SELECT COUNT(*) FROM messages WHERE discussion_id = d.id
                        AND direction = 'received') AS reply_count
                FROM discussions d
                JOIN leads l ON l.id = d.lead_id
                ORDER BY d.last_message_at DESC
                LIMIT %s
            """, (limit,))
        rows = cursor.fetchall()
        result = []
        for r in rows:
            r = dict(r)
            for f in ("last_message_at", "created_at"):
                if r.get(f) and hasattr(r[f], "isoformat"):
                    r[f] = r[f].isoformat()
            result.append(r)
        return result


def get_discussion_messages(discussion_id: int) -> list:
    """Return all messages in a discussion ordered chronologically."""
    with get_conn() as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("""
            SELECT * FROM messages
            WHERE discussion_id = %s
            ORDER BY created_at ASC
        """, (discussion_id,))
        rows = cursor.fetchall()
        result = []
        for r in rows:
            r = dict(r)
            if r.get("created_at") and hasattr(r["created_at"], "isoformat"):
                r["created_at"] = r["created_at"].isoformat()
            result.append(r)
        return result


def get_lead_discussion(lead_id: str) -> dict | None:
    """Return the most recent discussion for a lead."""
    with get_conn() as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("""
            SELECT * FROM discussions WHERE lead_id = %s ORDER BY created_at DESC LIMIT 1
        """, (lead_id,))
        row = cursor.fetchone()
        if not row:
            return None
        r = dict(row)
        for f in ("last_message_at", "created_at"):
            if r.get(f) and hasattr(r[f], "isoformat"):
                r[f] = r[f].isoformat()
        return r