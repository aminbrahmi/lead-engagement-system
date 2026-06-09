"""
tracker_node.py — Agent 6: Response tracking + sentiment classification.

Monitors inbox via IMAP, classifies replies using LLM, tracks opens/clicks,
manages unsubscribes, and generates real-time notifications.

Components:
  1. IMAP inbox monitor — polls for new replies matching sent emails
  2. Sentiment classifier — LLM classifies: interested, not_interested, info_request, ooo, bounce
  3. Open/click tracker — pixel tracking endpoint + link redirect
  4. Unsubscribe handler — RGPD-compliant opt-out
  5. Notification system — stores alerts for frontend polling
"""

import imaplib
import email
import json
import os
import re
import hashlib
import threading
from datetime import datetime
from email.header import decode_header
from concurrent.futures import ThreadPoolExecutor

_tracker_lock = threading.Lock()

from langchain_core.messages import HumanMessage, SystemMessage

from dotenv import load_dotenv
load_dotenv()


# ── Config ────────────────────────────────────────────────────────────────────

IMAP_HOST = os.getenv("IMAP_HOST", "imap.gmail.com")
IMAP_PORT = int(os.getenv("IMAP_PORT", "993"))
IMAP_USER = os.getenv("IMAP_USER") or os.getenv("SMTP_USER", "")
IMAP_PASS = os.getenv("IMAP_PASS") or os.getenv("SMTP_PASS", "")

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# ── Persistent IMAP connection ────────────────────────────────────────────────
_imap_conn: imaplib.IMAP4_SSL | None = None
_imap_lock = threading.Lock()

def _get_imap_conn() -> imaplib.IMAP4_SSL:
    """Return a cached IMAP connection, reconnecting if stale or broken."""
    global _imap_conn
    with _imap_lock:
        # Test if existing connection is still alive
        if _imap_conn is not None:
            try:
                _imap_conn.noop()
            except Exception:
                _imap_conn = None

        if _imap_conn is None:
            conn = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
            conn.login(IMAP_USER, IMAP_PASS)
            _imap_conn = conn
            print(f"[IMAP] New connection established ({IMAP_HOST})")

        return _imap_conn


# ── Sentiment classification via Groq LLM ─────────────────────────────────────

_CLASSIFIER_SYSTEM = """You are an email response classifier for B2B outreach.
Classify the reply into exactly ONE category:

- interested: wants to learn more, asks for a call/demo, positive signal
- not_interested: explicit decline, asks to stop, not relevant
- info_request: asks a specific question, wants more details before deciding
- ooo: out of office / auto-reply / vacation
- bounce: delivery failure / email not found / permanent error

Return ONLY a JSON object (no fences):
{"sentiment": "interested|not_interested|info_request|ooo|bounce", "confidence": 0.0-1.0, "summary": "1 sentence"}"""


def classify_sentiment(reply_body: str, original_subject: str = "") -> dict:
    """Classify an email reply — uses get_writer_llm() for key rotation + provider fallbacks."""
    from agents.llm_factory import get_writer_llm
    fallback = {"sentiment": "info_request", "confidence": 0.0, "summary": "Classification unavailable"}
    try:
        llm = get_writer_llm()   # 4 Groq keys + Gemini + Together + OpenRouter
        prompt = f"""Original email subject: "{original_subject}"

Reply received:
{reply_body[:1500]}

Classify this reply."""
        response = llm.invoke([
            SystemMessage(content=_CLASSIFIER_SYSTEM),
            HumanMessage(content=prompt),
        ])
        content = re.sub(r'```json|```', '', response.content or '').strip()
        try:
            return json.loads(content)
        except Exception:
            m = re.search(r'\{.*\}', content, re.DOTALL)
            if m:
                return json.loads(m.group(0))
            return {"sentiment": "info_request", "confidence": 0.3, "summary": "Parse error"}
    except Exception as e:
        print(f"[Tracker] Classification error: {e}")
        return fallback


# ── Google Calendar notification parser ──────────────────────────────────────

