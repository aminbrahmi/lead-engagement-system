"""
monitor_node.py — Agent 7: Classification automatique des réponses + actions.

Rôle dans le pipeline :
  Tracker (Agent 6) → détecte les réponses IMAP, les sauvegarde dans messages
  Monitor (Agent 7) → lit les messages non classifiés, les analyse avec LLM,
                      exécute les actions automatiques, enrichit les notifications.

Catégories :
  interested | info_request | not_interested | angry | ooo | bounce

Actions automatiques par catégorie : voir _ACTIONS_MAP
"""

import json
import os
import re
from datetime import datetime

from langchain_core.messages import HumanMessage, SystemMessage

from agents.llm_factory import get_writer_llm


# ── System prompt ─────────────────────────────────────────────────────────────

_MONITOR_SYSTEM = """Tu es un expert en classification d'emails pour un système de prospection B2B.

Analyse chaque réponse email et classe-la dans une catégorie précise, puis détermine les actions automatiques à exécuter.

## CATÉGORIES

### INTERESTED
Indicateurs: "yes", "interested", "let's talk", "schedule", "demo", "call", "meeting", "learn more",
ton positif, questions produit/service, demande de prochaines étapes.
Exemples: "Yes, can we schedule a call?", "I'd like to learn more.", "This could be a good fit."

### INFO_REQUEST
Indicateurs: questions pricing/features/intégrations/case studies, pas d'engagement clair (ni oui ni non),
demande de documentation, comparaison avec concurrents.
Exemples: "What's your pricing?", "Do you integrate with Salesforce?", "Send me a case study."

### NOT_INTERESTED
Indicateurs: "not interested", "not a fit", "happy with current solution",
"please remove", "unsubscribe", ton neutre/légèrement négatif.
Exemples: "Not interested, thanks.", "We're happy with our provider.", "This isn't a fit."

### ANGRY
Indicateurs: CAPS LOCK, points d'exclamation multiples, "spam", "harassment", "stop",
"inappropriate", menaces légales, ton très négatif.
Exemples: "STOP SPAMMING ME!!!", "How did you get my email? This is harassment."

### OOO
Auto-reply, message d'absence, out of office, vacation responder.

### BOUNCE
Delivery failure, mailer-daemon, email not found, permanent error.

## RÈGLES
1. Confidence > 0.90 = clair | 0.70-0.90 = probable | < 0.70 = review humaine
2. Entre INFO_REQUEST et INTERESTED : demande de call/meeting → INTERESTED, sinon → INFO_REQUEST
3. OOO et BOUNCE ne sont jamais ANGRY ni INTERESTED

## FORMAT DE RÉPONSE — JSON uniquement, sans fences, sans texte autour

{
  "category": "interested|info_request|not_interested|angry|ooo|bounce",
  "confidence": 0.95,
  "reason": "Explication courte (1-2 phrases)",
  "sentiment": "positive|neutral|negative|very_negative",
  "urgency": "high|medium|low",
  "automatic_actions": ["cancel_all_followups", "update_segment_hot", ...],
  "manual_actions": ["Répondre dans l'heure", "Proposer 2-3 créneaux"],
  "suggested_response": "Template de réponse suggéré"
}"""

# ── Actions par catégorie ─────────────────────────────────────────────────────

_ACTIONS_MAP = {
    "interested": [
        "cancel_all_followups",
        "update_status_replied_interested",
        "update_segment_hot",
        "add_score_50",
        "alert_sales_team",
        "set_priority_p1",
        "add_badge_hot",
    ],
    "info_request": [
        "cancel_immediate_followup",
        "keep_longterm_followups",
        "update_status_replied_info_request",
        "update_segment_warm",
        "add_score_20",
        "flag_needs_info",
    ],
    "not_interested": [
        "cancel_all_followups_immediately",
        "update_status_replied_not_interested",
        "update_segment_cold",
        "subtract_score_10",
        "flag_do_not_contact_6months",
        "archive_lead",
    ],
    "angry": [
        "cancel_all_followups_immediately",
        "update_status_replied_angry",
        "add_to_exclusion_list_permanent",
        "alert_compliance_team",
        "flag_human_review_urgent",
        "check_gdpr_compliance",
    ],
    "ooo": [
        "keep_all_followups",
        "update_status_replied_ooo",
    ],
    "bounce": [
        "cancel_all_followups_immediately",
        "update_status_replied_bounce",
        "flag_invalid_email",
    ],
}

