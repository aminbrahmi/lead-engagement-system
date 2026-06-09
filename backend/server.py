"""
backend/server.py — FastAPI server that wraps the existing LangGraph pipeline
and exposes REST endpoints + WebSocket for live pipeline streaming.

Run:
    cd your-project-root
    uvicorn backend.server:app --reload --port 8000
"""

import asyncio
import json
import sys
import os
import io
import hashlib
from contextlib import redirect_stdout
from datetime import datetime
from typing import Optional
import threading
import time

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from utils.email_verifier import verify_email, should_auto_verify
from agents.sender_node import send_email, generate_followups
from memory.storage import update_sequence_status
from fastapi.responses import Response, RedirectResponse, HTMLResponse
import urllib.parse

# ── Add project root to path so imports work ──────────────────────────────────
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from memory.storage import (
    init_db, get_all_leads, get_campaign_leads,
    save_enrichment_results, update_lead_qualification,
    get_all_campaigns, get_campaign_by_prompt, _generate_campaign_id, get_conn,
    get_campaign_events, log_campaign_event, update_campaign_status,
    get_exclusion_list, add_exclusion, remove_exclusion, remove_exclusion_by_value,
    get_sender_config, save_sender_config, update_sender_config,
    find_similar_campaign, save_campaign_criteria, delete_lead_completely,
)
from orchestration.graph import build_pipeline, LeadPipelineState
from utils.json_utils import extract_json_list

# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(title="LeadFlow API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()

# Base URL used in customer-facing links (unsubscribe / resubscribe).
# Must match the host the recipient can reach — same value the sender uses.
BASE_URL = os.getenv("REACT_APP_API_URL", "http://localhost:8000")

# ── In-memory campaign store ─────────────────────────────────────────────────

_campaigns: dict[str, dict] = {}
_campaign_results: dict[str, dict] = {}


# ── Models ────────────────────────────────────────────────────────────────────



class CampaignRequest(BaseModel):
    prompt: str

class EmailUpdate(BaseModel):
    subject: Optional[str] = None
    body: Optional[str] = None
    variant: Optional[str] = None
    cc: Optional[str] = None

class LeadStatusUpdate(BaseModel):
    status: str

class ScheduleMeetRequest(BaseModel):
    date:         str
    time:         str
    duration:     Optional[int] = 30
    notes:        Optional[str] = None
    to_email:     Optional[str] = None
    extra_emails: Optional[list] = None

class DiscussionReplyRequest(BaseModel):
    subject: str
    body: str
    cc: Optional[str] = None

class LeadFieldsUpdate(BaseModel):
    email: Optional[str] = None
    email_source: Optional[str] = None
    email_verified: Optional[bool] = None
    location: Optional[str] = None
    insights: Optional[dict] = None
    segment: Optional[str] = None
    status: Optional[str] = None
    score: Optional[int] = None

class ExclusionCreate(BaseModel):
    value: str
    type: str       # company | domain | email
    reason: Optional[str] = None

class SenderCreate(BaseModel):
    name: str
    email: str
    title: Optional[str] = ""
    company: Optional[str] = ""
    company_description: Optional[str] = ""  # what the company does
    company_location: Optional[str] = ""     # HQ location
    company_size: Optional[str] = ""         # e.g. "50-200 employees"
    company_url: Optional[str] = ""          # tracked link in emails
    signature: Optional[str] = ""
    is_default: Optional[bool] = True


# ── REST Endpoints ────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/campaigns")
async def create_campaign(req: CampaignRequest):
    """Create a new campaign or return existing one if same prompt."""
    existing = get_campaign_by_prompt(req.prompt)

    if existing:
        campaign_id = existing["id"]
        _campaigns[campaign_id] = {
            "id": campaign_id,
            "prompt": req.prompt,
            "status": "existing",
            "created_at": str(existing.get("created_at", "")),
        }
        return {
            "campaign_id": campaign_id,
            "status": "existing",
            "existing": True,
            "leads_count": existing.get("leads_count", 0),
        }

    campaign_id = _generate_campaign_id(req.prompt)
    _campaigns[campaign_id] = {
        "id": campaign_id,
        "prompt": req.prompt,
        "status": "pending",
        "created_at": datetime.now().isoformat(),
    }

    return {"campaign_id": campaign_id, "status": "pending", "existing": False}


@app.get("/campaigns")
def list_campaigns():
    """Return all campaigns from DB with lead counts."""
    campaigns = get_all_campaigns()

    # Parse datetime fields for JSON serialization
    for c in campaigns:
        for field in ["created_at", "updated_at"]:
            if c.get(field) and hasattr(c[field], "isoformat"):
                c[field] = c[field].isoformat()

    return {"campaigns": campaigns}


@app.get("/campaigns/{campaign_id}")
def get_campaign(campaign_id: str):
    """Return campaign detail + its leads."""
    # Try DB first
    campaigns = get_all_campaigns()
    campaign = next((c for c in campaigns if c["id"] == campaign_id), None)

    if not campaign:
        # Fallback to in-memory (pipeline still running)
        if campaign_id in _campaigns:
            return _campaigns[campaign_id]
        raise HTTPException(404, "Campaign not found")

    for field in ["created_at", "updated_at"]:
        if campaign.get(field) and hasattr(campaign[field], "isoformat"):
            campaign[field] = campaign[field].isoformat()

    return campaign


@app.get("/campaigns/{campaign_id}/leads")
def get_campaign_leads_endpoint(campaign_id: str):
    """Return all leads for a specific campaign."""
    leads = get_campaign_leads(campaign_id)

    for lead in leads:
        for field in ["insights", "draft_email"]:
            if isinstance(lead.get(field), str):
                try:
                    lead[field] = json.loads(lead[field])
                except Exception:
                    pass
        for field in ["created_at", "updated_at"]:
            if lead.get(field) and hasattr(lead[field], "isoformat"):
                lead[field] = lead[field].isoformat()

    return {"leads": leads, "count": len(leads)}


@app.get("/leads")
def list_leads(campaign_id: Optional[str] = None):
    if campaign_id:
        leads = get_campaign_leads(campaign_id)
    else:
        leads = get_all_leads()

    # Parse JSON fields + serialize datetimes
    for lead in leads:
        for field in ["insights", "draft_email"]:
            if isinstance(lead.get(field), str):
                try:
                    lead[field] = json.loads(lead[field])
                except Exception:
                    pass
        for field in ["created_at", "updated_at"]:
            if lead.get(field) and hasattr(lead[field], "isoformat"):
                lead[field] = lead[field].isoformat()
    return {"leads": leads}


@app.get("/leads/{lead_id}")
def get_lead(lead_id: str):
    all_leads = get_all_leads()
    for lead in all_leads:
        if lead.get("id") == lead_id:
            for field in ["insights", "draft_email"]:
                if isinstance(lead.get(field), str):
                    try:
                        lead[field] = json.loads(lead[field])
                    except Exception:
                        pass
            return lead
    raise HTTPException(404, "Lead not found")


@app.delete("/leads/{lead_id}")
def delete_lead(lead_id: str):
    """RGPD Art. 17 — erase all personal data for this lead across every store."""
    result = delete_lead_completely(lead_id)
    return {"status": "deleted", "erased": result}


