"""
analyst_node.py — Agent Analyst (Agent 7).

Synthesizes campaign data into:
  • key metrics (leads, deliverability, engagement)
  • A/B variant performance comparison
  • LLM-written optimization recommendations
  • a downloadable PDF report (with charts)

Used by the Analytics page and for weekly reports across all campaigns.
"""

import io
import os
import re
import json
from datetime import datetime, timedelta

from psycopg2.extras import RealDictCursor

from memory.storage import get_conn


# ──────────────────────────────────────────────────────────────────────────────
# METRICS
# ──────────────────────────────────────────────────────────────────────────────

def _pct(part: int, whole: int) -> float:
    return round(part / whole * 100, 1) if whole else 0.0


def compute_campaign_metrics(campaign_id: str) -> dict:
    """All key metrics for one campaign (leads + deliverability + engagement)."""
    with get_conn() as conn:
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # ── Leads ──
        cur.execute("""
            SELECT
                COUNT(*)                                              AS total,
                COUNT(*) FILTER (WHERE segment = 'hot')              AS hot,
                COUNT(*) FILTER (WHERE segment = 'warm')            AS warm,
                COUNT(*) FILTER (WHERE segment = 'cold')            AS cold,
                COUNT(*) FILTER (WHERE email IS NOT NULL AND email <> '') AS with_email,
                COUNT(*) FILTER (WHERE email_verified)              AS verified,
                COALESCE(ROUND(AVG(score)), 0)                      AS avg_score
            FROM leads WHERE campaign = %s
        """, (campaign_id,))
        leads = dict(cur.fetchone() or {})

        # ── Emails (sequences) ──
        # "sent" = any row that was actually emailed. A reply/open/click all
        # imply it was sent, so we count those too (and tolerate rows whose
        # sent_at was cleared by older code).
        sent_expr = ("(sent_at IS NOT NULL OR message_id IS NOT NULL "
                     "OR clicked_at IS NOT NULL OR status IN ('sent', 'replied'))")
        cur.execute(f"""
            SELECT
                COUNT(*) FILTER (WHERE {sent_expr})            AS sent,
                COUNT(*) FILTER (WHERE clicked_at IS NOT NULL) AS clicked,
                COUNT(*) FILTER (WHERE status = 'replied')     AS replied,
                COUNT(*) FILTER (WHERE status = 'failed')      AS failed,
                COALESCE(SUM(click_count), 0)                  AS total_clicks
            FROM email_sequences WHERE campaign_id = %s
        """, (campaign_id,))
        emails = dict(cur.fetchone() or {})

        # ── Notifications (bounces, unsubscribes, meetings) ──
        cur.execute("""
            SELECT type, COUNT(*) AS n
            FROM lead_notifications WHERE campaign_id = %s GROUP BY type
        """, (campaign_id,))
        notif = {r["type"]: r["n"] for r in cur.fetchall()}

        # ── Per-variant performance (A/B) ──
        cur.execute(f"""
            SELECT variant,
                COUNT(*) FILTER (WHERE {sent_expr})            AS sent,
                COUNT(*) FILTER (WHERE clicked_at IS NOT NULL) AS clicked,
                COUNT(*) FILTER (WHERE status = 'replied')     AS replied
            FROM email_sequences
            WHERE campaign_id = %s AND variant IS NOT NULL AND variant <> ''
            GROUP BY variant ORDER BY variant
        """, (campaign_id,))
        variant_rows = cur.fetchall()

    sent = emails.get("sent", 0) or 0
    bounced = notif.get("email_bounced", 0)
    unsubscribed = notif.get("unsubscribe", 0)
    meetings = notif.get("calendar_accepted", 0)

    variants = {}
    for r in variant_rows:
        v_sent = r["sent"] or 0
        variants[r["variant"]] = {
            "sent":       v_sent,
            "clicked":    r["clicked"] or 0,
            "replied":    r["replied"] or 0,
            "click_rate": _pct(r["clicked"] or 0, v_sent),
            "reply_rate": _pct(r["replied"] or 0, v_sent),
        }

    # Determine the winning variant by reply rate, then click rate
    winner = None
    if len(variants) >= 2:
        winner = max(
            variants.items(),
            key=lambda kv: (kv[1]["reply_rate"], kv[1]["click_rate"]),
        )[0]

    return {
        "leads": {
            "total":          leads.get("total", 0),
            "hot":            leads.get("hot", 0),
            "warm":           leads.get("warm", 0),
            "cold":           leads.get("cold", 0),
            "with_email":     leads.get("with_email", 0),
            "verified":       leads.get("verified", 0),
            "avg_score":      int(leads.get("avg_score", 0) or 0),
            "email_coverage": _pct(leads.get("with_email", 0), leads.get("total", 0)),
            "verified_pct":   _pct(leads.get("verified", 0), leads.get("with_email", 0)),
        },
        "emails": {
            "sent":          sent,
            "clicked":       emails.get("clicked", 0) or 0,
            "total_clicks":  emails.get("total_clicks", 0) or 0,
            "replied":       emails.get("replied", 0) or 0,
            "failed":        emails.get("failed", 0) or 0,
            "bounced":       bounced,
            "unsubscribed":  unsubscribed,
            "meetings":      meetings,
            "click_rate":    _pct(emails.get("clicked", 0) or 0, sent),
            "reply_rate":    _pct(emails.get("replied", 0) or 0, sent),
            "bounce_rate":   _pct(bounced, sent),
        },
        "variants":     variants,
        "best_variant": winner,
    }


