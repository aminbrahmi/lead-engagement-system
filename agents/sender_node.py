"""
sender_node.py — Agent 5: email sending + follow-up sequence management.

Responsibilities:
  1. Generate 3 follow-up emails (J+3, J+7, J+14) for each lead using LLM
  2. Create the full 4-step sequence in DB (initial + 3 follow-ups)
  3. Send the initial email via SMTP
  4. Schedule follow-ups for automatic sending

Follow-up strategy:
  - J+3: gentle nudge — reference the initial email, add a new angle
  - J+7: value-add — share a relevant insight or case study
  - J+14: final breakup — last attempt, give an easy out

The scheduler (run_due_sequences) handles sending follow-ups when they're due.
"""

import json
import re
import os
import smtplib
import ssl
import uuid
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr, make_msgid
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from langchain_core.messages import HumanMessage, SystemMessage

from agents.llm_factory import get_writer_llm
from memory.storage import (
    get_sender_config, create_full_sequence, get_due_sequences,
    update_sequence_status, cancel_remaining_sequence,
    log_campaign_event, is_excluded, get_lead_sequence,
)


# ── Follow-up LLM generation ─────────────────────────────────────────────────

_FOLLOWUP_SYSTEM = (
    "You are a senior B2B outreach strategist. You write professional follow-up emails "
    "that feel natural, not desperate. Each follow-up must add new value — never just "
    "'bumping this up' or 'checking in'. You reference the previous email naturally, "
    "without quoting it. No exclamation marks. No generic openers."
)


def _followup_prompt(lead: dict, initial_email: dict, step: int,
                     campaign_prompt: str, sender_info: dict) -> str:
    """Generate prompt for follow-up at step 1 (J+3), 2 (J+7), or 3 (J+14)."""
    insights = lead.get("insights", {})
    name = lead.get("name", "")
    company = lead.get("company", "")

    sender_name = sender_info.get("name", "[Your Name]")
    sender_title = sender_info.get("title", "")
    sender_company = sender_info.get("company", "")

    signature = sender_name
    if sender_title and sender_company:
        signature = f"{sender_name}\n{sender_title}, {sender_company}"
    elif sender_company:
        signature = f"{sender_name}\n{sender_company}"

    strategies = {
        1: {
            "name": "Gentle nudge (J+3)",
            "rules": (
                "- Acknowledge you reached out a few days ago (don't quote the email)\n"
                "- Add ONE new angle: a metric, a trend, or a specific benefit\n"
                "- Keep it shorter than the initial email (3-4 sentences)\n"
                "- CTA: 'Would a 10-minute call be worth it?'\n"
                "- Tone: respectful, not pushy"
            ),
        },
        2: {
            "name": "Value-add (J+7)",
            "rules": (
                "- Don't mention the previous emails explicitly\n"
                "- Share a relevant insight, stat, or mini case study\n"
                "- Frame it as: 'thought this might be useful for you'\n"
                "- CTA: offer to share a relevant resource or brief analysis\n"
                "- Tone: helpful peer, zero sales pressure"
            ),
        },
        3: {
            "name": "Breakup email (J+14)",
            "rules": (
                "- Acknowledge this is the last follow-up\n"
                "- Be direct: 'if this isn't relevant, no worries at all'\n"
                "- Leave the door open: 'happy to reconnect if timing changes'\n"
                "- Keep it very short (2-3 sentences max)\n"
                "- Tone: professional, graceful exit"
            ),
        },
    }

    strat = strategies.get(step, strategies[1])

    return f"""Campaign: {campaign_prompt}

Lead:
  Name:    {name}
  Role:    {lead.get('role')}
  Company: {company}

Initial email subject: "{initial_email.get('subject', '')}"

Research context:
  Recent news:       {insights.get('recent_news', 'N/A')}
  Company challenge: {insights.get('company_challenge', 'N/A')}
  Value angle:       {insights.get('value_angle', 'N/A')}

Write follow-up: {strat['name']}

Rules:
{strat['rules']}
- Subject: "Re: {initial_email.get('subject', '')}" (keep the thread)
- No exclamation marks
- Sign off with:
  Best regards,
  {signature}

Return ONLY raw JSON (no fences):
{{
  "subject": "Re: {initial_email.get('subject', '')}",
  "body": "..."
}}"""