def _parse_calendar_notification(subject: str, body: str, from_email: str) -> dict | None:
    """
    Detect and parse Google Calendar invitation responses (accept/decline/tentative).
    Returns a dict with clean event info, or None if not a calendar notification.
    """
    subj_lower = subject.lower()
    body_lower = body.lower()

    # Strong subject-based signals (work even for HTML-only emails with empty text body)
    cal_subject_prefixes = (
        "accepté :", "accepté:", "acceptée :", "acceptée:",
        "accepted:", "accepted :",
        "refusé :", "refusé:", "refusée:", "refusée :",
        "declined:", "declined :",
        "peut-être:", "peut-être :", "tentative:", "maybe:",
    )
    subject_is_cal = any(subj_lower.startswith(p) for p in cal_subject_prefixes)

    # Body-based signals
    is_calendar = (
        subject_is_cal
        or "calendar-notification@google.com" in from_email.lower()
        or "invite-noreply@google.com" in from_email.lower()
        or "calendar.google.com" in body_lower
        or "google.com/calendar" in body_lower
    )
    if not is_calendar:
        return None

    # Determine response type
    if any(w in subj_lower for w in ("accepté", "accepted", "acceptée")):
        status = "accepted"
    elif any(w in subj_lower for w in ("refusé", "declined", "refusée")):
        status = "declined"
    elif any(w in subj_lower for w in ("peut-être", "tentative", "maybe")):
        status = "tentative"
    else:
        status = "response"

    # Extract who responded
    responder = None
    for pattern in [
        r"(.+?)\s+a\s+accept",       # French: "Jean a accepté"
        r"(.+?)\s+a\s+refus",        # French: "Jean a refusé"
        r"(.+?)\s+accepted\s+your",  # English
        r"(.+?)\s+declined\s+your",  # English
    ]:
        m = re.search(pattern, body, re.IGNORECASE)
        if m:
            responder = m.group(1).strip()
            break

    # Extract Meet link
    meet_link = None
    m = re.search(r'https://meet\.google\.com/[a-z0-9\-?&=]+', body)
    if m:
        meet_link = m.group(0).split()[0].rstrip(')')

    # Extract event title from subject (remove prefix like "Accepté: ")
    event_title = re.sub(
        r'^(accept[eé]e?|refus[eé]e?|peut-être|tentative|accepted|declined|maybe)\s*:\s*',
        '', subject, flags=re.IGNORECASE
    ).strip()

    return {
        "status":      status,
        "responder":   responder,
        "event_title": event_title,
        "meet_link":   meet_link,
    }


def _find_lead_from_event_title(event_title: str) -> dict | None:
    """
    Extract lead name / company from the meeting title and find the matching discussion.
    Title format: "Meeting with {Lead Name} ({Company})"
    """
    from memory.storage import get_conn
    from psycopg2.extras import RealDictCursor

    # Parse "Meeting with Name (Company)" or "Meeting with Name"
    m = re.search(r'(?:meeting\s+with\s+)(.+?)(?:\s+\((.+?)\))?(?:\s*[-–].*)?$',
                  event_title, re.IGNORECASE)
    if not m:
        return None

    name_hint    = m.group(1).strip()
    company_hint = m.group(2).strip() if m.group(2) else None

    try:
        with get_conn() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            if company_hint:
                cursor.execute("""
                    SELECT d.id AS disc_id, d.lead_id, d.campaign_id, l.name, l.company
                    FROM discussions d JOIN leads l ON l.id = d.lead_id
                    WHERE (l.company ILIKE %s OR l.name ILIKE %s)
                    ORDER BY d.last_message_at DESC LIMIT 1
                """, (f'%{company_hint}%', f'%{name_hint}%'))
            else:
                cursor.execute("""
                    SELECT d.id AS disc_id, d.lead_id, d.campaign_id, l.name, l.company
                    FROM discussions d JOIN leads l ON l.id = d.lead_id
                    WHERE l.name ILIKE %s
                    ORDER BY d.last_message_at DESC LIMIT 1
                """, (f'%{name_hint}%',))
            row = cursor.fetchone()
            return dict(row) if row else None
    except Exception as e:
        print(f"[Tracker] Event title lead lookup error: {e}")
        return None