@app.patch("/leads/{lead_id}")
def update_lead_status(lead_id: str, update: LeadStatusUpdate):
    from memory.storage import get_conn

    with get_conn() as conn:
        conn.cursor().execute(
            "UPDATE leads SET status = %s, updated_at = %s WHERE id = %s",
            (update.status, datetime.now().isoformat(), lead_id),
        )

    return {"status": "updated"}


@app.patch("/leads/{lead_id}/fields")
def update_lead_fields(lead_id: str, update: LeadFieldsUpdate):
    """Update any combination of lead fields (email, location, insights, segment…)."""
    with get_conn() as conn:
        cursor = conn.cursor()
        sets, vals = [], []

        if update.email is not None:
            sets.append("email = %s"); vals.append(update.email)
        if update.email_source is not None:
            sets.append("email_source = %s"); vals.append(update.email_source)
        if update.email_verified is not None:
            sets.append("email_verified = %s"); vals.append(update.email_verified)
        if update.location is not None:
            sets.append("location = %s"); vals.append(update.location)
        if update.insights is not None:
            sets.append("insights = %s"); vals.append(json.dumps(update.insights))
        if update.segment is not None:
            sets.append("segment = %s"); vals.append(update.segment)
        if update.status is not None:
            sets.append("status = %s"); vals.append(update.status)
        if update.score is not None:
            sets.append("score = %s"); vals.append(update.score)

        if not sets:
            return {"status": "nothing to update"}

        sets.append("updated_at = NOW()")
        vals.append(lead_id)
        cursor.execute(f"UPDATE leads SET {', '.join(sets)} WHERE id = %s", vals)

    return {"status": "updated"}


# ── Campaign events / timeline ────────────────────────────────────────────────

@app.get("/campaigns/{campaign_id}/events")
def get_events(campaign_id: str):
    events = get_campaign_events(campaign_id)
    return {"events": events}


# ── Exclusion list ────────────────────────────────────────────────────────────

@app.get("/exclusions")
def list_exclusions():
    return {"exclusions": get_exclusion_list()}

@app.post("/exclusions")
def create_exclusion(exc: ExclusionCreate):
    add_exclusion(exc.value, exc.type, exc.reason)
    return {"status": "added"}

@app.delete("/exclusions/{exclusion_id}")
def delete_exclusion(exclusion_id: int):
    remove_exclusion(exclusion_id)
    return {"status": "removed"}


# ── Sender config ─────────────────────────────────────────────────────────────

@app.get("/sender")
def get_sender():
    config = get_sender_config(default_only=True)
    return config or {"name": "", "email": "", "title": "", "company": "", "signature": ""}

@app.post("/sender")
def create_sender(sender: SenderCreate):
    save_sender_config(
        name=sender.name, email=sender.email, title=sender.title,
        company=sender.company, signature=sender.signature,
        is_default=sender.is_default,
        company_description=sender.company_description,
        company_location=sender.company_location,
        company_size=sender.company_size,
        company_url=sender.company_url,
    )
    return {"status": "saved"}


# ── Lead A/B emails ───────────────────────────────────────────────────────────

@app.get("/leads/{lead_id}/emails")
def get_lead_emails(lead_id: str):
    """Get A/B email variants for a lead."""
    all_leads = get_all_leads()
    for lead in all_leads:
        if lead.get("id") == lead_id:
            result = {"lead_id": lead_id, "emails": {}}
            # Parse draft_emails (A/B variants)
            if lead.get("draft_emails"):
                raw = lead["draft_emails"]
                if isinstance(raw, str):
                    try:
                        result["emails"] = json.loads(raw)
                    except Exception:
                        pass
                else:
                    result["emails"] = raw
            # Fallback to single draft_email as variant A
            elif lead.get("draft_email"):
                raw = lead["draft_email"]
                if isinstance(raw, str):
                    try:
                        raw = json.loads(raw)
                    except Exception:
                        pass
                result["emails"] = {"A": raw}
            return result
    raise HTTPException(404, "Lead not found")


@app.patch("/leads/{lead_id}/emails/{variant}")
def update_lead_email_variant(lead_id: str, variant: str, update: EmailUpdate):
    """Update a specific A/B variant email."""
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT draft_emails, draft_email FROM leads WHERE id = %s", (lead_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(404, "Lead not found")

        # Parse existing variants
        emails = {}
        if row[0]:
            try:
                emails = json.loads(row[0]) if isinstance(row[0], str) else row[0]
            except Exception:
                emails = {}

        # Get or init the variant
        v = emails.get(variant, {})
        if update.subject is not None:
            v["subject"] = update.subject
        if update.body is not None:
            v["body"] = update.body
        if update.cc is not None:
            v["cc"] = update.cc
        emails[variant] = v

        # Save back
        cursor.execute(
            "UPDATE leads SET draft_emails = %s, updated_at = %s WHERE id = %s",
            (json.dumps(emails), datetime.now().isoformat(), lead_id),
        )

        # Also update draft_email if variant A
        if variant == "A":
            cursor.execute(
                "UPDATE leads SET draft_email = %s WHERE id = %s",
                (json.dumps(v), lead_id),
            )

    return {"status": "updated", "variant": variant, "email": v}


# ── Export ────────────────────────────────────────────────────────────────────

@app.get("/campaigns/{campaign_id}/export")
def export_campaign_csv(campaign_id: str):
    """Export campaign leads as CSV."""
    import csv
    import io

    leads = get_campaign_leads(campaign_id)
    if not leads:
        raise HTTPException(404, "No leads found")

    output = io.StringIO()
    fields = ["name", "company", "role", "email", "email_source", "email_verified",
              "score", "segment", "location", "source_url", "status"]
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for lead in leads:
        writer.writerow(lead)

    from fastapi.responses import StreamingResponse
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=campaign_{campaign_id}_leads.csv"},
    )


# ── WebSocket — live pipeline streaming ───────────────────────────────────────

def _detect_stage(line: str) -> Optional[str]:
    """Parse print output to detect which pipeline stage is active."""
    line_lower = line.lower()
    if "parsing campaign" in line_lower:
        return "parse"
    if "agent 1" in line_lower or "lead collection" in line_lower or "[collector]" in line_lower:
        return "collect"
    if "agent 2" in line_lower or "qualification" in line_lower or "[qualifier]" in line_lower:
        return "qualify"
    if "agent 3" in line_lower or "enrichment" in line_lower or "[enricher]" in line_lower:
        return "enrich"
    if "agent 4" in line_lower or "email" in line_lower.replace("email_", "") or "[emailgen]" in line_lower:
        return "emails"
    return None


def _detect_level(line: str) -> str:
    if "✓" in line or "success" in line.lower() or "done" in line.lower():
        return "success"
    if "⚠" in line or "warning" in line.lower() or "fallback" in line.lower():
        return "warn"
    if "❌" in line or "error" in line.lower() or "failed" in line.lower():
        return "error"
    return "info"


def _detect_agent(line: str) -> Optional[str]:
    for tag in ["[Parser]", "[Collector]", "[Qualifier]", "[Enricher]", "[EmailGen]", "[Storage]", "[EmailFinder]", "[NameEnricher]"]:
        if tag in line:
            return tag.strip("[]")
    return None


