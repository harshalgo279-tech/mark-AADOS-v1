# backend/app/api/calls.py

import asyncio
import json
import os
from datetime import datetime
from typing import Any, List, Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.api.websocket import manager
from app.config import settings
from app.database import get_db
from app.models.call import Call
from app.models.lead import Lead
from app.models.transcript import Transcript
from app.models.email import Email
from app.models.linkedin import LinkedInMessage
from app.utils.logger import logger

from app.agents.voice_agent import VoiceAgent
from app.agents.email_agent import EmailAgent

from app.pipelines.call_pipeline import run_post_call_pipeline, ensure_call_analysis, handle_unanswered_call
from app.services.elevenlabs_service import ElevenLabsService

# Rate limiting support
from app.utils.rate_limit import (
    webhook_rate_limit,
    user_action_rate_limit,
    read_rate_limit,
    expensive_rate_limit,
)

router = APIRouter(prefix="/api/calls", tags=["calls"])


# ---------------------------
# Twilio Webhook Security
# ---------------------------

def _verify_twilio_signature(request: Request, form_data: dict) -> bool:
    """
    Verify Twilio webhook signature to prevent request forgery.

    Args:
        request: The FastAPI request object
        form_data: Parsed form data from the request

    Returns:
        True if signature is valid or verification is disabled, False otherwise
    """
    auth_token = getattr(settings, "TWILIO_AUTH_TOKEN", "") or ""
    if not auth_token:
        logger.warning("TWILIO_AUTH_TOKEN not set - skipping signature verification (DEV MODE)")
        return True

    try:
        from twilio.request_validator import RequestValidator
        validator = RequestValidator(auth_token)
    except ImportError:
        logger.error("twilio package not installed - cannot verify signatures")
        return True  # Allow in dev mode

    signature = request.headers.get("X-Twilio-Signature", "")
    if not signature:
        logger.warning("Missing X-Twilio-Signature header")
        return False

    # Build the full URL that Twilio used to generate the signature
    url = str(request.url)

    # Validate the request
    is_valid = validator.validate(url, form_data, signature)

    if not is_valid:
        logger.warning(f"Invalid Twilio signature for URL: {url}")

    return is_valid


async def _get_verified_form_data(request: Request, require_signature: bool = True) -> dict:
    """
    Parse form data and verify Twilio signature.

    Args:
        request: The FastAPI request object
        require_signature: If True, reject requests with invalid signatures

    Returns:
        Parsed form data dictionary

    Raises:
        HTTPException: If signature verification fails and require_signature is True
    """
    try:
        form = await request.form()
        form_data = {k: v for k, v in form.items()}
    except Exception as e:
        logger.error(f"Failed to parse form data: {e}")
        form_data = {}

    if require_signature:
        # In production, verify signature
        is_production = getattr(settings, "ENVIRONMENT", "development") == "production"

        if is_production and not _verify_twilio_signature(request, form_data):
            raise HTTPException(status_code=403, detail="Invalid Twilio signature")
        elif not is_production:
            # In dev mode, just verify if token is set
            if getattr(settings, "TWILIO_AUTH_TOKEN", ""):
                _verify_twilio_signature(request, form_data)  # Log warning but don't reject

    return form_data


class CallResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    lead_id: int
    phone_number: Optional[str] = None
    duration: Optional[int] = None
    status: Optional[str] = None

    full_transcript: Optional[str] = None
    transcript_summary: Optional[str] = None

    lead_interest_level: Optional[str] = None
    sentiment: Optional[str] = None

    demo_requested: bool = False
    follow_up_requested: bool = False

    objections_raised: Optional[Any] = None
    questions_asked: Optional[Any] = None
    use_cases_discussed: Optional[Any] = None

    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    recording_url: Optional[str] = None

    transcript_record: Optional[dict] = None


# ---------------------------
# Transcript helpers
# ---------------------------

def _transcript_to_dict(t: Transcript) -> dict:
    return {
        "twilio_call_sid": getattr(t, "twilio_call_sid", None),
        "call_id": t.call_id,
        "lead_id": t.lead_id,
        "full_transcript": t.full_transcript,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if getattr(t, "updated_at", None) else None,
    }