# Mapping catégorie → type de notification
_NOTIF_TYPE_MAP = {
    "interested":    "reply_interested",
    "info_request":  "reply_info_request",
    "not_interested":"reply_declined",
    "angry":         "reply_angry",
    "ooo":           "reply_ooo",
    "bounce":        "email_bounced",
}


# ── LLM classification ────────────────────────────────────────────────────────

def classify_email(body: str, subject: str = "", from_email: str = "") -> dict:
    """Classify a reply using the monitor LLM. Returns full classification dict."""
    fallback = {
        "category": "info_request",
        "confidence": 0.0,
        "reason": "Classification error",
        "sentiment": "neutral",
        "urgency": "low",
        "automatic_actions": _ACTIONS_MAP["info_request"],
        "manual_actions": [],
        "suggested_response": "",
    }

    try:
        llm = get_writer_llm()

        prompt = f"""**De:** {from_email}
**Sujet:** {subject or "(no subject)"}
**Corps:**
{body[:2000]}

Analyse cet email et retourne la classification JSON."""

        response = llm.invoke([
            SystemMessage(content=_MONITOR_SYSTEM),
            HumanMessage(content=prompt),
        ])

        content = re.sub(r"```json|```", "", response.content or "").strip()

        try:
            result = json.loads(content)
        except Exception:
            m = re.search(r"\{.*\}", content, re.DOTALL)
            result = json.loads(m.group(0)) if m else {}

        # Fallback actions if LLM skipped them
        cat = result.get("category", "info_request")
        result.setdefault("automatic_actions", _ACTIONS_MAP.get(cat, []))
        result.setdefault("manual_actions", [])
        result.setdefault("suggested_response", "")
        result.setdefault("confidence", 0.5)
        result.setdefault("reason", "")
        result.setdefault("sentiment", "neutral")
        result.setdefault("urgency", "medium")
        return result

    except Exception as e:
        print(f"[Monitor] Classification error: {e}")
        fallback["reason"] = str(e)
        return fallback


# ── Execute automatic actions ─────────────────────────────────────────────────