@app.websocket("/ws/pipeline/{campaign_id}")
async def pipeline_ws(websocket: WebSocket, campaign_id: str):
    await websocket.accept()

    if campaign_id not in _campaigns:
        await websocket.send_json({"type": "error", "data": {"message": "Campaign not found"}})
        await websocket.close()
        return

    campaign = _campaigns[campaign_id]
    prompt = campaign["prompt"]
    campaign["status"] = "running"

    async def send(msg_type: str, data: dict):
        try:
            await websocket.send_json({"type": msg_type, "data": data})
        except Exception:
            pass

    # Run pipeline in thread, capture stdout for live streaming
    def run_pipeline():
        pipeline = build_pipeline()
        result = pipeline.invoke({"campaign_prompt": prompt})
        return result

    # We run the pipeline in a thread and stream stdout lines via WS
    loop = asyncio.get_event_loop()

    # Capture stdout using a custom stream
    class WSStream(io.TextIOBase):
        def __init__(self):
            self.buffer_lines = []

        def write(self, text):
            if text.strip():
                self.buffer_lines.append(text.strip())
            return len(text)

    ws_stream = WSStream()
    old_stdout = sys.stdout

    try:
        # Run pipeline with captured output
        sys.stdout = ws_stream
        result = await loop.run_in_executor(None, run_pipeline)
        sys.stdout = old_stdout

        # Stream all captured log lines to the client
        current_stage = "parse"
        for line in ws_stream.buffer_lines:
            stage = _detect_stage(line)
            if stage and stage != current_stage:
                current_stage = stage
                await send("stage", {"stage": stage})

            await send("log", {
                "msg": line,
                "level": _detect_level(line),
                "agent": _detect_agent(line),
            })
            await asyncio.sleep(0.05)  # Small delay for streaming effect

        # Extract final leads
        enriched = result.get("enriched_leads", [])
        qualified = result.get("qualified_leads", [])
        leads = enriched if enriched else qualified

        if leads:
            await send("leads", {"leads": leads})

        # Store result
        _campaign_results[campaign_id] = {
            "leads_count": len(leads),
            "skipped_agents": result.get("skipped_agents", []),
        }
        campaign["status"] = "complete"

        await send("complete", {"campaign_id": campaign_id, "leads_count": len(leads)})

    except WebSocketDisconnect:
        sys.stdout = old_stdout
    except Exception as e:
        sys.stdout = old_stdout
        campaign["status"] = "error"
        await send("error", {"message": str(e)})
    finally:
        sys.stdout = old_stdout
        try:
            await websocket.close()
        except Exception:
            pass

class EmailVerifyRequest(BaseModel):
    email: str
    email_source: Optional[str] = None

class EmailSendRequest(BaseModel):
    variant: Optional[str] = "A"
    send_followups: Optional[bool] = True
    to_email: Optional[str] = None
    subject: Optional[str] = None   
    body: Optional[str] = None      
    cc: Optional[str] = None

class DraftEmailUpdate(BaseModel):
    subject: str
    body: str
    variant: str
    cc: Optional[str] = None

class EmailAddressUpdate(BaseModel):
    email: str


# ── Email Routes ──────────────────────────────────────────────────────────────

@app.post("/leads/{lead_id}/verify-email")
async def verify_lead_email(lead_id: str, req: EmailVerifyRequest):
    """
    Verify a lead's email address.
    - Auto-verifies if from trusted source (Hunter, FTL, Apollo)
    - SMTP-verifies for other sources (pattern, web scraping, etc.)
    """
    if not req.email:
        raise HTTPException(status_code=400, detail="No email provided")
    
    # Check if should auto-verify
    if should_auto_verify(req.email_source):
        verified = True
        message = f"Auto-verified (trusted source: {req.email_source})"
        method = "auto"
    else:
        # SMTP verification
        verified, message = verify_email(req.email, req.email_source)
        method = "smtp"
    
    # Update in database
    from memory.storage import update_email_verification
    update_email_verification(lead_id, verified)
    
    return {
        "lead_id": lead_id,
        "email": req.email,
        "verified": verified,
        "method": method,
        "message": message,
    }