def _handle_calendar_event(cal: dict, matched_seq: dict, lead_name: str,
                            company: str, message_id: str):
    """Save a calendar acceptance as a clean event message + create notification."""
    from memory.storage import get_or_create_discussion, get_conn as _gc

    status      = cal.get("status", "response")
    event_title = cal.get("event_title", "Meeting")
    meet_link   = cal.get("meet_link", "")
    lead_id     = matched_seq.get("lead_id", "")
    campaign_id = matched_seq.get("campaign_id", "")

    # ── Find the correct lead from the event title (more reliable than email) ──
    correct = _find_lead_from_event_title(event_title)
    if correct:
        lead_id     = correct["lead_id"]
        campaign_id = correct["campaign_id"]
        lead_name   = correct["name"] or lead_name
        company     = correct["company"] or company
        print(f"[Tracker] Calendar event matched by title → {lead_name} @ {company}")

    # Clean event title — strip timestamp suffix like " - Mon. 2"
    clean_title = re.split(r'\s+-\s+\w{3}\.?\s+\d', event_title)[0].strip()

    # Build conversation body — Meet link only shown for accepted meetings
    action = {"accepted": "confirmed", "declined": "declined"}.get(status, "responded to")
    clean_body = f"Meeting {action} with {lead_name}."
    if meet_link and status == "accepted":
        clean_body += f"\n\nGoogle Meet: {meet_link}"

    # Save as "event" message — two-level dedup:
    #   1. by message_id (same email reprocessed)
    #   2. by (lead_id, body, 1h window) — catches multiple Google Calendar
    #      notification emails for the same status change (different message_ids)
    already_saved = False
    try:
        disc_id = get_or_create_discussion(lead_id, campaign_id, event_title)
        with _gc() as conn:
            c = conn.cursor()

            # Level 1 — exact message_id
            if message_id:
                c.execute("SELECT 1 FROM messages WHERE message_id = %s LIMIT 1", (message_id,))
                if c.fetchone():
                    already_saved = True

            # Level 2 — same lead + same body in the last hour
            # (handles multiple Google Calendar notification emails for one event change)
            if not already_saved:
                c.execute("""
                    SELECT 1 FROM messages
                    WHERE lead_id = %s AND direction = 'event'
                      AND body = %s
                      AND created_at > NOW() - INTERVAL '1 hour'
                    LIMIT 1
                """, (lead_id, clean_body))
                if c.fetchone():
                    already_saved = True

            if not already_saved:
                c.execute("""
                    INSERT INTO messages
                      (discussion_id, lead_id, direction, subject, body,
                       message_id, notification_sent)
                    VALUES (%s, %s, 'event', %s, %s, %s, TRUE)
                """, (disc_id, lead_id,
                      f"Meeting {status}: {event_title}",
                      clean_body,
                      message_id or None))
    except Exception as e:
        print(f"[Tracker] Calendar event save error: {e}")

    # Already saved means notification was already created — skip entirely
    if already_saved:
        print(f"[Tracker] Calendar event already processed — skipping notification")
        return

    # Build notification text
    icon = {"accepted": "calendar_accepted", "declined": "calendar_declined"}.get(status, "calendar_response")
    if status == "accepted":
        msg = f"Meeting confirmed with {lead_name} @ {company}: {clean_title}"
        if meet_link:
            msg += f" | Meet: {meet_link}"
    elif status == "declined":
        msg = f"{lead_name} @ {company} declined the meeting: {clean_title}"
    else:
        msg = f"{lead_name} @ {company} responded ({status}) to: {clean_title}"

    _create_notification(campaign_id, lead_id, icon, msg,
                         {"meet_link": meet_link if status == "accepted" else "",
                          "status": status,
                          "event_title": clean_title, "lead_name": lead_name,
                          "reply_message_id": message_id})
    print(f"[Tracker] Calendar {status}: {lead_name} @ {company} — {clean_title}")


# ── IMAP inbox monitoring ─────────────────────────────────────────────────────

def _decode_header_value(value):
    """Decode MIME-encoded email header."""
    if not value:
        return ""
    decoded_parts = decode_header(value)
    parts = []
    for part, charset in decoded_parts:
        if isinstance(part, bytes):
            parts.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            parts.append(part)
    return " ".join(parts)


def _extract_reply_body(msg) -> str:
    """Extract plain text body from email message."""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type == "text/plain":
                try:
                    return part.get_payload(decode=True).decode("utf-8", errors="replace")
                except Exception:
                    continue
    else:
        try:
            return msg.get_payload(decode=True).decode("utf-8", errors="replace")
        except Exception:
            return ""
    return ""


# Patterns that mark the start of the quoted/forwarded section in a reply
_QUOTE_SEPARATORS = re.compile(
    r"^(-{3,}|_{3,}|On .{5,} wrote:\s*$"
    r"|From\s*:\s.+|De\s*:\s.+"          # Outlook: "From: " / "De : "
    r"|-----\s*Original Message\s*-----"
    r"|________________________________)",
    re.IGNORECASE | re.MULTILINE,
)