def _execute_actions(actions: list, lead_id: str, campaign_id: str,
                     lead_name: str, company: str, category: str,
                     classification: dict):
    """Execute all automatic_actions returned by the classifier."""
    from memory.storage import (
        get_conn, cancel_remaining_sequence, add_exclusion, log_campaign_event,
    )

    for action in actions:
        try:
            # ── Sequence / followup control ───────────────────────────────────
            if action in ("cancel_all_followups", "cancel_all_followups_immediately"):
                cancel_remaining_sequence(lead_id)

            elif action == "cancel_immediate_followup":
                with get_conn() as conn:
                    conn.cursor().execute("""
                        UPDATE email_sequences SET status = 'cancelled'
                        WHERE lead_id = %s AND status = 'scheduled'
                          AND step = (
                            SELECT MIN(step) FROM email_sequences
                            WHERE lead_id = %s AND status = 'scheduled'
                          )
                    """, (lead_id, lead_id))

            elif action in ("keep_longterm_followups", "keep_all_followups"):
                pass  # intentional no-op

            # ── Lead status ───────────────────────────────────────────────────
            elif action.startswith("update_status_"):
                status = action.replace("update_status_", "")
                with get_conn() as conn:
                    conn.cursor().execute(
                        "UPDATE leads SET status=%s, updated_at=NOW() WHERE id=%s",
                        (status, lead_id)
                    )

            # ── Segment ───────────────────────────────────────────────────────
            elif action in ("update_segment_hot", "add_badge_hot"):
                with get_conn() as conn:
                    conn.cursor().execute(
                        "UPDATE leads SET segment='hot', updated_at=NOW() WHERE id=%s",
                        (lead_id,)
                    )

            elif action == "update_segment_warm":
                with get_conn() as conn:
                    conn.cursor().execute(
                        "UPDATE leads SET segment='warm', updated_at=NOW() WHERE id=%s",
                        (lead_id,)
                    )

            elif action == "update_segment_cold":
                with get_conn() as conn:
                    conn.cursor().execute(
                        "UPDATE leads SET segment='cold', updated_at=NOW() WHERE id=%s",
                        (lead_id,)
                    )

            # ── Score ─────────────────────────────────────────────────────────
            elif action.startswith("add_score_"):
                delta = int(action.replace("add_score_", ""))
                with get_conn() as conn:
                    conn.cursor().execute(
                        "UPDATE leads SET score=LEAST(100, score+%s), updated_at=NOW() WHERE id=%s",
                        (delta, lead_id)
                    )

            elif action.startswith("subtract_score_"):
                delta = int(action.replace("subtract_score_", ""))
                with get_conn() as conn:
                    conn.cursor().execute(
                        "UPDATE leads SET score=GREATEST(0, score-%s), updated_at=NOW() WHERE id=%s",
                        (delta, lead_id)
                    )

            # ── Exclusion / archiving ─────────────────────────────────────────
            elif action == "add_to_exclusion_list_permanent":
                with get_conn() as conn:
                    c = conn.cursor()
                    c.execute("SELECT email FROM leads WHERE id=%s", (lead_id,))
                    row = c.fetchone()
                    if row and row[0]:
                        add_exclusion(row[0], "email", "Angry reply — permanent exclusion")
                    if company:
                        add_exclusion(company, "company", "Angry reply — permanent exclusion")

            elif action == "flag_do_not_contact_6months":
                with get_conn() as conn:
                    conn.cursor().execute(
                        "UPDATE leads SET status='do_not_contact', updated_at=NOW() WHERE id=%s",
                        (lead_id,)
                    )

            elif action == "archive_lead":
                with get_conn() as conn:
                    conn.cursor().execute(
                        "UPDATE leads SET status='archived', updated_at=NOW() WHERE id=%s",
                        (lead_id,)
                    )

            elif action == "flag_invalid_email":
                with get_conn() as conn:
                    conn.cursor().execute(
                        "UPDATE leads SET email_verified=FALSE, updated_at=NOW() WHERE id=%s",
                        (lead_id,)
                    )

            # ── Flags (stored as lead metadata / log) ─────────────────────────
            elif action in ("set_priority_p1", "flag_needs_info",
                            "flag_human_review_urgent", "check_gdpr_compliance"):
                log_campaign_event(
                    campaign_id, "Monitor", action,
                    f"{action} for {lead_name} @ {company}",
                    {"lead_id": lead_id, "category": category},
                )

            print(f"[Monitor] ✓ {action} → {company}")

        except Exception as e:
            print(f"[Monitor] ✗ Action '{action}' failed for {company}: {e}")


# ── Notification with full metadata ──────────────────────────────────────────

def _save_classification_notification(campaign_id: str, lead_id: str,
                                       lead_name: str, company: str,
                                       classification: dict):
    """Create / update notification with full classification metadata."""
    from memory.storage import get_conn

    category = classification.get("category", "info_request")
    notif_type = _NOTIF_TYPE_MAP.get(category, "reply_info_request")
    urgency = classification.get("urgency", "medium")
    reason = classification.get("reason", "")
    confidence = classification.get("confidence", 0)

    message = (
        f"[{urgency.upper()}] {lead_name} @ {company} → {category.upper()}"
        f" ({int(confidence * 100)}%) — {reason[:100]}"
    )

    metadata = {
        "category":           category,
        "confidence":         confidence,
        "reason":             reason,
        "sentiment":          classification.get("sentiment"),
        "urgency":            urgency,
        "manual_actions":     classification.get("manual_actions", []),
        "suggested_response": classification.get("suggested_response", ""),
        "classified_at":      datetime.now().isoformat(),
    }

    try:
        with get_conn() as conn:
            cursor = conn.cursor()
            # Upsert: update existing unread notification for this lead if present
            cursor.execute("""
                SELECT id FROM lead_notifications
                WHERE lead_id=%s AND read=FALSE
                  AND created_at > NOW() - INTERVAL '48 hours'
                  AND type LIKE 'reply_%'
                ORDER BY created_at DESC LIMIT 1
            """, (lead_id,))
            existing = cursor.fetchone()

            if existing:
                cursor.execute("""
                    UPDATE lead_notifications
                    SET type=%s, message=%s, metadata=%s
                    WHERE id=%s
                """, (notif_type, message, json.dumps(metadata), existing[0]))
            else:
                cursor.execute("""
                    INSERT INTO lead_notifications
                      (campaign_id, lead_id, type, message, metadata)
                    VALUES (%s,%s,%s,%s,%s)
                """, (campaign_id, lead_id, notif_type, message, json.dumps(metadata)))
    except Exception as e:
        print(f"[Monitor] Notification error: {e}")