@app.post("/leads/{lead_id}/send-email")
async def send_lead_email(lead_id: str, req: EmailSendRequest):
    """
    Send email to a lead.
    - Sends the selected variant (A or B)
    - Optionally creates follow-up sequence (J+3, J+7, J+14)
    - Requires email to be verified first
    """
    # Get lead from database
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, name, company, email, email_verified, email_source,
                   draft_emails, campaign, insights
            FROM leads
            WHERE id = %s
        """, (lead_id,))
        row = cursor.fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="Lead not found")
        
        lead = {
            "id": row[0],
            "name": row[1],
            "company": row[2],
            "email": row[3],
            "email_verified": row[4],
            "email_source": row[5],
            "draft_emails": json.loads(row[6]) if row[6] else {},
            "campaign": row[7],
            "insights": json.loads(row[8]) if row[8] else {},
        }
        # Override email if to_email provided (for testing)
        if req.to_email:
            lead["email"] = req.to_email
            lead["email_verified"] = True  # Trust manual override
    
    # Verify email exists
    if not lead["email"]:
        raise HTTPException(status_code=400, detail="Lead has no email")
    
    # Auto-verify if from trusted source
    if not lead["email_verified"] and should_auto_verify(lead["email_source"]):
        from memory.storage import update_email_verification
        update_email_verification(lead_id, True)
        lead["email_verified"] = True
    
    # Check if verified
    if not lead["email_verified"]:
        raise HTTPException(
            status_code=400,
            detail="Email not verified. Please verify email before sending."
        )
    
    # Get draft email for selected variant
    draft_emails = lead.get("draft_emails", {})
    if not draft_emails:
        raise HTTPException(status_code=400, detail="No draft email available")
    
    selected_email = draft_emails.get(req.variant)
    if not selected_email:
        # Fallback to any available variant
        selected_email = draft_emails.get("A") or draft_emails.get("B") or list(draft_emails.values())[0]
    
    # Get sender config
    sender_config = get_sender_config(default_only=True)
    if not sender_config:
        raise HTTPException(
            status_code=500,
            detail="No sender configuration found. Please configure sender in Settings."
        )
    
    # ── USE EDITED CONTENT FROM FRONTEND — not DB version ──
    final_subject = req.subject if req.subject else selected_email.get("subject", "")
    final_body = req.body if req.body else selected_email.get("body", "")
    final_cc = req.cc if req.cc else selected_email.get("cc")

    # ── BUILD SENDER SIGNATURE + COMPANY LINK ──
    sender_name = sender_config.get("name", "")
    sender_title = sender_config.get("title", "")
    sender_company = sender_config.get("company", "")
    sender_desc = sender_config.get("company_description", "")
    company_url = sender_config.get("company_url", "")

    body_lower = final_body.lower()
    if sender_name and sender_name.lower() not in body_lower[-300:]:
        sig_lines = ["\nBest regards,"]
        if sender_title and sender_company:
            sig_lines += [sender_name, f"{sender_title}, {sender_company}"]
        elif sender_company:
            sig_lines.append(f"{sender_name}, {sender_company}")
        else:
            sig_lines.append(sender_name)
        if sender_desc:
            sig_lines.append(sender_desc)
        if company_url:
            sig_lines.append(company_url)
        final_body = final_body.rstrip() + "\n" + "\n".join(sig_lines)
    elif company_url and company_url not in final_body:
        final_body = final_body.rstrip() + f"\n\n{company_url}"

    # ── CREATE SEQUENCE FIRST so we have sequence_id for link tracking ──
    from memory.storage import create_full_sequence
    sequence_ids = []
    if req.send_followups:
        try:
            followups = generate_followups(
                lead,
                {"subject": final_subject, "body": final_body},
                campaign_prompt="",
                sender_info=sender_config,
            )
            sequence_ids = create_full_sequence(
                lead_id,
                lead["campaign"],
                req.variant,
                final_subject,
                final_body,
                followups,
                cc=final_cc,
            )
        except Exception as e:
            print(f"[API] Follow-up sequence error: {e}")

    # ── SEND with sequence_id so the tracked link is embedded ──
    result = send_email(
        sender_config,
        lead["email"],
        final_subject,
        final_body,
        cc=final_cc,
        lead_id=lead_id,
        sequence_id=sequence_ids[0] if sequence_ids else None,
    )

    if not result["success"]:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to send email: {result.get('error', 'Unknown error')}"
        )

    if sequence_ids:
        update_sequence_status(
            sequence_ids[0], "sent",
            message_id=result["message_id"],
            recipient_email=lead["email"],  # actual address used (may differ from DB if to_email override)
        )

    # Create / update discussion and record the sent message
    try:
        from memory.storage import get_or_create_discussion, add_message as _add_msg
        disc_id = get_or_create_discussion(lead_id, lead["campaign"], final_subject)
        _add_msg(
            disc_id, lead_id, "sent",
            subject=final_subject, body=final_body,
            from_email=sender_config.get("email"),
            sequence_id=sequence_ids[0] if sequence_ids else None,
            message_id=result["message_id"],
        )
    except Exception as e:
        print(f"[API] Discussion record error: {e}")

    # Update lead status
    with get_conn() as conn:
        conn.cursor().execute(
            "UPDATE leads SET status = 'sent', updated_at = NOW() WHERE id = %s",
            (lead_id,)
        )

    return {
        "lead_id": lead_id,
        "email": lead["email"],
        "variant": req.variant,
        "message_id": result["message_id"],
        "followups_created": len(sequence_ids) - 1 if sequence_ids else 0,
        "sequence_ids": sequence_ids,
        "status": "sent",
    }


@app.patch("/leads/{lead_id}/draft-email")
async def update_draft_email(lead_id: str, req: DraftEmailUpdate):
    """
    Update a lead's draft email.
    Allows manual editing before sending.
    """
    # Get current draft_emails
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT draft_emails FROM leads WHERE id = %s", (lead_id,))
        row = cursor.fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="Lead not found")
        
        # Parse existing draft_emails
        draft_emails = {}
        if row[0]:
            try:
                draft_emails = json.loads(row[0]) if isinstance(row[0], str) else row[0]
            except Exception:
                draft_emails = {}
        
        # Update the specified variant
        draft_emails[req.variant] = {
            "subject": req.subject,
            "body": req.body,
            "cc": req.cc,
            "variant": req.variant,
        }
        
        # Save back to database
        cursor.execute("""
            UPDATE leads
            SET draft_emails = %s, updated_at = NOW()
            WHERE id = %s
        """, (json.dumps(draft_emails), lead_id))
        conn.commit()
    
    return {
        "lead_id": lead_id,
        "variant": req.variant,
        "updated": True,
    }


@app.post("/leads/batch-verify")
async def batch_verify_emails():
    """
    Batch verify all unverified emails.
    - Auto-verifies emails from Hunter/FTL/Apollo
    - SMTP-verifies pattern/web-scraped emails
    """
    from memory.storage import update_email_verification
    
    with get_conn() as conn:
        cursor = conn.cursor()
        
        # Get all unverified leads with email
        cursor.execute("""
            SELECT id, email, email_source
            FROM leads
            WHERE email IS NOT NULL
              AND email != ''
              AND email_verified = FALSE
        """)
        
        leads = cursor.fetchall()
        
        if not leads:
            return {"message": "No leads to verify", "verified": 0, "failed": 0}
        
        verified_count = 0
        failed_count = 0
        auto_verified_count = 0
        
        for lead_id, email, email_source in leads:
            # Auto-verify trusted sources
            if should_auto_verify(email_source):
                update_email_verification(lead_id, True)
                auto_verified_count += 1
            else:
                # SMTP verification
                verified, message = verify_email(email, email_source)
                update_email_verification(lead_id, verified)
                
                if verified:
                    verified_count += 1
                else:
                    failed_count += 1
    
    return {
        "total": len(leads),
        "auto_verified": auto_verified_count,
        "smtp_verified": verified_count,
        "failed": failed_count,
        "message": f"Verified {auto_verified_count + verified_count}/{len(leads)} emails",
    }

 
@app.patch("/leads/{lead_id}/email")
async def update_lead_email_address(lead_id: str, email_update: EmailAddressUpdate):
    """
    Update a lead's email address.
    Allows changing the recipient for testing.
    """
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE leads
            SET email = %s, updated_at = NOW()
            WHERE id = %s
        """, (email_update.email, lead_id))
        conn.commit()
    
    return {
        "status": "updated",
        "lead_id": lead_id,
        "email": email_update.email,
    }
 
def _follow_up_scheduler():
    """Background thread — tracker every 30s, follow-ups every 60s, monitor every 5min."""
    print("[Scheduler] Background scheduler started (tracker=30s, followups=60s, monitor=5min)")
    tick = 0
    while True:
        time.sleep(30)
        tick += 1

        # ── IMAP tracker (every 30 seconds) ──────────────────────────────────
        try:
            from agents.tracker_node import run_tracker
            t = run_tracker()
            if t["notifications"] > 0:
                print(f"[Scheduler] Tracker: {t['matched']} matched, "
                      f"{t['notifications']} notifications")
        except Exception as e:
            print(f"[Scheduler] Tracker error: {e}")

        # ── Follow-up sending (every 60 seconds = every 2 ticks) ─────────────
        if tick % 2 == 0:
            try:
                from agents.sender_node import run_due_sequences
                stats = run_due_sequences()
                if stats["sent"] > 0 or stats["failed"] > 0:
                    print(f"[Scheduler] Followups: sent={stats['sent']} failed={stats['failed']}")
            except Exception as e:
                print(f"[Scheduler] Followup error: {e}")

        # ── Monitor classification (every 5 minutes = every 10 ticks) ─────────
        if tick % 10 == 0:
            try:
                from agents.monitor_node import run_monitor
                m = run_monitor()
                if m["classified"] > 0:
                    print(f"[Scheduler] Monitor: {m['classified']} classified, "
                          f"{m['actions_executed']} actions")
            except Exception as e:
                print(f"[Scheduler] Monitor error: {e}")


@app.on_event("startup")
def start_scheduler():
    thread = threading.Thread(target=_follow_up_scheduler, daemon=True)
    thread.start()
    print("[Scheduler] Follow-up background thread launched")


 # ── Open / Click / Unsubscribe tracking ───────────────────────────────────────