# ──────────────────────────────────────────────────────────────────────────────
# LLM RECOMMENDATIONS
# ──────────────────────────────────────────────────────────────────────────────

def generate_recommendations(campaign_prompt: str, metrics: dict) -> dict:
    """Ask the Analyst LLM for a short summary + optimization recommendations."""
    from agents.llm_factory import get_analyst_llm
    from langchain_core.messages import HumanMessage, SystemMessage

    system = (
        "You are a B2B outbound performance analyst. Given campaign metrics, "
        "write a concise executive summary and concrete, actionable optimization "
        "recommendations. Be specific and data-driven. No fluff."
    )
    prompt = f"""Campaign goal: "{campaign_prompt}"

Metrics (JSON):
{json.dumps(metrics, ensure_ascii=False, indent=2)}

Analyze deliverability (bounce/verified rate), engagement (click/reply rates),
lead quality (segment split, avg score), and the A/B variant comparison.

Return ONLY raw JSON (no markdown fences):
{{
  "summary": "2-3 sentence executive summary of how the campaign is performing",
  "recommendations": [
    "specific actionable recommendation 1",
    "specific actionable recommendation 2",
    "..."
  ]
}}"""

    try:
        resp = get_analyst_llm().invoke([
            SystemMessage(content=system),
            HumanMessage(content=prompt),
        ])
        content = resp.content
        if isinstance(content, list):
            content = "\n".join(
                b["text"] for b in content
                if isinstance(b, dict) and b.get("type") == "text"
            )
        content = re.sub(r"```json|```", "", content or "").strip()
        try:
            data = json.loads(content)
        except Exception:
            m = re.search(r"\{.*\}", content, re.DOTALL)
            data = json.loads(m.group(0)) if m else {}
        summary = data.get("summary", "")
        recs = data.get("recommendations", [])
        if isinstance(recs, str):
            recs = [recs]
        return {"summary": summary, "recommendations": [str(r) for r in recs if r]}
    except Exception as e:
        print(f"[Analyst] Recommendation generation failed: {e}")
        return {"summary": "", "recommendations": _fallback_recommendations(metrics)}


def _fallback_recommendations(metrics: dict) -> list:
    """Deterministic recommendations when the LLM is unavailable."""
    recs = []
    e = metrics.get("emails", {})
    l = metrics.get("leads", {})
    if e.get("bounce_rate", 0) > 5:
        recs.append("High bounce rate — verify emails (SMTP/API) before sending to protect deliverability.")
    if l.get("verified_pct", 0) < 50 and l.get("with_email", 0):
        recs.append("Less than half of emails are verified — rely more on Hunter/FindThatLead/Apollo and re-enrich cold leads.")
    if e.get("click_rate", 0) < 5 and e.get("sent", 0):
        recs.append("Low click rate — make the call-to-action clearer and add a single relevant link.")
    if e.get("reply_rate", 0) < 5 and e.get("sent", 0):
        recs.append("Low reply rate — personalize the opener with a concrete insight about the lead.")
    if metrics.get("best_variant"):
        recs.append(f"Variant {metrics['best_variant']} performs best — shift more volume to it.")
    if l.get("cold", 0) > l.get("hot", 0) + l.get("warm", 0):
        recs.append("Most leads are cold (no reliable email) — improve targeting or email discovery.")
    return recs or ["Not enough data yet — send more emails to generate actionable insights."]