def _get_transcript_by_sid(db: Session, sid: str) -> Optional[Transcript]:
    sid = (sid or "").strip()
    if not sid:
        return None
    return db.query(Transcript).filter(Transcript.twilio_call_sid == sid).first()


def _upsert_transcript(db: Session, call: Call) -> Optional[Transcript]:
    sid = (call.twilio_call_sid or "").strip()
    text = (call.full_transcript or "").strip()
    if not sid or not text:
        return None

    existing = db.query(Transcript).filter(Transcript.twilio_call_sid == sid).first()
    if existing:
        existing.full_transcript = call.full_transcript
        existing.call_id = call.id
        existing.lead_id = call.lead_id
        db.commit()
        return existing

    t = Transcript(
        twilio_call_sid=sid,
        call_id=call.id,
        lead_id=call.lead_id,
        full_transcript=call.full_transcript,
    )
    db.add(t)
    db.commit()
    return t


# ---------------------------
# Email helpers
# ---------------------------

def _email_to_dict(e: Email) -> dict:
    return {
        "id": e.id,
        "lead_id": e.lead_id,
        "call_id": e.call_id,
        "subject": e.subject,
        "body_html": e.body_html,
        "body_text": e.body_text,
        "email_type": e.email_type,
        "status": e.status,
        "sent_at": e.sent_at.isoformat() if e.sent_at else None,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }


# ---------------------------
# Core APIs
# ---------------------------