@app.get("/track/open/{sequence_id}/{token}")
def track_open(sequence_id: int, token: str):
    """1x1 pixel — records email open."""
    expected = hashlib.md5(f"open-{sequence_id}".encode()).hexdigest()[:16]
    if token == expected:
        try:
            with get_conn() as conn:
                conn.cursor().execute("""
                    UPDATE email_sequences
                    SET status = CASE WHEN status = 'sent' THEN 'opened' ELSE status END,
                        opened_at = COALESCE(opened_at, NOW())
                    WHERE id = %s
                """, (sequence_id,))
                print(f"[Track] Open detected: sequence {sequence_id}")
        except Exception as e:
            print(f"[Track] Open error: {e}")

    # Return 1x1 transparent GIF
    pixel = b'\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00\x21\xf9\x04\x00\x00\x00\x00\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02\x44\x01\x00\x3b'
    return Response(content=pixel, media_type="image/gif")


def _unsub_page(title: str, message: str, lead_id: str = None,
                token: str = None, action: str = None) -> str:
    """Render a styled unsubscribe/resubscribe confirmation page.
    action: 'resubscribe' | 'unsubscribe' | None — adds the matching button."""
    button = ""
    if action == "resubscribe" and lead_id and token:
        button = f"""
        <a href="{BASE_URL}/resubscribe/{lead_id}/{token}" style="
            display:inline-block;margin-top:24px;padding:12px 28px;
            background:#6c5ce7;color:#fff;text-decoration:none;border-radius:8px;
            font-weight:600;font-size:14px">Resubscribe</a>
        <p style="color:#999;font-size:12px;margin-top:16px">
            Changed your mind? Click above to start receiving emails again.</p>"""
    elif action == "unsubscribe" and lead_id and token:
        button = f"""
        <a href="{BASE_URL}/unsubscribe/{lead_id}/{token}" style="
            display:inline-block;margin-top:24px;padding:12px 28px;
            background:#ff6b6b;color:#fff;text-decoration:none;border-radius:8px;
            font-weight:600;font-size:14px">Unsubscribe again</a>"""

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{title}</title></head>
    <body style="font-family:-apple-system,Segoe UI,Arial,sans-serif;background:#f5f6fa;margin:0">
    <div style="max-width:480px;margin:80px auto;background:#fff;padding:48px 40px;
        border-radius:16px;box-shadow:0 8px 32px rgba(0,0,0,0.08);text-align:center">
        <h2 style="color:#2d3436;margin:0 0 12px">{title}</h2>
        <p style="color:#636e72;font-size:15px;line-height:1.6;margin:0">{message}</p>
        {button}
    </div></body></html>"""


@app.get("/unsubscribe/{lead_id}/{token}")
def _do_unsubscribe(lead_id: str) -> None:
    """Core opt-out logic: cancel sequences, exclude email, mark lead, notify."""
    from memory.storage import cancel_remaining_sequence
    from agents.tracker_node import _create_notification

    cancel_remaining_sequence(lead_id)

    lead_name, lead_company, lead_email, campaign_id = "this contact", "", None, None
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name, company, email, campaign FROM leads WHERE id = %s",
            (lead_id,)
        )
        row = cursor.fetchone()
        if row:
            lead_name = row[0] or "Unknown"
            lead_company = row[1] or ""
            lead_email = row[2]
            campaign_id = row[3]
        cursor.execute(
            "UPDATE leads SET status = 'unsubscribed', updated_at = %s WHERE id = %s",
            (datetime.now().isoformat(), lead_id)
        )

    if lead_email:
        add_exclusion(lead_email, "email", "RGPD unsubscribe")

    who = f"{lead_name}" + (f" @ {lead_company}" if lead_company else "")
    _create_notification(
        campaign_id or "", lead_id, "unsubscribe",
        f"🚫 {who} unsubscribed",
        {"lead_id": lead_id, "email": lead_email},
    )


@app.get("/unsubscribe/{lead_id}/{token}")
def unsubscribe(lead_id: str, token: str):
    """RGPD unsubscribe page — cancels sequences, excludes email, notifies, offers resubscribe."""
    from utils.tokens import verify_token
    if not verify_token(lead_id, token):
        return HTMLResponse(content=_unsub_page(
            "Invalid link",
            "This link is invalid or has expired.",
        ))

    try:
        _do_unsubscribe(lead_id)
    except Exception as e:
        print(f"[Unsub] Error: {e}")

    return HTMLResponse(content=_unsub_page(
        "You have been unsubscribed",
        "You will no longer receive emails from us.",
        lead_id=lead_id, token=token, action="resubscribe",
    ))


@app.post("/unsubscribe/{lead_id}/{token}")
def unsubscribe_one_click(lead_id: str, token: str):
    """RFC 8058 one-click unsubscribe — called by the mail client (Gmail/Outlook)."""
    from utils.tokens import verify_token
    if not verify_token(lead_id, token):
        raise HTTPException(status_code=400, detail="Invalid token")
    try:
        _do_unsubscribe(lead_id)
    except Exception as e:
        print(f"[Unsub] One-click error: {e}")
    return {"status": "unsubscribed"}


@app.get("/resubscribe/{lead_id}/{token}")
def resubscribe(lead_id: str, token: str):
    """Re-enable emails for a lead that previously unsubscribed."""
    from utils.tokens import verify_token
    if not verify_token(lead_id, token):
        return HTMLResponse(content=_unsub_page(
            "Invalid link",
            "This link is invalid or has expired.",
        ))

    lead_name, lead_company, lead_email, campaign_id = "this contact", "", None, None
    try:
        from agents.tracker_node import _create_notification

        with get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name, company, email, campaign FROM leads WHERE id = %s",
                (lead_id,)
            )
            row = cursor.fetchone()
            if row:
                lead_name = row[0] or "Unknown"
                lead_company = row[1] or ""
                lead_email = row[2]
                campaign_id = row[3]
            # Restore lead status
            cursor.execute(
                "UPDATE leads SET status = 'enriched', updated_at = %s WHERE id = %s",
                (datetime.now().isoformat(), lead_id)
            )

        if lead_email:
            remove_exclusion_by_value(lead_email, "email")

        who = f"{lead_name}" + (f" @ {lead_company}" if lead_company else "")
        _create_notification(
            campaign_id or "", lead_id, "resubscribe",
            f"✅ {who} resubscribed",
            {"lead_id": lead_id, "email": lead_email},
        )
    except Exception as e:
        print(f"[Resub] Error: {e}")

    return HTMLResponse(content=_unsub_page(
        "You're resubscribed",
        "Welcome back! You will receive our emails again.",
        lead_id=lead_id, token=token, action="unsubscribe",
    ))

@app.get("/track/click/{sequence_id}")
def track_click(sequence_id: int, url: str = ""):
    """Track link click, create notification, redirect to real URL."""
    lead_id, campaign_id, lead_name, lead_company = None, None, "Unknown", "Unknown"

    # Transaction 1: record click timestamp in email_sequences (leadflow owns this table)
    try:
        with get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE email_sequences SET clicked_at = COALESCE(clicked_at, NOW())
                WHERE id = %s RETURNING lead_id, campaign_id
            """, (sequence_id,))
            row = cursor.fetchone()
            if row:
                lead_id, campaign_id = row
                cursor.execute("SELECT name, company FROM leads WHERE id = %s", (lead_id,))
                lead_row = cursor.fetchone()
                if lead_row:
                    lead_name, lead_company = lead_row
        print(f"[Track] Click recorded: {lead_name} @ {lead_company} → {url}")
    except Exception as e:
        print(f"[Track] Click record error: {e}")

    # Transaction 2: notification + discussion message
    if lead_id:
        try:
            with get_conn() as conn:
                cursor = conn.cursor()

                # 2a. Notification
                cursor.execute("""
                    INSERT INTO lead_notifications (campaign_id, lead_id, type, message, metadata)
                    VALUES (%s, %s, 'link_clicked', %s, %s)
                """, (
                    campaign_id, lead_id,
                    f"{lead_name} from {lead_company} clicked your link",
                    json.dumps({"url": url, "sequence_id": sequence_id,
                                "clicked_at": datetime.now().isoformat()}),
                ))

                # 2b. Add a click event to the discussion messages table
                #     so it's visible in the Inbox thread
                cursor.execute(
                    "SELECT id FROM discussions WHERE lead_id = %s ORDER BY created_at DESC LIMIT 1",
                    (lead_id,)
                )
                disc_row = cursor.fetchone()
                if disc_row:
                    raw_url = urllib.parse.unquote(url) if url else url
                    cursor.execute("""
                        INSERT INTO messages
                          (discussion_id, lead_id, direction, subject, body, created_at)
                        VALUES (%s, %s, 'event', 'Link clicked', %s, NOW())
                    """, (disc_row[0], lead_id,
                          f"Clicked your company link: {raw_url}"))
                    cursor.execute(
                        "UPDATE discussions SET last_message_at = NOW() WHERE id = %s",
                        (disc_row[0],)
                    )
        except Exception as e:
            print(f"[Track] Notification/message error: {e}")

    target = urllib.parse.unquote(url) if url else "https://example.com"
    return RedirectResponse(url=target)