# ── Main entry point ──────────────────────────────────────────────────────────

def run_monitor(campaign_id: str = None) -> dict:
    """
    Agent 7 — reads unclassified received messages, classifies them with LLM,
    executes automatic actions, updates notifications.
    """
    from memory.storage import get_conn
    from psycopg2.extras import RealDictCursor

    stats = {"processed": 0, "classified": 0, "actions_executed": 0, "errors": 0}
    print("\n[AGENT 7] Monitor — starting classification run…")

    # 1. Fetch unclassified received messages
    with get_conn() as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        if campaign_id:
            cursor.execute("""
                SELECT m.id, m.body, m.subject, m.from_email,
                       m.lead_id, m.discussion_id, m.message_id,
                       d.campaign_id,
                       l.name AS lead_name, l.company
                FROM messages m
                JOIN discussions d ON d.id = m.discussion_id
                JOIN leads l ON l.id = m.lead_id
                WHERE m.direction = 'received'
                  AND (m.sentiment IS NULL OR m.sentiment = 'info_request')
                  AND d.campaign_id = %s
                ORDER BY m.created_at DESC
            """, (campaign_id,))
        else:
            cursor.execute("""
                SELECT m.id, m.body, m.subject, m.from_email,
                       m.lead_id, m.discussion_id, m.message_id,
                       d.campaign_id,
                       l.name AS lead_name, l.company
                FROM messages m
                JOIN discussions d ON d.id = m.discussion_id
                JOIN leads l ON l.id = m.lead_id
                WHERE m.direction = 'received'
                  AND (m.sentiment IS NULL OR m.sentiment = 'info_request')
                ORDER BY m.created_at DESC
                LIMIT 50
            """)
        messages = [dict(r) for r in cursor.fetchall()]

    if not messages:
        print("[Monitor] No unclassified messages found.")
        return stats

    print(f"[Monitor] {len(messages)} message(s) to classify")

    for msg in messages:
        stats["processed"] += 1
        lead_name = msg.get("lead_name", "Unknown")
        company   = msg.get("company", "Unknown")
        lead_id   = msg.get("lead_id", "")
        camp_id   = msg.get("campaign_id", campaign_id or "")

        print(f"[Monitor] Classifying reply from {lead_name} @ {company}…")

        # 2. LLM classification
        try:
            classification = classify_email(
                body=msg.get("body", ""),
                subject=msg.get("subject", ""),
                from_email=msg.get("from_email", ""),
            )
        except Exception as e:
            print(f"[Monitor] ✗ Classification failed: {e}")
            stats["errors"] += 1
            continue

        category   = classification.get("category", "info_request")
        confidence = classification.get("confidence", 0)
        reason     = classification.get("reason", "")
        print(f"[Monitor] → {category.upper()} ({int(confidence*100)}%) — {reason[:80]}")

        # 3. Persist classification on the message row
        try:
            with get_conn() as conn:
                conn.cursor().execute("""
                    UPDATE messages
                    SET sentiment = %s
                    WHERE id = %s
                """, (category, msg["id"]))
        except Exception as e:
            print(f"[Monitor] ✗ Could not update message sentiment: {e}")

        stats["classified"] += 1

        # 4. Execute automatic actions
        actions = classification.get("automatic_actions", _ACTIONS_MAP.get(category, []))
        _execute_actions(
            actions, lead_id, camp_id, lead_name, company, category, classification
        )
        stats["actions_executed"] += len(actions)

        # 5. Create / update notification with full metadata
        _save_classification_notification(
            camp_id, lead_id, lead_name, company, classification
        )

        print(f"[Monitor] ✓ {lead_name} @ {company} — {len(actions)} actions executed")

    print(f"\n[Agent 7] Done: {stats['classified']}/{stats['processed']} classified, "
          f"{stats['actions_executed']} actions, {stats['errors']} errors")
    return stats