def _strip_quoted_text(body: str) -> str:
    """Keep only the new content of a reply — strip the quoted original message."""
    if not body:
        return body

    lines = body.splitlines()
    cutoff = len(lines)

    for i, line in enumerate(lines):
        stripped = line.strip()
        # Lines starting with > are quoted text
        if stripped.startswith(">"):
            cutoff = i
            break
        # Blank line followed by "On ... wrote:" pattern
        if _QUOTE_SEPARATORS.match(stripped):
            # Walk back past any preceding blank lines
            cutoff = i
            while cutoff > 0 and not lines[cutoff - 1].strip():
                cutoff -= 1
            break

    result = "\n".join(lines[:cutoff]).strip()
    return result if result else body.strip()


def check_inbox(since_hours: int = 24) -> list:
    """Check IMAP inbox for new replies. Returns list of parsed replies."""
    if not IMAP_USER or not IMAP_PASS:
        print("[Tracker] IMAP credentials not configured. Skipping inbox check.")
        return []

    replies = []

    try:
        mail = _get_imap_conn()
        mail.select("INBOX")

        # Search for recent emails (replies typically have "Re:" in subject)
        from datetime import timedelta
        since_date = (datetime.now() - timedelta(hours=since_hours)).strftime("%d-%b-%Y")
        _, msg_ids = mail.search(None, f'(SINCE {since_date})')

        if not msg_ids[0]:
            return []

        ids = msg_ids[0].split()
        print(f"[Tracker] Found {len(ids)} emails since {since_date}")

        for msg_id in ids[-20:]:  # Process last 20 max (scanner tourne toutes les 2 min)
            _, msg_data = mail.fetch(msg_id, "(RFC822)")
            if not msg_data or not msg_data[0]:
                continue

            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)

            from_addr = _decode_header_value(msg.get("From", ""))
            subject = _decode_header_value(msg.get("Subject", ""))
            date_str = _decode_header_value(msg.get("Date", ""))
            message_id = msg.get("Message-ID", "")
            # In-Reply-To may be absent in some clients (Gmail self-reply); fall back to References
            in_reply_to = msg.get("In-Reply-To", "").strip()
            if not in_reply_to:
                refs = msg.get("References", "").strip()
                if refs:
                    in_reply_to = refs.split()[-1]  # last message-id in thread chain
            raw_body = _extract_reply_body(msg)  # full body for calendar parsing
            body     = _strip_quoted_text(raw_body)

            # Extract email address from "Name <email>" format
            email_match = re.search(r'[\w.-]+@[\w.-]+', from_addr)
            from_email = email_match.group(0) if email_match else from_addr

            # ── Detect Google Calendar notifications ──────────────────────
            cal_event = _parse_calendar_notification(subject, raw_body, from_email)
            if cal_event:
                replies.append({
                    "from_email": from_email,
                    "from_name": from_addr.split("<")[0].strip().strip('"'),
                    "subject": subject,
                    "body": body[:3000],
                    "date": date_str,
                    "message_id": message_id,
                    "in_reply_to": in_reply_to,
                    "is_reply": True,
                    "calendar_event": cal_event,  # special marker
                })
                continue

            # Skip our own sent emails UNLESS they have In-Reply-To (= test reply to self)
            is_own = from_email.lower() == IMAP_USER.lower()
            is_reply = bool(in_reply_to) or subject.lower().startswith("re:")
            if is_own and not is_reply:
                continue

            replies.append({
                "from_email": from_email,
                "from_name": from_addr.split("<")[0].strip().strip('"'),
                "subject": subject,
                "body": body[:3000],
                "date": date_str,
                "message_id": message_id,
                "in_reply_to": in_reply_to,
                "is_reply": subject.lower().startswith("re:"),
            })

        print(f"[Tracker] Parsed {len(replies)} potential replies")

    except imaplib.IMAP4.error as e:
        print(f"[Tracker] IMAP error: {e}")
        global _imap_conn
        _imap_conn = None  # force reconnect next scan
    except Exception as e:
        print(f"[Tracker] Inbox check failed: {e}")
        _imap_conn = None

    return replies


# ── Match replies to leads ────────────────────────────────────────────────────

def _norm_msgid(mid: str) -> str:
    """Normalise a Message-ID: strip whitespace and angle brackets for comparison."""
    return mid.strip().strip("<>").lower()


def _strip_re(subject: str) -> str:
    """Remove Re:/RE:/Fwd: prefixes for subject matching."""
    return re.sub(r'^(re|fwd|fw|rép|réf)\s*:\s*', '', subject.strip(), flags=re.IGNORECASE).strip().lower()