@app.get("/notifications")
def list_notifications(unread_only: bool = True, limit: int = 50):
    with get_conn() as conn:
        from psycopg2.extras import RealDictCursor
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        if unread_only:
            cursor.execute("SELECT * FROM lead_notifications WHERE read = FALSE ORDER BY created_at DESC LIMIT %s", (limit,))
        else:
            cursor.execute("SELECT * FROM lead_notifications ORDER BY created_at DESC LIMIT %s", (limit,))
        rows = cursor.fetchall()
        for r in rows:
            if r.get("created_at") and hasattr(r["created_at"], "isoformat"):
                r["created_at"] = r["created_at"].isoformat()
            if r.get("metadata") and isinstance(r["metadata"], str):
                try: r["metadata"] = json.loads(r["metadata"])
                except: pass
        return {"notifications": [dict(r) for r in rows]}


@app.post("/notifications/{notif_id}/read")
def read_notification(notif_id: int):
    with get_conn() as conn:
        conn.cursor().execute("UPDATE lead_notifications SET read = TRUE WHERE id = %s", (notif_id,))
    return {"status": "read"}

@app.post("/notifications/read-all")
def read_all_notifications():
    with get_conn() as conn:
        conn.cursor().execute("UPDATE lead_notifications SET read = TRUE WHERE read = FALSE")
    return {"status": "ok"}


# ── Discussions ───────────────────────────────────────────────────────────────

@app.get("/discussions")
def list_discussions(campaign_id: Optional[str] = None):
    from memory.storage import get_discussions
    return {"discussions": get_discussions(campaign_id=campaign_id)}


def _build_full_thread(discussion_id: int, lead_id: str) -> list:
    """Return all messages for a discussion — merging the messages table
    with any sent email_sequences not yet recorded in messages."""
    from memory.storage import get_discussion_messages
    from psycopg2.extras import RealDictCursor

    msgs = get_discussion_messages(discussion_id)
    already_seq_ids = {m["sequence_id"] for m in msgs if m.get("sequence_id")}

    # Backfill sent emails from email_sequences that are missing from messages
    with get_conn() as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("""
            SELECT es.id AS sequence_id, es.subject, es.body, es.message_id,
                   COALESCE(es.sent_at, es.created_at) AS created_at
            FROM email_sequences es
            WHERE es.lead_id = %s
              AND es.status IN ('sent', 'replied', 'opened')
              AND es.step = 0
            ORDER BY es.created_at ASC
        """, (lead_id,))
        for row in cursor.fetchall():
            row = dict(row)
            if row["sequence_id"] in already_seq_ids:
                continue
            if row.get("created_at") and hasattr(row["created_at"], "isoformat"):
                row["created_at"] = row["created_at"].isoformat()
            msgs.append({
                "id": f"seq_{row['sequence_id']}",
                "discussion_id": discussion_id,
                "lead_id": lead_id,
                "direction": "sent",
                "subject": row["subject"],
                "body": row["body"],
                "from_email": None,
                "sequence_id": row["sequence_id"],
                "message_id": row["message_id"],
                "sentiment": None,
                "created_at": row["created_at"],
            })

    # Sort chronologically
    msgs.sort(key=lambda m: str(m.get("created_at") or ""))
    return msgs


@app.get("/discussions/{discussion_id}/messages")
def get_thread(discussion_id: int):
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT lead_id FROM discussions WHERE id = %s", (discussion_id,))
        row = cursor.fetchone()
    if not row:
        raise HTTPException(404, "Discussion not found")
    return {"messages": _build_full_thread(discussion_id, row[0])}


@app.get("/leads/{lead_id}/discussion")
def get_lead_discussion_endpoint(lead_id: str):
    from memory.storage import get_lead_discussion
    disc = get_lead_discussion(lead_id)
    if not disc:
        # No discussion yet — still show sent emails if any
        return {"discussion": None, "messages": []}
    msgs = _build_full_thread(disc["id"], lead_id)
    return {"discussion": disc, "messages": msgs}