def _parse_json(content: str) -> dict:
    """Parse LLM response JSON."""
    if isinstance(content, list):
        content = "\n".join(
            b["text"] for b in content if isinstance(b, dict) and b.get("type") == "text"
        )
    content = re.sub(r'```json|```', '', content or '').strip()
    content = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', content)

    try:
        return json.loads(content)
    except Exception:
        pass

    match = re.search(r'\{.*\}', content, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            pass

    s = re.search(r'"subject"\s*:\s*"([^"]+)"', content)
    b = re.search(r'"body"\s*:\s*"(.*?)"(?:\s*[,}])', content, re.DOTALL)
    return {
        "subject": s.group(1) if s else "",
        "body": b.group(1).replace("\\n", "\n") if b else "",
    }


def generate_followups(lead: dict, initial_email: dict,
                       campaign_prompt: str, sender_info: dict) -> list:
    """Generate 3 follow-up emails using LLM."""
    llm = get_writer_llm()
    followups = []

    for step in [1, 2, 3]:
        step_label = {1: "J+3", 2: "J+7", 3: "J+14"}[step]
        try:
            response = llm.invoke([
                SystemMessage(content=_FOLLOWUP_SYSTEM),
                HumanMessage(content=_followup_prompt(
                    lead, initial_email, step, campaign_prompt, sender_info
                )),
            ])
            email = _parse_json(response.content)
            followups.append(email)
            print(f"[Sender] ✓ Follow-up {step_label} generated for {lead.get('company')}")
        except Exception as e:
            print(f"[Sender] ⚠ Follow-up {step_label} failed for {lead.get('company')}: {e}")
            # Fallback: simple follow-up
            followups.append({
                "subject": f"Re: {initial_email.get('subject', '')}",
                "body": f"Hi {lead.get('name', '').split()[0] if lead.get('name') else 'there'},\n\n"
                        f"Wanted to follow up on my previous note. "
                        f"Would love to find 10 minutes to discuss how we might help {lead.get('company', 'your team')}.\n\n"
                        f"Best regards,\n{sender_info.get('name', '[Your Name]')}",
            })

    return followups


# ── SMTP sending ──────────────────────────────────────────────────────────────

def _build_mime_message(sender_config: dict, to_email: str, subject: str,
                        body: str, cc: str = None, message_id: str = None) -> MIMEMultipart:
    """Build a professional MIME email message."""
    msg = MIMEMultipart("alternative")

    msg["From"] = formataddr((sender_config.get("name", ""), sender_config.get("email", "")))
    msg["To"] = to_email
    msg["Subject"] = subject
    msg["Message-ID"] = message_id or make_msgid()
    msg["X-Mailer"] = "LeadFlow/1.0"

    if cc:
        msg["Cc"] = cc

    # Add signature to body
    signature = sender_config.get("signature", "")
    full_body = body
    if signature:
        full_body = f"{body}\n\n---\n{signature}"

    # Plain text version
    msg.attach(MIMEText(full_body, "plain", "utf-8"))

    # HTML version — professional formatting
    html_body = full_body.replace("\n\n", "</p><p>").replace("\n", "<br>")
    html = f"""
    <html>
    <body style="font-family: Arial, sans-serif; font-size: 14px; color: #1a1a2e; line-height: 1.7;">
      <p>{html_body}</p>
    </body>
    </html>
    """
    msg.attach(MIMEText(html, "html", "utf-8"))

    return msg


def send_email(sender_config: dict, to_email: str, subject: str, body: str,
               cc: str = None) -> dict:
    """Send a single email via SMTP. Returns {success, message_id, error}."""
    smtp_host = sender_config.get("smtp_host", os.getenv("SMTP_HOST", "smtp.gmail.com"))
    smtp_port = sender_config.get("smtp_port", int(os.getenv("SMTP_PORT", "587")))
    smtp_user = sender_config.get("smtp_user") or sender_config.get("email") or os.getenv("SMTP_USER", "")
    smtp_pass = sender_config.get("smtp_pass") or os.getenv("SMTP_PASS", "")

    if not smtp_user or not smtp_pass:
        return {"success": False, "message_id": None, "error": "SMTP credentials not configured"}

    message_id = make_msgid()
    msg = _build_mime_message(sender_config, to_email, subject, body, cc, message_id)

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
            server.starttls(context=context)
            server.login(smtp_user, smtp_pass)

            recipients = [to_email]
            if cc:
                recipients.extend([addr.strip() for addr in cc.split(",") if addr.strip()])

            server.sendmail(smtp_user, recipients, msg.as_string())

        print(f"[SMTP] ✓ Sent to {to_email}: {subject}")
        return {"success": True, "message_id": message_id, "error": None}

    except smtplib.SMTPAuthenticationError as e:
        err = f"SMTP authentication failed: {e}"
        print(f"[SMTP] ✗ {err}")
        return {"success": False, "message_id": None, "error": err}
    except smtplib.SMTPRecipientsRefused as e:
        err = f"Recipient refused: {e}"
        print(f"[SMTP] ✗ {err}")
        return {"success": False, "message_id": None, "error": err}
    except Exception as e:
        err = f"SMTP error: {e}"
        print(f"[SMTP] ✗ {err}")
        return {"success": False, "message_id": None, "error": err}


# ── Main agent entry point ────────────────────────────────────────────────────

def _process_one_lead(lead: dict, campaign_prompt: str, campaign_id: str,
                      sender_info: dict, variant: str = "A") -> dict:
    """Process a single lead: generate follow-ups, create sequence, send initial."""
    name = lead.get("name", "")
    company = lead.get("company", "")
    email = lead.get("email", "")

    if not email:
        print(f"[Sender] ✗ Skipping {company} — no email")
        return lead

    # Check exclusion list
    domain = email.split("@")[-1] if "@" in email else ""
    if is_excluded(company=company, domain=domain, email=email):
        print(f"[Sender] ✗ Skipping {company} — in exclusion list")
        return lead

    # Get the initial email (A or B variant)
    draft_emails = lead.get("draft_emails", {})
    if isinstance(draft_emails, str):
        try:
            draft_emails = json.loads(draft_emails)
        except Exception:
            draft_emails = {}

    initial = draft_emails.get(variant, lead.get("draft_email", {}))
    if isinstance(initial, str):
        try:
            initial = json.loads(initial)
        except Exception:
            initial = {}

    if not initial or not initial.get("body"):
        print(f"[Sender] ✗ Skipping {company} — no draft email")
        return lead

    initial_subject = initial.get("subject", "")
    initial_body = initial.get("body", "")
    cc = initial.get("cc", "")

    print(f"[Sender] Processing {name} @ {company}…")

    # ── Step 1: Generate 3 follow-up emails ──────────────────────────────────
    print(f"[Sender] Generating follow-up sequence for {company}…")
    followups = generate_followups(lead, initial, campaign_prompt, sender_info)

    # ── Step 2: Create full sequence in DB ───────────────────────────────────
    lead_id = lead.get("id", "")
    if not lead_id:
        from memory.storage import _generate_id
        lead_id = _generate_id(name, company)

    seq_ids = create_full_sequence(
        lead_id=lead_id,
        campaign_id=campaign_id,
        variant=variant,
        initial_subject=initial_subject,
        initial_body=initial_body,
        followup_emails=followups,
        cc=cc,
    )

    # ── Step 3: Send the initial email (step 0) ─────────────────────────────
    print(f"[Sender] Sending initial email to {email}…")
    result = send_email(sender_info, email, initial_subject, initial_body, cc)

    if result["success"]:
        update_sequence_status(seq_ids[0], "sent", message_id=result["message_id"])
        log_campaign_event(
            campaign_id, "Sender", "email_sent",
            f"Initial email sent to {name} @ {company}",
            {"lead_id": lead_id, "email": email, "variant": variant, "step": 0},
        )
        print(f"[Sender] ✓ Initial email sent to {email}")
    else:
        update_sequence_status(seq_ids[0], "failed", error_message=result["error"])
        log_campaign_event(
            campaign_id, "Sender", "email_failed",
            f"Failed to send to {email}: {result['error']}",
            {"lead_id": lead_id, "email": email, "error": result["error"]},
        )
        print(f"[Sender] ✗ Failed: {result['error']}")

    lead = dict(lead)
    lead["send_status"] = "sent" if result["success"] else "failed"
    lead["sequence_ids"] = seq_ids
    return lead


def run_sender(enriched_leads: list, campaign_prompt: str, campaign_id: str,
               variant: str = "A") -> list:
    """Agent 5: send initial emails + create follow-up sequences for all HOT/WARM leads."""
    sender_info = get_sender_config(default_only=True)
    if not sender_info:
        print("[Sender] ⚠ No sender configured. Using env variables.")
        sender_info = {
            "name": os.getenv("SENDER_NAME", "[Your Name]"),
            "email": os.getenv("SENDER_EMAIL", ""),
            "title": os.getenv("SENDER_TITLE", ""),
            "company": os.getenv("SENDER_COMPANY", ""),
            "signature": os.getenv("SENDER_SIGNATURE", ""),
            "smtp_host": os.getenv("SMTP_HOST", "smtp.gmail.com"),
            "smtp_port": int(os.getenv("SMTP_PORT", "587")),
            "smtp_user": os.getenv("SMTP_USER", ""),
            "smtp_pass": os.getenv("SMTP_PASS", ""),
        }

    if not sender_info.get("email") or not sender_info.get("smtp_user", sender_info.get("email")):
        print("[Sender] ✗ No sender email/SMTP configured. Aborting send.")
        print("[Sender] → Configure via POST /sender or set SMTP_* env variables.")
        return enriched_leads

    to_send = [
        l for l in enriched_leads
        if l.get("segment") in ("hot", "warm")
        and l.get("email")
        and (l.get("draft_email") or l.get("draft_emails"))
    ]
    rest = [l for l in enriched_leads if l not in to_send]

    if not to_send:
        print("[Sender] No leads ready to send.")
        return enriched_leads

    print(f"\n[AGENT 5] Sending {len(to_send)} emails + creating follow-up sequences…")
    log_campaign_event(
        campaign_id, "Sender", "batch_start",
        f"Starting send for {len(to_send)} leads",
    )

    result_map = {}
    # Process sequentially — SMTP servers don't like parallel floods
    for i, lead in enumerate(to_send):
        try:
            result_map[i] = _process_one_lead(
                lead, campaign_prompt, campaign_id, sender_info, variant
            )
        except Exception as e:
            print(f"[Sender] ⚠ Lead {i} failed completely: {e}")
            result_map[i] = lead

    processed = [result_map[i] for i in sorted(result_map)]

    sent_count = sum(1 for l in processed if l.get("send_status") == "sent")
    fail_count = sum(1 for l in processed if l.get("send_status") == "failed")

    log_campaign_event(
        campaign_id, "Sender", "batch_complete",
        f"Batch complete: {sent_count} sent, {fail_count} failed",
        {"sent": sent_count, "failed": fail_count, "total": len(to_send)},
    )

    print(f"\n[Agent 5] Results: {sent_count} sent, {fail_count} failed")
    print(f"[Agent 5] Follow-up sequences created: J+3, J+7, J+14 scheduled")

    return processed + rest


# ── Scheduler: process due follow-ups ─────────────────────────────────────────

def run_due_sequences() -> dict:
    """Check for due follow-ups and send them.
    Call this periodically (e.g. every hour via cron or APScheduler).
    """
    sender_info = get_sender_config(default_only=True)
    if not sender_info:
        sender_info = {
            "name": os.getenv("SENDER_NAME", ""),
            "email": os.getenv("SENDER_EMAIL", ""),
            "smtp_host": os.getenv("SMTP_HOST", "smtp.gmail.com"),
            "smtp_port": int(os.getenv("SMTP_PORT", "587")),
            "smtp_user": os.getenv("SMTP_USER", ""),
            "smtp_pass": os.getenv("SMTP_PASS", ""),
            "signature": os.getenv("SENDER_SIGNATURE", ""),
        }

    due = get_due_sequences()
    if not due:
        return {"sent": 0, "failed": 0, "skipped": 0}

    print(f"[Scheduler] Processing {len(due)} due follow-ups…")

    sent = 0
    failed = 0
    skipped = 0

    for seq in due:
        email = seq.get("email", "")
        company = seq.get("company", "")
        step = seq.get("step", 0)
        step_label = {0: "initial", 1: "J+3", 2: "J+7", 3: "J+14"}.get(step, f"step-{step}")

        if not email:
            update_sequence_status(seq["id"], "failed", error_message="No email address")
            skipped += 1
            continue

        # Check if lead already replied (cancel remaining sequence)
        lead_seq = get_lead_sequence(seq["lead_id"])
        replied = any(s.get("status") == "replied" for s in lead_seq)
        if replied:
            cancel_remaining_sequence(seq["lead_id"])
            skipped += 1
            print(f"[Scheduler] ✓ Skipped {company} {step_label} — already replied")
            continue

        # Check exclusion
        domain = email.split("@")[-1] if "@" in email else ""
        if is_excluded(company=company, domain=domain, email=email):
            update_sequence_status(seq["id"], "cancelled")
            skipped += 1
            continue

        # Send
        print(f"[Scheduler] Sending {step_label} to {email} ({company})…")
        result = send_email(
            sender_info, email,
            seq.get("subject", ""), seq.get("body", ""),
            cc=seq.get("cc"),
        )

        if result["success"]:
            update_sequence_status(seq["id"], "sent", message_id=result["message_id"])
            log_campaign_event(
                seq.get("campaign_id", ""), "Scheduler", "followup_sent",
                f"Follow-up {step_label} sent to {company}",
                {"step": step, "email": email},
            )
            sent += 1
        else:
            update_sequence_status(seq["id"], "failed", error_message=result["error"])
            failed += 1

    stats = {"sent": sent, "failed": failed, "skipped": skipped}
    print(f"[Scheduler] Done: {sent} sent, {failed} failed, {skipped} skipped")
    return stats