def _most_recent(candidates: list) -> dict | None:
    """Among several matching sequences, return the one sent most recently."""
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]

    def _ts(seq):
        v = seq.get("sent_at")
        if v is None:
            return ""
        # datetime object → isoformat; already a string → keep as-is
        return v.isoformat() if hasattr(v, "isoformat") else str(v)

    return max(candidates, key=_ts)


def match_reply_to_lead(reply: dict, sent_sequences: list) -> dict | None:
    """Match an incoming reply to a lead's sequence.

    Steps (in order of reliability):
      1. In-Reply-To / References  → exact message_id  (always unique)
      2. Email + subject combined  → most recent match (handles testing with own email)
      3. Email only                → most recently sent to that address
      4. Lead email only           → most recently sent to that lead
      5. Subject only              → most recently sent with that subject
    """
    from_email    = reply.get("from_email", "").lower()
    in_reply_to   = _norm_msgid(reply.get("in_reply_to", ""))
    reply_subject = _strip_re(reply.get("subject", ""))

    # 1. Exact message-id — unambiguous, always preferred
    if in_reply_to:
        for seq in sent_sequences:
            stored_mid = _norm_msgid(seq.get("message_id") or "")
            if stored_mid and stored_mid == in_reply_to:
                return seq

    # 2. Email + subject combined — critical when testing with own email address:
    #    multiple leads share the same email, so the reply subject ("Re: XYZ")
    #    uniquely identifies which lead the reply belongs to.
    if from_email and reply_subject:
        candidates = [
            seq for seq in sent_sequences
            if (seq.get("recipient_email", "").lower() == from_email
                or seq.get("email", "").lower() == from_email)
            and _strip_re(seq.get("subject", "")) == reply_subject
        ]
        match = _most_recent(candidates)
        if match:
            return match

    # 3. Email match only → most recently sent to that address
    if from_email:
        candidates = [
            seq for seq in sent_sequences
            if seq.get("recipient_email", "").lower() == from_email
        ]
        match = _most_recent(candidates)
        if match:
            return match

    # 4. Lead email match → most recently sent to that lead
    if from_email:
        candidates = [
            seq for seq in sent_sequences
            if seq.get("email", "").lower() == from_email
        ]
        match = _most_recent(candidates)
        if match:
            return match

    # 5. Subject fallback → most recent match
    if reply_subject:
        candidates = [
            seq for seq in sent_sequences
            if _strip_re(seq.get("subject", "")) == reply_subject
        ]
        match = _most_recent(candidates)
        if match:
            return match

    return None


# ── Open/click tracking ───────────────────────────────────────────────────────

def generate_tracking_pixel_url(sequence_id: int, base_url: str = "") -> str:
    """Generate a 1x1 pixel tracking URL for open detection."""
    base = base_url or os.getenv("REACT_APP_API_URL", "http://localhost:8000")
    token = hashlib.md5(f"open-{sequence_id}".encode()).hexdigest()[:16]
    return f"{base}/track/open/{sequence_id}/{token}"


def generate_click_url(sequence_id: int, target_url: str, base_url: str = "") -> str:
    """Generate a redirect URL for click tracking."""
    base = base_url or os.getenv("REACT_APP_API_URL", "http://localhost:8000")
    import urllib.parse
    encoded = urllib.parse.quote(target_url, safe="")
    return f"{base}/track/click/{sequence_id}?url={encoded}"


def generate_unsubscribe_url(lead_id: str, base_url: str = "") -> str:
    """Generate RGPD-compliant unsubscribe link with a signed (HMAC) token."""
    from utils.tokens import make_token
    base = base_url or os.getenv("REACT_APP_API_URL", "http://localhost:8000")
    token = make_token(lead_id)
    return f"{base}/unsubscribe/{lead_id}/{token}"


# ── Main tracking loop ────────────────────────────────────────────────────────

_last_tracker_run: datetime | None = None

def run_tracker(campaign_id: str = None) -> dict:
    """Main Agent 6 entry point. Skips if already running (prevents duplicate notifications)."""
    if not _tracker_lock.acquire(blocking=False):
        print("[Tracker] Already running — skipping concurrent call")
        return {"replies_found": 0, "classified": 0, "matched": 0, "notifications": 0}
    try:
        return _run_tracker_inner(campaign_id)
    finally:
        _tracker_lock.release()