@router.get("", response_model=List[CallResponse])
@router.get("/", response_model=List[CallResponse])
async def list_calls(
    skip: int = 0,
    limit: int = 100,
    lead_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    q = db.query(Call)
    if lead_id:
        q = q.filter(Call.lead_id == lead_id)

    calls = q.order_by(Call.created_at.desc()).offset(skip).limit(limit).all()

    out: List[dict] = []
    for c in calls:
        obj = CallResponse.model_validate(c).model_dump()
        sid = (c.twilio_call_sid or "").strip()
        t = _get_transcript_by_sid(db, sid) if sid else None
        obj["transcript_record"] = _transcript_to_dict(t) if t else None
        out.append(obj)

    return out


@router.get("/{call_id}", response_model=CallResponse)
async def get_call(call_id: int, db: Session = Depends(get_db)):
    call = db.query(Call).filter(Call.id == call_id).first()
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")

    obj = CallResponse.model_validate(call).model_dump()
    sid = (call.twilio_call_sid or "").strip()
    t = _get_transcript_by_sid(db, sid) if sid else None
    obj["transcript_record"] = _transcript_to_dict(t) if t else None
    return obj


@router.get("/{call_id}/transcript")
async def get_call_transcript(call_id: int, db: Session = Depends(get_db)):
    call = db.query(Call).filter(Call.id == call_id).first()
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")

    sid = (call.twilio_call_sid or "").strip()
    t = _get_transcript_by_sid(db, sid) if sid else None

    return {
        "call_id": call.id,
        "lead_id": call.lead_id,
        "status": call.status,
        "full_transcript": call.full_transcript,
        "transcript_summary": call.transcript_summary,
        "duration": call.duration,
        "sentiment": call.sentiment,
        "interest_level": call.lead_interest_level,
        "objections": call.objections_raised,
        "questions": call.questions_asked,
        "use_cases_discussed": call.use_cases_discussed,
        "demo_requested": call.demo_requested,
        "follow_up_requested": call.follow_up_requested,
        "recording_url": call.recording_url,
        "transcript_record": _transcript_to_dict(t) if t else None,
    }


# ---------------------------
# ✅ (Legacy) Optional: Serve TTS files if you still have old callers hitting it
# You can safely DELETE this entire section if you fully migrated.
# ---------------------------

@router.get("/{call_id}/tts/{filename}")
async def serve_tts_audio(call_id: int, filename: str):
    """
    Legacy endpoint from OpenAI TTS days.
    Keep temporarily if your frontend/old TwiML still references it.
    Delete once fully migrated.
    """
    cache_dir = getattr(settings, "TTS_CACHE_DIR", None) or "storage/tts"

    filename = (filename or "").strip()
    if not filename or ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    path = os.path.join(cache_dir, filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="TTS audio not found")

    return FileResponse(path, media_type="audio/mpeg", filename=filename)


# ---------------------------
# Twilio Webhooks (ElevenLabs-driven)
# ---------------------------

async def _twilio_field(request: Request, key: str) -> str:
    """
    Twilio posts form-encoded fields. If Twilio hits a GET for any reason, we also check query params.
    """
    if request.method.upper() == "POST":
        form = await request.form()
        return str(form.get(key) or "").strip()
    return str(request.query_params.get(key) or "").strip()


@router.get("/{call_id}/webhook")
@router.post("/{call_id}/webhook")
async def twilio_webhook(call_id: int, request: Request, db: Session = Depends(get_db)):
    """
    Twilio requests TwiML here.
    We call ElevenLabs register-call and return the TwiML (XML) back to Twilio.
    """
    # Verify Twilio signature for POST requests
    if request.method.upper() == "POST":
        try:
            form_data = await _get_verified_form_data(request, require_signature=True)
        except HTTPException:
            logger.warning(f"Twilio webhook signature verification failed for call_id={call_id}")
            return Response(content="<Response></Response>", media_type="application/xml")
    else:
        form_data = {}

    call = db.query(Call).filter(Call.id == call_id).first()
    if not call:
        return Response(content="<Response></Response>", media_type="application/xml")

    try:
        # Use verified form data or query params
        from_number = str(form_data.get("From") or request.query_params.get("From") or "").strip()
        to_number = str(form_data.get("To") or request.query_params.get("To") or "").strip()
        sid = str(form_data.get("CallSid") or request.query_params.get("CallSid") or "").strip()

        if sid and not call.twilio_call_sid:
            call.twilio_call_sid = sid

        if not call.started_at:
            call.started_at = datetime.utcnow()
        if not call.status or call.status in ("initiated", "queued"):
            call.status = "in-progress"
        db.commit()

        await manager.broadcast({"type": "call_in_progress", "call_id": call_id, "lead_id": call.lead_id})

        twilio_number = (getattr(settings, "TWILIO_PHONE_NUMBER", "") or "").strip()
        direction = "inbound" if (twilio_number and to_number == twilio_number) else "outbound"

        agent = VoiceAgent(db)
        twiml = await agent.build_twiml_for_twilio_webhook(
            call_id=call.id,
            from_number=from_number,
            to_number=to_number,
            direction=direction,
        )

        return Response(content=twiml, media_type="application/xml")

    except Exception as e:
        logger.error(f"Twilio webhook error: {str(e)}")
        return Response(content="<Response></Response>", media_type="application/xml")


@router.post("/{call_id}/webhook/turn")
async def twilio_turn(call_id: int, request: Request, db: Session = Depends(get_db)):
    """
    ✅ No longer used.
    The live conversation is handled fully by ElevenLabs once Twilio connects via the register-call TwiML.
    Keeping this endpoint as a no-op avoids 404s if anything old still calls it.
    """
    return Response(content="<Response></Response>", media_type="application/xml")


@router.post("/{call_id}/webhook/status")
async def twilio_status(call_id: int, request: Request, db: Session = Depends(get_db)):
    """
    Twilio call status callback.
    We still store status/duration and broadcast UI events.

    NEW: Triggers unanswered call email if call was not answered.

    NOTE: We DO NOT run the post-call pipeline here anymore,
    because transcript comes from ElevenLabs post-call webhook.
    """
    # Verify Twilio signature
    try:
        form_data = await _get_verified_form_data(request, require_signature=True)
    except HTTPException:
        logger.warning(f"Twilio status webhook signature verification failed for call_id={call_id}")
        return {"ok": False, "error": "Invalid signature"}

    call = db.query(Call).filter(Call.id == call_id).first()
    if not call:
        return {"ok": False}

    try:
        status = str(form_data.get("CallStatus") or "").strip()
        sid = str(form_data.get("CallSid") or "").strip()

        if sid and not call.twilio_call_sid:
            call.twilio_call_sid = sid

        if status:
            call.status = status

        if status == "completed":
            call.ended_at = datetime.utcnow()
            if call.started_at:
                call.duration = int((call.ended_at - call.started_at).total_seconds())

        db.commit()

        await manager.broadcast({
            "type": "call_status",
            "call_id": call.id,
            "lead_id": call.lead_id,
            "status": call.status,
        })

        # Handle unanswered calls - trigger intro email
        unanswered_statuses = ["no-answer", "busy", "failed", "canceled"]
        if status.lower() in unanswered_statuses:
            logger.info(f"Call unanswered (status={status}), triggering intro email for call_id={call.id}")
            asyncio.create_task(handle_unanswered_call(call.id))

        return {"ok": True}

    except Exception as e:
        logger.error(f"Status webhook error: {str(e)}")
        return {"ok": False}


@router.post("/{call_id}/webhook/recording")
async def twilio_recording(call_id: int, request: Request, db: Session = Depends(get_db)):
    # Verify Twilio signature
    try:
        form_data = await _get_verified_form_data(request, require_signature=True)
    except HTTPException:
        logger.warning(f"Twilio recording webhook signature verification failed for call_id={call_id}")
        return {"ok": False, "error": "Invalid signature"}

    call = db.query(Call).filter(Call.id == call_id).first()
    if not call:
        return {"ok": False}

    try:
        recording_url = str(form_data.get("RecordingUrl") or "").strip()
        recording_sid = str(form_data.get("RecordingSid") or "").strip()

        if recording_url:
            call.recording_url = recording_url
            db.commit()

            await manager.broadcast({
                "type": "recording_ready",
                "call_id": call.id,
                "lead_id": call.lead_id,
                "recording_url": recording_url,
                "recording_sid": recording_sid,
            })

        return {"ok": True}
    except Exception as e:
        logger.error(f"Recording webhook error: {str(e)}")
        return {"ok": False}


# ---------------------------
# ✅ ElevenLabs Post-Call Webhook (Transcript source of truth)
# ---------------------------

@router.post("/elevenlabs/post-call")
@webhook_rate_limit()
async def elevenlabs_post_call(request: Request, db: Session = Depends(get_db)):
    """
    Receives ElevenLabs post-call webhook payload.
    Stores transcript to Call.full_transcript, upserts Transcript record,
    broadcasts 'call_transcript_ready', and triggers your post-call pipeline.
    Rate limited to prevent abuse.
    """
    raw = await request.body()
    sig = request.headers.get("elevenlabs-signature") or request.headers.get("ElevenLabs-Signature")

    eleven = ElevenLabsService()
    if not eleven.verify_webhook_signature(raw_body=raw, signature_header=sig):
        raise HTTPException(status_code=401, detail="Invalid ElevenLabs webhook signature")

    payload = json.loads(raw.decode("utf-8"))
    event_type = payload.get("type") or payload.get("event_type")

    # Accept a small set of likely names (vendor payloads vary)
    allowed = {"post_call_transcription", "post_call", "post_call_analysis"}
    if str(event_type) not in allowed:
        return {"ok": True}

    data = payload.get("data") or {}
    transcript = data.get("transcript") or []
    metadata = data.get("metadata") or {}

    # Prefer correlation by dynamic_variables.call_id (we set it during register-call)
    call_id_val: Optional[int] = None
    ci = data.get("conversation_initiation_client_data") or {}
    dyn = (ci.get("dynamic_variables") or {}) if isinstance(ci, dict) else {}
    if dyn.get("call_id"):
        try:
            call_id_val = int(dyn["call_id"])
        except Exception:
            call_id_val = None

    # Fallback by Twilio CallSid if present
    twilio_sid = (
        metadata.get("call_sid")
        or metadata.get("twilio_call_sid")
        or data.get("twilio_call_sid")
        or payload.get("twilio_call_sid")
    )
    twilio_sid = str(twilio_sid).strip() if twilio_sid else None

    call: Optional[Call] = None
    if call_id_val is not None:
        call = db.query(Call).filter(Call.id == call_id_val).first()
    elif twilio_sid:
        call = db.query(Call).filter(Call.twilio_call_sid == twilio_sid).first()

    if not call:
        logger.warning("ElevenLabs post-call: could not match Call; ignoring")
        return {"ok": True}

    # Normalize transcript to your stored format
    lines: List[str] = []
    for turn in transcript:
        role = (turn.get("role") or "").upper()
        text = (turn.get("message") or turn.get("text") or "").strip()
        if not text:
            continue
        if role == "USER":
            lines.append(f"LEAD: {text}")
        else:
            lines.append(f"AGENT: {text}")

    if lines:
        call.full_transcript = "\n".join(lines).strip()

    # Optional status
    status = (data.get("status") or "").lower().strip()
    if status in ("done", "completed"):
        call.status = "completed"
        if not call.ended_at:
            call.ended_at = datetime.utcnow()
        if call.started_at and not call.duration:
            call.duration = int((call.ended_at - call.started_at).total_seconds())

    db.commit()

    # Upsert transcript record for UI
    _upsert_transcript(db, call)

    # Notify frontend
    await manager.broadcast({
        "type": "call_transcript_ready",
        "call_id": call.id,
        "lead_id": call.lead_id,
    })

    # Now run your pipeline (transcript exists)
    asyncio.create_task(run_post_call_pipeline(call.id))

    return {"ok": True}


# ---------------------------
# Manual analyze trigger
# ---------------------------

@router.post("/{call_id}/analyze")
@expensive_rate_limit()
async def analyze_call(call_id: int, request: Request, db: Session = Depends(get_db)):
    """Analyze a call - rate limited as it's an expensive AI operation."""
    call = db.query(Call).filter(Call.id == call_id).first()
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")

    try:
        agent = VoiceAgent(db)
        # In ElevenLabs architecture, VoiceAgent doesn't "end_call_and_analyze" usually,
        # but keep this for backward compatibility.
        if hasattr(agent, "end_call_and_analyze"):
            await agent.end_call_and_analyze(call)  # type: ignore
            db.commit()
            db.refresh(call)

        await ensure_call_analysis(db, call)
        _upsert_transcript(db, call)

        return {"ok": True, "call_id": call.id}

    except Exception as e:
        logger.error(f"Analyze call error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------
# ✅ Email + LinkedIn fetchers for UI
# ---------------------------

@router.get("/{call_id}/emails")
async def list_call_emails(call_id: int, db: Session = Depends(get_db)):
    call = db.query(Call).filter(Call.id == call_id).first()
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")

    rows = (
        db.query(Email)
        .filter(Email.call_id == call_id)
        .order_by(Email.created_at.asc())
        .all()
    )
    return {
        "call_id": call_id,
        "lead_id": call.lead_id,
        "count": len(rows),
        "emails": [_email_to_dict(x) for x in rows],
    }


@router.post("/{call_id}/emails/{email_id}/send")
async def send_call_email(call_id: int, email_id: int, db: Session = Depends(get_db)):
    call = db.query(Call).filter(Call.id == call_id).first()
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")

    email = db.query(Email).filter(Email.id == email_id).first()
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")

    if int(email.call_id or 0) != int(call_id):
        raise HTTPException(status_code=400, detail="Email does not belong to this call")

    agent = EmailAgent(db)
    result = await agent.send_email_by_id(email_id)

    db.refresh(email)
    return {"result": result, "email": _email_to_dict(email)}


@router.get("/{call_id}/linkedin/latest")
async def get_latest_linkedin_for_call(call_id: int, db: Session = Depends(get_db)):
    call = db.query(Call).filter(Call.id == call_id).first()
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")

    lead = db.query(Lead).filter(Lead.id == call.lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    li = (
        db.query(LinkedInMessage)
        .filter(LinkedInMessage.lead_id == lead.id)
        .order_by(LinkedInMessage.generated_at.desc())
        .first()
    )
    if not li:
        raise HTTPException(status_code=404, detail="No LinkedIn messages found")

    return {
        "lead_id": lead.id,
        "call_id": call.id,
        "linkedin": {
            "id": li.id,
            "connection_request": li.connection_request,
            "use_case_1_message": li.use_case_1_message,
            "use_case_2_message": li.use_case_2_message,
            "use_case_3_message": li.use_case_3_message,
            "follow_up_1": li.follow_up_1,
            "follow_up_2": li.follow_up_2,
            "generated_at": li.generated_at.isoformat() if li.generated_at else None,
        },
    }