# ──────────────────────────────────────────────────────────────────────────────
# REPORT BUILDERS
# ──────────────────────────────────────────────────────────────────────────────

def _campaign_row(campaign_id: str) -> dict:
    with get_conn() as conn:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT id, prompt, created_at FROM campaigns WHERE id = %s", (campaign_id,))
        row = cur.fetchone()
    if not row:
        return {"id": campaign_id, "prompt": "(unknown campaign)", "created_at": None}
    d = dict(row)
    if d.get("created_at") and hasattr(d["created_at"], "isoformat"):
        d["created_at"] = d["created_at"].isoformat()
    return d


def build_campaign_report(campaign_id: str, with_recommendations: bool = True) -> dict:
    """Full analyst report (metrics + variant + recommendations) for one campaign."""
    campaign = _campaign_row(campaign_id)
    metrics = compute_campaign_metrics(campaign_id)
    recs = (generate_recommendations(campaign.get("prompt", ""), metrics)
            if with_recommendations else {"summary": "", "recommendations": []})
    return {
        "campaign":        campaign,
        "generated_at":    datetime.now().isoformat(),
        **metrics,
        "summary":         recs.get("summary", ""),
        "recommendations": recs.get("recommendations", []),
    }


def build_weekly_report(with_recommendations: bool = True, user_id=None) -> dict:
    """Aggregate report across the user's campaigns active in the last 7 days."""
    since = datetime.now() - timedelta(days=7)
    with get_conn() as conn:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        if user_id is not None:
            cur.execute("SELECT id, prompt, created_at FROM campaigns WHERE user_id = %s "
                        "ORDER BY created_at DESC", (user_id,))
        else:
            cur.execute("SELECT id, prompt, created_at FROM campaigns ORDER BY created_at DESC")
        campaigns = [dict(r) for r in cur.fetchall()]

    per_campaign = []
    totals = {"leads": 0, "sent": 0, "clicked": 0,
              "replied": 0, "bounced": 0, "meetings": 0, "hot": 0, "warm": 0, "cold": 0}

    for camp in campaigns:
        m = compute_campaign_metrics(camp["id"])
        # Skip campaigns with no leads at all
        if not m["leads"]["total"]:
            continue
        per_campaign.append({
            "id":      camp["id"],
            "prompt":  camp["prompt"],
            "metrics": m,
        })
        totals["leads"]   += m["leads"]["total"]
        totals["hot"]     += m["leads"]["hot"]
        totals["warm"]    += m["leads"]["warm"]
        totals["cold"]    += m["leads"]["cold"]
        totals["sent"]    += m["emails"]["sent"]
        totals["clicked"] += m["emails"]["clicked"]
        totals["replied"] += m["emails"]["replied"]
        totals["bounced"] += m["emails"]["bounced"]
        totals["meetings"]+= m["emails"]["meetings"]

    totals["click_rate"] = _pct(totals["clicked"], totals["sent"])
    totals["reply_rate"] = _pct(totals["replied"], totals["sent"])
    totals["bounce_rate"] = _pct(totals["bounced"], totals["sent"])

    recs = {"summary": "", "recommendations": []}
    if with_recommendations and per_campaign:
        recs = generate_recommendations(
            "Weekly performance across all active campaigns",
            {"totals": totals, "campaigns": [
                {"prompt": c["prompt"], **c["metrics"]} for c in per_campaign[:8]
            ]},
        )

    return {
        "generated_at":    datetime.now().isoformat(),
        "period_start":    since.isoformat(),
        "period_end":      datetime.now().isoformat(),
        "totals":          totals,
        "campaigns":       per_campaign,
        "summary":         recs.get("summary", ""),
        "recommendations": recs.get("recommendations", []),
    }