def _run_tracker_inner(campaign_id: str = None) -> dict:
    """Internal tracker logic — called only when lock is acquired."""
    global _last_tracker_run
    from memory.storage import (
        get_conn, update_sequence_status,
        cancel_remaining_sequence, log_campaign_event,
    )
    from psycopg2.extras import RealDictCursor

    print(f"\n[AGENT 6] Starting response tracking...")
    stats = {"replies_found": 0, "classified": 0, "matched": 0, "notifications": 0}

    # 1. Get all sent sequences to match against
    sent_sequences = []
    with get_conn() as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        # ── email_sequences — include sent_at so _most_recent() can sort correctly ──
        if campaign_id:
            cursor.execute("""
                SELECT es.id, es.message_id, es.subject, es.lead_id, es.campaign_id,
                       l.email, l.name, l.company,
                       COALESCE(es.recipient_email, l.email) AS recipient_email,
                       COALESCE(es.sent_at, es.created_at) AS sent_at
                FROM email_sequences es JOIN leads l ON l.id = es.lead_id
                WHERE es.campaign_id = %s AND es.status IN ('sent', 'replied')
            """, (campaign_id,))
        else:
            cursor.execute("""
                SELECT es.id, es.message_id, es.subject, es.lead_id, es.campaign_id,
                       l.email, l.name, l.company,
                       COALESCE(es.recipient_email, l.email) AS recipient_email,
                       COALESCE(es.sent_at, es.created_at) AS sent_at
                FROM email_sequences es JOIN leads l ON l.id = es.lead_id
                WHERE es.status IN ('sent', 'replied')
            """)
        sent_sequences = [dict(r) for r in cursor.fetchall()]

        # ── messages table: sent via inbox Reply composer — include created_at ──
        cursor.execute("""
            SELECT NULL AS id,
                   m.message_id, m.subject, m.lead_id, d.campaign_id,
                   l.email, l.name, l.company,
                   l.email AS recipient_email,
                   m.created_at AS sent_at
            FROM messages m
            JOIN discussions d ON d.id = m.discussion_id
            JOIN leads       l ON l.id = m.lead_id
            WHERE m.direction = 'sent' AND m.message_id IS NOT NULL
        """)
        sent_sequences += [dict(r) for r in cursor.fetchall()]

    # Deduplicate by message_id — keep only the first occurrence per message_id
    # (avoids double-matching when the same email exists in both tables)
    seen_mids: set = set()
    deduped: list = []
    for seq in sent_sequences:
        mid = (seq.get("message_id") or "").strip()
        if mid and mid in seen_mids:
            continue
        if mid:
            seen_mids.add(mid)
        deduped.append(seq)
    sent_sequences = deduped

    if not sent_sequences:
        print("[Tracker] No sent emails to track.")
        return stats

    print(f"[Tracker] Tracking {len(sent_sequences)} sent email/message references")

    # 2. Check inbox for replies — use a tight window when called automatically
    from datetime import timedelta
    if _last_tracker_run:
        delta_minutes = (datetime.now() - _last_tracker_run).total_seconds() / 60
        since_h = max(1, min(int(delta_minutes / 60) + 1, 4))
    else:
        since_h = 24  # first run: look back 24h to catch anything missed
    _last_tracker_run = datetime.now()
    replies = check_inbox(since_hours=since_h)
    stats["replies_found"] = len(replies)

    # 3. Match and classify each reply
    # No per-run dedup set — notification_sent flag on the messages table is the
    # single source of truth, allowing multiple genuine replies from the same lead.
    processed_mids = set()  # avoid re-processing the same IMAP email twice in one run

    for reply in replies:
        matched_seq = match_reply_to_lead(reply, sent_sequences)
        if not matched_seq:
            continue

        # Within a single run, skip the same raw email if it matched multiple sequences
        reply_key = reply.get("message_id") or f"{reply.get('from_email')}|{reply.get('subject')}"
        if reply_key in processed_mids:
            continue
        processed_mids.add(reply_key)

        stats["matched"] += 1
        lead_name = matched_seq.get("name", "Unknown")
        company   = matched_seq.get("company", "Unknown")

        # ── Google Calendar acceptance — handle separately, skip LLM ────────
        cal = reply.get("calendar_event")
        if cal:
            _handle_calendar_event(
                cal, matched_seq, lead_name, company, reply.get("message_id", "")
            )
            stats["notifications"] += 1
            continue

        # ── Skip emails with empty/too-short body — avoids false "declined" on auto-replies ──
        body_text = (reply.get("body") or "").strip()
        if len(body_text.split()) < 4:
            print(f"[Tracker] Body too short ({len(body_text.split())} words) — skip classification")
            continue

        # ── Check notification_sent BEFORE calling LLM — saves tokens ──────
        from memory.storage import get_or_create_discussion, add_message, get_conn as _gc
        reply_mid = reply.get("message_id", "")
        msg_id_db = None
        existing  = None

        try:
            with _gc() as _conn:
                _c = _conn.cursor()
                if reply_mid:
                    _c.execute("SELECT id, notification_sent FROM messages WHERE message_id = %s LIMIT 1",
                               (reply_mid,))
                else:
                    _c.execute("""SELECT id, notification_sent FROM messages
                                  WHERE lead_id=%s AND direction='received'
                                    AND subject=%s AND from_email=%s
                                  ORDER BY created_at DESC LIMIT 1""",
                               (matched_seq["lead_id"], reply.get("subject",""), reply.get("from_email","")))
                existing = _c.fetchone()
        except Exception as e:
            print(f"[Tracker] Pre-check error: {e}")

        if existing:
            msg_id_db, notif_sent = existing
            if notif_sent:
                print(f"[Tracker] Already processed — skip (no LLM call)")
                continue
            # Saved but not yet notified — classify and notify, skip re-saving

        print(f"[Tracker] Reply matched: {lead_name} @ {company}")

        # 4. Classify sentiment — only reached for truly new/unnotified replies
        classification = classify_sentiment(
            reply["body"],
            original_subject=matched_seq.get("subject", ""),
        )
        sentiment  = classification.get("sentiment", "info_request")
        confidence = classification.get("confidence", 0)
        summary    = classification.get("summary", "")
        stats["classified"] += 1

        print(f"[Tracker] Classified: {sentiment} (confidence: {confidence:.0%}) — {summary}")

        # 5. Update sequence status
        if matched_seq.get("id") is not None:
            update_sequence_status(matched_seq["id"], "replied")

        # 5b. Save reply if not already in DB
        if not existing:
            try:
                disc_id = get_or_create_discussion(
                    matched_seq["lead_id"],
                    matched_seq.get("campaign_id", ""),
                    matched_seq.get("subject", ""),
                )
                msg_id_db = add_message(
                    disc_id,
                    matched_seq["lead_id"],
                    "received",
                    subject=reply.get("subject", ""),
                    body=reply.get("body", ""),
                    from_email=reply.get("from_email", ""),
                    message_id=reply_mid,
                    in_reply_to=reply.get("in_reply_to", ""),
                    sentiment=sentiment,
                )
            except Exception as e:
                print(f"[Tracker] Discussion update error: {e}")
                msg_id_db = None

        # 6. Auto-actions based on sentiment
        base_meta = {"sentiment": sentiment, "confidence": confidence,
                     "reply_message_id": reply_mid}

        if sentiment == "interested":
            cancel_remaining_sequence(matched_seq["lead_id"])
            _create_notification(
                matched_seq.get("campaign_id", ""),
                matched_seq["lead_id"],
                "reply_interested",
                f"{lead_name} @ {company} is interested: {summary}",
                base_meta,
            )

        elif sentiment == "not_interested":
            cancel_remaining_sequence(matched_seq["lead_id"])
            _create_notification(
                matched_seq.get("campaign_id", ""),
                matched_seq["lead_id"],
                "reply_declined",
                f"{lead_name} @ {company} declined: {summary}",
                base_meta,
            )

        elif sentiment == "ooo":
            _create_notification(
                matched_seq.get("campaign_id", ""),
                matched_seq["lead_id"],
                "reply_ooo",
                f"{lead_name} @ {company} is out of office",
                base_meta,
            )

        elif sentiment == "bounce":
            cancel_remaining_sequence(matched_seq["lead_id"])
            _create_notification(
                matched_seq.get("campaign_id", ""),
                matched_seq["lead_id"],
                "email_bounced",
                f"Email to {company} bounced — invalid address",
                base_meta,
            )

        elif sentiment == "info_request":
            _create_notification(
                matched_seq.get("campaign_id", ""),
                matched_seq["lead_id"],
                "reply_info_request",
                f"{lead_name} @ {company} asked for more info: {summary}",
                {**base_meta, "reply_preview": reply["body"][:200]},
            )

        # Mark notification_sent = TRUE on the message row — prevents re-notification on next run
        if msg_id_db:
            try:
                with _gc() as _conn:
                    _c = _conn.cursor()
                    _c.execute("UPDATE messages SET notification_sent = TRUE WHERE id = %s",
                               (msg_id_db,))
            except Exception as e:
                print(f"[Tracker] Could not mark notification_sent: {e}")

        # Log event
        log_campaign_event(
            matched_seq.get("campaign_id", ""),
            "Tracker",
            f"reply_{sentiment}",
            f"Reply from {lead_name} @ {company}: {sentiment}",
            {"sentiment": sentiment, "confidence": confidence, "summary": summary},
        )
        stats["notifications"] += 1

    print(f"[Agent 6] Done: {stats['matched']} matched, {stats['classified']} classified, {stats['notifications']} notifications")
    return stats