@app.post("/discussions/{discussion_id}/generate-reply")
async def generate_discussion_reply(discussion_id: int):
    """Generate a reply email based on the last received message in a discussion."""
    from psycopg2.extras import RealDictCursor
    from agents.writer_node import generate_reply_from_response

    with get_conn() as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        # Discussion + lead info
        cursor.execute("""
            SELECT d.lead_id, l.name, l.company, l.role, l.insights
            FROM discussions d JOIN leads l ON l.id = d.lead_id
            WHERE d.id = %s
        """, (discussion_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(404, "Discussion not found")

        lead = {
            "name":    row["name"],
            "company": row["company"],
            "role":    row["role"],
            "insights": json.loads(row["insights"]) if isinstance(row["insights"], str) else (row["insights"] or {}),
        }

        # Last received message (the lead's reply)
        cursor.execute("""
            SELECT body FROM messages
            WHERE discussion_id = %s AND direction = 'received'
            ORDER BY created_at DESC LIMIT 1
        """, (discussion_id,))
        recv = cursor.fetchone()
        if not recv:
            raise HTTPException(400, "No received message found in this discussion")

        # Original sent email subject for context
        cursor.execute("""
            SELECT subject FROM messages
            WHERE discussion_id = %s AND direction = 'sent'
            ORDER BY created_at ASC LIMIT 1
        """, (discussion_id,))
        sent = cursor.fetchone()
        original_subject = sent["subject"] if sent else ""

    sender_config = get_sender_config(default_only=True) or {}

    try:
        result = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: generate_reply_from_response(
                lead, recv["body"], original_subject, sender_config
            ),
        )
    except Exception as e:
        raise HTTPException(500, f"Generation failed: {e}")

    return {"subject": result.get("subject", ""), "body": result.get("body", "")}


@app.post("/discussions/{discussion_id}/reply")
async def send_discussion_reply(discussion_id: int, req: DiscussionReplyRequest):
    """Send a reply email from within a discussion thread."""
    from psycopg2.extras import RealDictCursor

    # Get discussion + lead + last message-id for In-Reply-To threading
    with get_conn() as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("""
            SELECT d.lead_id, d.campaign_id,
                   l.name AS lead_name,
                   COALESCE(
                     (SELECT from_email FROM messages
                      WHERE discussion_id = d.id AND direction = 'received'
                      ORDER BY created_at DESC LIMIT 1),
                     l.email
                   ) AS to_email,
                   (SELECT message_id FROM messages
                    WHERE discussion_id = d.id
                    ORDER BY created_at DESC LIMIT 1) AS in_reply_to
            FROM discussions d
            JOIN leads l ON l.id = d.lead_id
            WHERE d.id = %s
        """, (discussion_id,))
        row = cursor.fetchone()

    if not row:
        raise HTTPException(404, "Discussion not found")

    lead_id     = row["lead_id"]
    to_email    = row["to_email"]
    in_reply_to = row["in_reply_to"]

    if not to_email:
        raise HTTPException(400, "No recipient email found for this discussion")

    sender_config = get_sender_config(default_only=True)
    if not sender_config:
        raise HTTPException(500, "No sender configuration found")

    result = send_email(
        sender_config, to_email,
        req.subject, req.body,
        cc=req.cc, lead_id=lead_id,
        in_reply_to=in_reply_to,
    )

    if not result["success"]:
        raise HTTPException(500, f"Send failed: {result.get('error', 'Unknown error')}")

    # Save sent message into the discussion
    from memory.storage import add_message
    add_message(
        discussion_id, lead_id, "sent",
        subject=req.subject, body=req.body,
        from_email=sender_config.get("email"),
        message_id=result["message_id"],
        in_reply_to=in_reply_to,
    )

    return {"status": "sent", "message_id": result["message_id"]}


# ── Google Calendar / Meet OAuth2 ────────────────────────────────────────────

_GCAL_SCOPES   = ["https://www.googleapis.com/auth/calendar.events"]
_TOKEN_FILE    = os.path.join(os.path.dirname(__file__), "..", ".google_token.json")
_REDIRECT_URI  = "http://localhost:8000/google/calendar/callback"

def _gcal_client_config():
    cid    = os.getenv("GOOGLE_CLIENT_ID", "")
    secret = os.getenv("GOOGLE_CLIENT_SECRET", "")
    if not cid or not secret:
        return None
    return {
        "web": {
            "client_id": cid,
            "client_secret": secret,
            "redirect_uris": [_REDIRECT_URI],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }

def _gcal_credentials():
    """Load stored credentials, refresh if expired."""
    import json as _json
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request

    if not os.path.exists(_TOKEN_FILE):
        return None
    try:
        with open(_TOKEN_FILE) as f:
            data = _json.load(f)

        cfg = _gcal_client_config() or {}
        web = cfg.get("web", {})

        # Build explicitly — avoids from_authorized_user_info format mismatch
        creds = Credentials(
            token=data.get("token") or data.get("access_token"),
            refresh_token=data.get("refresh_token"),
            token_uri=data.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=data.get("client_id") or web.get("client_id", ""),
            client_secret=data.get("client_secret") or web.get("client_secret", ""),
            scopes=data.get("scopes") or _GCAL_SCOPES,
        )

        # Restore expiry if saved
        if data.get("expiry"):
            from datetime import datetime as _dt
            try:
                creds.expiry = _dt.fromisoformat(data["expiry"].replace("Z", "+00:00"))
            except Exception:
                pass

        if creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                _save_token(creds)
            except Exception as refresh_err:
                err_str = str(refresh_err).lower()
                if "invalid_grant" in err_str or "token has been expired" in err_str or "revoked" in err_str:
                    # Refresh token is dead — delete it so the UI shows "Connect Google"
                    print(f"[GCal] Refresh token revoked — clearing stored token")
                    if os.path.exists(_TOKEN_FILE):
                        os.remove(_TOKEN_FILE)
                    return None
                raise

        # Final validity check: try a lightweight token refresh to confirm it works
        if creds.token and not creds.expired:
            return creds
        if creds.refresh_token:
            try:
                creds.refresh(Request())
                _save_token(creds)
                return creds
            except Exception as e:
                err_str = str(e).lower()
                if "invalid_grant" in err_str or "revoked" in err_str:
                    print(f"[GCal] Token invalid — clearing")
                    if os.path.exists(_TOKEN_FILE):
                        os.remove(_TOKEN_FILE)
                return None
        return None
    except Exception as e:
        print(f"[GCal] Credential load error: {e}")
        return None


def _save_token(creds):
    """Save credentials as a plain JSON dict."""
    import json as _json
    data = {
        "token":         creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri":     creds.token_uri,
        "client_id":     creds.client_id,
        "client_secret": creds.client_secret,
        "scopes":        list(creds.scopes) if creds.scopes else _GCAL_SCOPES,
        "expiry":        creds.expiry.isoformat() if creds.expiry else None,
    }
    with open(_TOKEN_FILE, "w") as f:
        _json.dump(data, f, indent=2)


@app.get("/google/calendar/status")
def gcal_status():
    """Check if Google Calendar is connected."""
    cfg   = _gcal_client_config()
    creds = _gcal_credentials()
    return {
        "configured": bool(cfg),
        "connected":  bool(creds),
    }


@app.get("/google/calendar/auth")
def gcal_auth():
    """Return the OAuth2 authorization URL — built manually (no PKCE)."""
    cfg = _gcal_client_config()
    if not cfg:
        raise HTTPException(400, "GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET not set in .env")
    import urllib.parse
    params = {
        "client_id":     cfg["web"]["client_id"],
        "redirect_uri":  _REDIRECT_URI,
        "response_type": "code",
        "scope":         " ".join(_GCAL_SCOPES),
        "access_type":   "offline",
        "prompt":        "consent",
    }
    auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)
    return {"auth_url": auth_url}


@app.get("/google/calendar/callback")
def gcal_callback(code: str = ""):
    """Exchange the auth code for tokens — direct HTTP, no PKCE library."""
    cfg = _gcal_client_config()
    if not cfg or not code:
        return HTMLResponse("<h2>Error: missing code or config</h2>")
    try:
        import httpx
        from google.oauth2.credentials import Credentials

        resp = httpx.post("https://oauth2.googleapis.com/token", data={
            "code":          code,
            "client_id":     cfg["web"]["client_id"],
            "client_secret": cfg["web"]["client_secret"],
            "redirect_uri":  _REDIRECT_URI,
            "grant_type":    "authorization_code",
        })
        tokens = resp.json()
        if "error" in tokens:
            return HTMLResponse(
                f"<h2>Auth error: {tokens.get('error_description', tokens['error'])}</h2>"
            )

        creds = Credentials(
            token=tokens.get("access_token"),
            refresh_token=tokens.get("refresh_token"),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=cfg["web"]["client_id"],
            client_secret=cfg["web"]["client_secret"],
            scopes=_GCAL_SCOPES,
        )
        _save_token(creds)
    except Exception as e:
        return HTMLResponse(f"<h2>Auth error: {e}</h2>")

    return HTMLResponse("""
        <html><body style="font-family:Arial;text-align:center;padding:60px">
        <h2 style="color:#00b894">&#10003; Google Calendar connected!</h2>
        <p>You can close this tab and return to TheLeadFlow.</p>
        <script>window.close();</script>
        </body></html>
    """)


@app.post("/discussions/{discussion_id}/create-meet")
async def create_google_meet(discussion_id: int, req: ScheduleMeetRequest):
    """Create a Google Calendar event with Meet link. Returns meet_link."""
    from psycopg2.extras import RealDictCursor
    from googleapiclient.discovery import build
    from datetime import datetime as dt, timedelta, timezone

    creds = _gcal_credentials()
    if not creds:
        raise HTTPException(401, "Google Calendar not connected. Visit /google/calendar/auth first.")

    with get_conn() as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("""
            SELECT d.lead_id, l.name, l.email, l.company
            FROM discussions d JOIN leads l ON l.id = d.lead_id
            WHERE d.id = %s
        """, (discussion_id,))
        row = cursor.fetchone()

    # Build attendees list
    primary = req.to_email or (row["email"] if row else None)
    extras  = req.extra_emails or []
    attendees = [{"email": e} for e in {primary, *extras} if e]

    # Event times
    start_dt = dt.strptime(f"{req.date} {req.time}", "%Y-%m-%d %H:%M")
    dur      = req.duration or 60
    end_dt   = start_dt + timedelta(minutes=dur)

    lead_name = row["name"] if row else "Lead"
    company   = row["company"] if row else ""

    event = {
        "summary": f"Meeting with {lead_name}" + (f" ({company})" if company else ""),
        "description": req.notes or "",
        "start": {"dateTime": start_dt.isoformat(), "timeZone": "UTC"},
        "end":   {"dateTime": end_dt.isoformat(),   "timeZone": "UTC"},
        "attendees": attendees,
        "conferenceData": {
            "createRequest": {
                "requestId": f"leadflow-{discussion_id}-{int(dt.now().timestamp())}",
                "conferenceSolutionKey": {"type": "hangoutsMeet"},
            }
        },
        "reminders": {"useDefault": True},
    }

    try:
        service = build("calendar", "v3", credentials=creds)
        created = service.events().insert(
            calendarId="primary",
            body=event,
            conferenceDataVersion=1,
            sendUpdates="all" if attendees else "none",
        ).execute()

        meet_link = (
            created.get("hangoutLink")
            or next(
                (e["uri"] for e in created.get("conferenceData", {}).get("entryPoints", [])
                 if e.get("entryPointType") == "video"),
                None,
            )
        )
        return {
            "status":      "created",
            "meet_link":   meet_link,
            "event_id":    created.get("id"),
            "event_link":  created.get("htmlLink"),
            "attendees":   [a["email"] for a in attendees],
        }
    except Exception as e:
        err_str = str(e).lower()
        if "invalid_grant" in err_str or "revoked" in err_str:
            if os.path.exists(_TOKEN_FILE):
                os.remove(_TOKEN_FILE)
            raise HTTPException(401, "Google Calendar token expired — please reconnect via /google/calendar/auth")
        raise HTTPException(500, f"Google Calendar error: {e}")


# ── Tracker (IMAP reply check) ────────────────────────────────────────────────

@app.post("/tracker/run")
async def run_tracker_endpoint(campaign_id: Optional[str] = None):
    """Manually trigger IMAP inbox check (Tracker) then Monitor classification."""
    try:
        from agents.tracker_node import run_tracker
        from agents.monitor_node import run_monitor

        tracker_stats = await asyncio.get_event_loop().run_in_executor(
            None, lambda: run_tracker(campaign_id)
        )
        # Run monitor immediately after tracker to classify any new replies
        monitor_stats = await asyncio.get_event_loop().run_in_executor(
            None, lambda: run_monitor(campaign_id)
        )
        return {
            "status": "ok",
            "tracker": tracker_stats,
            "monitor": monitor_stats,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))




