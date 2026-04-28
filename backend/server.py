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

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from utils.email_verifier import verify_email, should_auto_verify
from agents.sender_node import send_email, generate_followups
from memory.storage import update_sequence_status

# ── Add project root to path so imports work ──────────────────────────────────
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from memory.storage import (
    init_db, get_all_leads, get_campaign_leads,
    save_enrichment_results, update_lead_qualification,
    get_all_campaigns, get_campaign_by_prompt, _generate_campaign_id, get_conn,
    get_campaign_events, log_campaign_event, update_campaign_status,
    get_exclusion_list, add_exclusion, remove_exclusion,
    get_sender_config, save_sender_config, update_sender_config,
    find_similar_campaign, save_campaign_criteria,
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

class ExclusionCreate(BaseModel):
    value: str
    type: str       # company | domain | email
    reason: Optional[str] = None

class SenderCreate(BaseModel):
    name: str
    email: str
    title: Optional[str] = ""
    company: Optional[str] = ""
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


@app.patch("/leads/{lead_id}/email")
def update_email(lead_id: str, update: EmailUpdate):
    """Update a lead's draft email (after user edits in the UI)."""
    from memory.storage import get_conn

    with get_conn() as conn:
        cursor = conn.cursor()

        # Get current draft
        cursor.execute("SELECT draft_email FROM leads WHERE id = %s", (lead_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(404, "Lead not found")

        current = {}
        if row[0]:
            try:
                current = json.loads(row[0])
            except Exception:
                pass

        if update.subject is not None:
            current["subject"] = update.subject
        if update.body is not None:
            current["body"] = update.body

        cursor.execute(
            "UPDATE leads SET draft_email = %s, updated_at = %s WHERE id = %s",
            (json.dumps(current), datetime.now().isoformat(), lead_id),
        )

    return {"status": "updated", "draft_email": current}


@app.patch("/leads/{lead_id}")
def update_lead_status(lead_id: str, update: LeadStatusUpdate):
    from memory.storage import get_conn

    with get_conn() as conn:
        conn.cursor().execute(
            "UPDATE leads SET status = %s, updated_at = %s WHERE id = %s",
            (update.status, datetime.now().isoformat(), lead_id),
        )

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
        company=sender.company, signature=sender.signature, is_default=sender.is_default,
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
    
    # Send initial email
    result = send_email(
        sender_config,
        lead["email"],
        selected_email.get("subject", ""),
        selected_email.get("body", ""),
        cc=selected_email.get("cc"),
    )
    
    if not result["success"]:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to send email: {result.get('error', 'Unknown error')}"
        )
    
    # Create follow-up sequence if requested
    sequence_ids = []
    if req.send_followups:
        try:
            from memory.storage import create_full_sequence
            
            # Generate follow-ups via LLM
            followups = generate_followups(
                lead,
                selected_email,
                campaign_prompt="",  # TODO: Get from campaign
                sender_info=sender_config,
            )
            
            # Create sequence in DB
            sequence_ids = create_full_sequence(
                lead_id,
                lead["campaign"],
                req.variant,
                selected_email.get("subject", ""),
                selected_email.get("body", ""),
                followups,
                cc=selected_email.get("cc"),
            )
            
            # Mark initial as sent
            update_sequence_status(sequence_ids[0], "sent", message_id=result["message_id"])
            
        except Exception as e:
            print(f"[API] ⚠️ Failed to create follow-up sequence: {e}")
            # Don't fail the request - initial email was sent successfully
    
    # Update lead status
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE leads
            SET status = 'sent', updated_at = NOW()
            WHERE id = %s
        """, (lead_id,))
    
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
 


 



# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