# ── Notifications ─────────────────────────────────────────────────────────────

def _create_notification(campaign_id: str, lead_id: str, notif_type: str,
                         message: str, metadata: dict = None):
    """Store a notification — deduplicated by reply message_id to allow multiple
    genuine replies from the same lead without blocking them."""
    from memory.storage import get_conn
    try:
        meta_str = json.dumps(metadata) if metadata else None

        reply_mid = (metadata or {}).get("reply_message_id", "")

        with get_conn() as conn:
            cursor = conn.cursor()
            if reply_mid:
                # Dedup by message_id in metadata
                cursor.execute("""
                    INSERT INTO lead_notifications (campaign_id, lead_id, type, message, metadata)
                    SELECT %s, %s, %s, %s, %s
                    WHERE NOT EXISTS (
                        SELECT 1 FROM lead_notifications
                        WHERE lead_id = %s AND type = %s
                          AND metadata::text LIKE %s
                    )
                """, (campaign_id, lead_id, notif_type, message, meta_str,
                      lead_id, notif_type, f'%{reply_mid}%'))
            else:
                # Dedup by exact message content — prevents identical notifications
                # regardless of timing (covers calendar events with no message_id)
                cursor.execute("""
                    INSERT INTO lead_notifications (campaign_id, lead_id, type, message, metadata)
                    SELECT %s, %s, %s, %s, %s
                    WHERE NOT EXISTS (
                        SELECT 1 FROM lead_notifications
                        WHERE lead_id = %s AND type = %s AND message = %s
                    )
                """, (campaign_id, lead_id, notif_type, message, meta_str,
                      lead_id, notif_type, message))
    except Exception as e:
        print(f"[Tracker] Notification error: {e}")