@app.post("/discussions/{discussion_id}/schedule-meet")
async def schedule_meet(discussion_id: int, req: ScheduleMeetRequest):
    """Send a meeting invitation email to the lead for a Google Meet."""
    from psycopg2.extras import RealDictCursor
    from agents.sender_node import send_email

    with get_conn() as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("""
            SELECT d.lead_id, l.name, l.email, l.company, l.role
            FROM discussions d JOIN leads l ON l.id = d.lead_id
            WHERE d.id = %s
        """, (discussion_id,))
        row = cursor.fetchone()

    sender_config = get_sender_config(default_only=True)
    if not sender_config:
        raise HTTPException(500, "No sender configuration found")

    # Determine recipients
    primary_email = req.to_email or (row["email"] if row else None)
    if not primary_email:
        raise HTTPException(400, "No recipient email provided")

    extra = req.extra_emails or []
    all_recipients = list({primary_email} | set(extra))

    from datetime import datetime as dt

    start = dt.strptime(f"{req.date} {req.time}", "%Y-%m-%d %H:%M")
    dur   = req.duration or 60

    dur_label = (
        f"{dur} min" if dur < 60 else
        f"{dur // 60}h{(' ' + str(dur % 60) + 'min') if dur % 60 else ''}"
    ) if req.duration else "open-ended"

    lead_name_short = (row["name"] or "").split()[0] if row and row["name"] else "there"

    # Build body parts outside f-string to avoid backslash-in-expression errors
    extra_line   = f"\nOther invitees: {', '.join(extra)}\n" if extra else ""
    agenda_line  = f"Agenda:\n{req.notes}\n" if req.notes else ""
    sender_title = sender_config.get("title", "")
    sender_co    = sender_config.get("company", "")
    title_line   = f"{sender_title}, {sender_co}" if sender_title and sender_co else sender_co

    body = (
        f"Hi {lead_name_short},\n\n"
        f"I'd love to connect for a {dur_label} call on "
        f"{start.strftime('%A, %B %d at %I:%M %p')}.\n"
        f"{extra_line}\n"
        f"{agenda_line}"
        f"Please confirm if this works for you, or suggest a time that suits you better.\n\n"
        f"Best regards,\n"
        f"{sender_config.get('name', '')}\n"
        f"{title_line}"
    )

    cc = ", ".join(extra) if extra else None

    result = send_email(
        sender_config,
        primary_email,
        f"Meeting invitation — {start.strftime('%B %d at %I:%M %p')}",
        body,
        cc=cc,
        lead_id=row["lead_id"] if row else None,
    )

    if not result["success"]:
        raise HTTPException(500, f"Email failed: {result.get('error')}")

    return {
        "status": "sent",
        "recipients": all_recipients,
        "duration": dur_label,
    }


@app.post("/monitor/run")
async def run_monitor_endpoint(campaign_id: Optional[str] = None):
    """Manually trigger Monitor to classify unprocessed replies."""
    try:
        from agents.monitor_node import run_monitor
        stats = await asyncio.get_event_loop().run_in_executor(
            None, lambda: run_monitor(campaign_id)
        )
        return {"status": "ok", **stats}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