def get_notifications(unread_only: bool = True, limit: int = 50) -> list:
    """Get notifications for the frontend."""
    from memory.storage import get_conn
    from psycopg2.extras import RealDictCursor

    with get_conn() as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        if unread_only:
            cursor.execute("""
                SELECT * FROM notifications
                WHERE read = FALSE
                ORDER BY created_at DESC LIMIT %s
            """, (limit,))
        else:
            cursor.execute("""
                SELECT * FROM notifications
                ORDER BY created_at DESC LIMIT %s
            """, (limit,))
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


def mark_notification_read(notif_id: int):
    from memory.storage import get_conn
    with get_conn() as conn:
        conn.cursor().execute("UPDATE notifications SET read = TRUE WHERE id = %s", (notif_id,))


def mark_all_notifications_read():
    from memory.storage import get_conn
    with get_conn() as conn:
        conn.cursor().execute("UPDATE notifications SET read = FALSE WHERE read = FALSE")


# ── Unsubscribe handling ──────────────────────────────────────────────────────

def handle_unsubscribe(lead_id: str, token: str) -> bool:
    """Process RGPD unsubscribe request."""
    from utils.tokens import verify_token
    if not verify_token(lead_id, token):
        return False

    from memory.storage import get_conn, cancel_remaining_sequence, add_exclusion

    with get_conn() as conn:
        # Get lead email for exclusion
        from psycopg2.extras import RealDictCursor
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT email, company FROM leads WHERE id = %s", (lead_id,))
        lead = cursor.fetchone()

        if lead and lead.get("email"):
            add_exclusion(lead["email"], "email", "RGPD unsubscribe")
        if lead and lead.get("company"):
            add_exclusion(lead["company"], "company", "RGPD unsubscribe")

    cancel_remaining_sequence(lead_id)

    _create_notification(
        "", lead_id, "unsubscribe",
        f"Lead {lead_id} unsubscribed (RGPD)",
        {"lead_id": lead_id},
    )

    print(f"[Tracker] Lead {lead_id} unsubscribed — added to exclusion list")
    return True
