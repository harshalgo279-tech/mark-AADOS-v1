# backend/app/api/calls.py
from __future__ import annotations

import asyncio
import json
import os
import re
from datetime import datetime
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.api.websocket import manager
from app.config import settings
from app.database import SessionLocal, get_db
from app.models.call import Call
from app.models.data_packet import DataPacket
from app.models.lead import Lead
from app.models.transcript import Transcript
from app.utils.logger import logger
from app.utils.response_cache import get_response_cache

from app.agents.voice_agent import VoiceAgent

try:
    from app.agents.data_packet_agent import DataPacketAgent
except Exception:
    DataPacketAgent = None  # type: ignore

try:
    from app.agents.linkedin_agent import LinkedInAgent
except Exception:
    LinkedInAgent = None  # type: ignore

try:
    from app.models.linkedin import LinkedInMessage
except Exception:
    LinkedInMessage = None  # type: ignore

try:
    from app.services.pdf_service import PDFService
except Exception:
    PDFService = None  # type: ignore

try:
    from app.services.openai_service import OpenAIService
except Exception:
    OpenAIService = None  # type: ignore

try:
    from app.agents.email_agent import EmailAgent
except Exception:
    EmailAgent = None  # type: ignore


router = APIRouter(prefix="/api/calls", tags=["calls"])


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


def _clean_transcript_for_summary(txt: str) -> str:
    if not txt:
        return ""
    txt = re.sub(r"\bAGENT:\s*AGENT:\s*", "AGENT: ", txt, flags=re.IGNORECASE)
    txt = re.sub(r"\bLEAD:\s*LEAD:\s*", "LEAD: ", txt, flags=re.IGNORECASE)
    txt = re.sub(r"[ \t]+", " ", txt)
    return txt.strip()


async def _ensure_call_analysis(db: Session, call: Call) -> Call:
    if (call.transcript_summary or "").strip() and (call.sentiment or "").strip() and (call.lead_interest_level or "").strip():
        return call

    transcript = _clean_transcript_for_summary((call.full_transcript or "").strip())
    if not transcript:
        call.transcript_summary = call.transcript_summary or "No transcript available."
        call.sentiment = call.sentiment or "neutral"
        call.lead_interest_level = call.lead_interest_level or "medium"
        call.objections_raised = call.objections_raised or []
        call.questions_asked = call.questions_asked or []
        call.use_cases_discussed = call.use_cases_discussed or []
        db.commit()
        db.refresh(call)
        return call

    if OpenAIService is not None:
        try:
            svc = OpenAIService()
            prompt = f"""
Analyze this outbound sales call transcript and return JSON only.

TRANSCRIPT:
{transcript}

Return JSON with keys:
- summary_paragraph: 1 paragraph, 3-5 sentences, NO speaker labels, NO bullet points
- sentiment: "positive"|"neutral"|"negative"
- interest_level: "low"|"medium"|"high"
- objections: array of strings
- questions: array of strings
- use_cases_discussed: array of strings
- demo_requested: true/false
- follow_up_requested: true/false
"""
            resp = await svc.generate_completion(prompt=prompt, temperature=0.2, max_tokens=900, timeout_s=12.0)
            data = json.loads(resp) if resp else {}

            summary = (data.get("summary_paragraph") or "").strip()
            sentiment = (data.get("sentiment") or "neutral").strip().lower()
            interest = (data.get("interest_level") or "medium").strip().lower()

            call.transcript_summary = summary or call.transcript_summary
            call.sentiment = sentiment or call.sentiment or "neutral"
            call.lead_interest_level = interest or call.lead_interest_level or "medium"

            call.objections_raised = data.get("objections") or call.objections_raised or []
            call.questions_asked = data.get("questions") or call.questions_asked or []
            call.use_cases_discussed = data.get("use_cases_discussed") or call.use_cases_discussed or []
            if data.get("demo_requested") is not None:
                call.demo_requested = bool(data.get("demo_requested"))
            if data.get("follow_up_requested") is not None:
                call.follow_up_requested = bool(data.get("follow_up_requested"))

            db.commit()
            db.refresh(call)
            return call

        except Exception as e:
            logger.error(f"_ensure_call_analysis OpenAIService failed: {e}")

    t = transcript.lower()
    flattened = re.sub(r"\b(AGENT|LEAD):\s*", "", transcript, flags=re.IGNORECASE).strip()
    if len(flattened) > 650:
        flattened = flattened[:650].rsplit(" ", 1)[0] + "..."
    call.transcript_summary = call.transcript_summary or flattened

    negative_markers = ["not interested", "bye", "stop", "no thanks", "don't call", "not now"]
    positive_markers = ["yes", "sure", "interested", "sounds good", "tell me more", "demo"]

    if any(m in t for m in negative_markers):
        call.sentiment = call.sentiment or "negative"
        call.lead_interest_level = call.lead_interest_level or "low"
    elif any(m in t for m in positive_markers):
        call.sentiment = call.sentiment or "positive"
        call.lead_interest_level = call.lead_interest_level or "high"
    else:
        call.sentiment = call.sentiment or "neutral"
        call.lead_interest_level = call.lead_interest_level or "medium"

    call.objections_raised = call.objections_raised or []
    call.questions_asked = call.questions_asked or []
    call.use_cases_discussed = call.use_cases_discussed or []

    db.commit()
    db.refresh(call)
    return call


async def _post_call_pipeline(call_id: int) -> None:
    db = SessionLocal()
    try:
        call = db.query(Call).filter(Call.id == call_id).first()
        if not call:
            return

        lead = db.query(Lead).filter(Lead.id == call.lead_id).first()
        if not lead:
            return

        await _ensure_call_analysis(db, call)

        packet = db.query(DataPacket).filter(DataPacket.lead_id == lead.id).first()
        if packet is None and DataPacketAgent is not None:
            try:
                packet = await DataPacketAgent(db).create_data_packet(lead)  # type: ignore
                await manager.broadcast({"type": "data_packet_generated", "lead_id": lead.id})
            except Exception as e:
                logger.error(f"Post-call pipeline: data_packet generation failed lead_id={lead.id}: {e}")

        linkedin_row = None
        if packet is not None and LinkedInAgent is not None:
            try:
                li = LinkedInAgent(db)
                if hasattr(li, "generate_linkedin_scripts"):
                    linkedin_row = await li.generate_linkedin_scripts(lead=lead, data_packet=packet, call=call)  # type: ignore
                elif hasattr(li, "generate_linkedin_messages"):
                    linkedin_row = await li.generate_linkedin_messages(lead=lead, data_packet=packet, call=call)  # type: ignore
                await manager.broadcast({"type": "linkedin_messages_generated", "lead_id": lead.id, "call_id": call.id})
            except Exception as e:
                logger.error(f"Post-call pipeline: linkedin generation failed call_id={call.id}: {e}")

        if linkedin_row is None and LinkedInMessage is not None:
            linkedin_row = (
                db.query(LinkedInMessage)
                .filter(LinkedInMessage.lead_id == lead.id)
                .order_by(LinkedInMessage.generated_at.desc())
                .first()
            )

        pdf_path = None
        if PDFService is not None and packet is not None:
            try:
                pack_dict = {
                    "bd_summary": (call.transcript_summary or "").strip(),
                    "connection_request": getattr(linkedin_row, "connection_request", "") if linkedin_row else "",
                    "use_case_1_message": getattr(linkedin_row, "use_case_1_message", "") if linkedin_row else "",
                    "use_case_2_message": getattr(linkedin_row, "use_case_2_message", "") if linkedin_row else "",
                    "use_case_3_message": getattr(linkedin_row, "use_case_3_message", "") if linkedin_row else "",
                    "follow_up_1": getattr(linkedin_row, "follow_up_1", "") if linkedin_row else "",
                    "follow_up_2": getattr(linkedin_row, "follow_up_2", "") if linkedin_row else "",
                }

                lead_dict = {
                    "id": lead.id,
                    "name": lead.name,
                    "email": getattr(lead, "email", None),
                    "phone": getattr(lead, "phone", None),
                    "company": getattr(lead, "company", None),
                    "title": getattr(lead, "title", None),
                    "company_industry": getattr(lead, "company_industry", None),
                }
                call_dict = {
                    "id": call.id,
                    "status": call.status,
                    "duration": call.duration,
                    "lead_interest_level": call.lead_interest_level,
                    "sentiment": call.sentiment,
                }

                pdf = PDFService()
                pdf_path = pdf.generate_linkedin_pack_pdf(
                    lead=lead_dict,
                    call=call_dict,
                    linkedin_pack=pack_dict,
                )

                if hasattr(call, "pdf_generated"):
                    call.pdf_generated = True
                if hasattr(call, "pdf_path"):
                    call.pdf_path = pdf_path

                db.commit()

                await manager.broadcast({
                    "type": "linkedin_pack_ready",
                    "call_id": call.id,
                    "lead_id": lead.id,
                    "download_url": f"/api/calls/{call.id}/linkedin-pack/pdf",
                    "pdf_path": pdf_path,
                })

            except Exception as e:
                logger.error(f"Post-call pipeline: pdf generation failed call_id={call.id}: {e}")

        if EmailAgent is not None:
            try:
                emails_created = await EmailAgent(db).generate_and_store_sequence(call=call, pdf_path=pdf_path)
                await manager.broadcast({
                    "type": "emails_created",
                    "call_id": call.id,
                    "lead_id": lead.id,
                    "count": len(emails_created),
                })
            except Exception as e:
                logger.error(f"Post-call pipeline: email generation failed call_id={call.id}: {e}")

    except Exception as e:
        logger.error(f"Post-call pipeline fatal error call_id={call_id}: {e}")
    finally:
        try:
            db.close()
        except Exception:
            pass


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

    out = []
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
# Serve OpenAI TTS mp3 for Twilio <Play>
# ---------------------------
@router.get("/{call_id}/tts/{filename}")
async def serve_tts_audio(call_id: int, filename: str):
    cache_dir = getattr(settings, "TTS_CACHE_DIR", None) or "storage/tts"

    filename = (filename or "").strip()
    if not filename or ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    path = os.path.join(cache_dir, filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="TTS audio not found")

    return FileResponse(path, media_type="audio/mpeg", filename=filename)


@router.get("/{call_id}/webhook")
@router.post("/{call_id}/webhook")
async def twilio_webhook(call_id: int, request: Request, db: Session = Depends(get_db)):
    call = db.query(Call).filter(Call.id == call_id).first()
    if not call:
        return Response(content="<Response></Response>", media_type="application/xml")

    try:
        if not call.started_at:
            call.started_at = datetime.utcnow()
        if not call.status or call.status == "initiated":
            call.status = "in-progress"
        db.commit()

        await manager.broadcast({"type": "call_in_progress", "call_id": call_id, "lead_id": call.lead_id})

        agent = VoiceAgent(db)

        lead = db.query(Lead).filter(Lead.id == call.lead_id).first()
        opener_text = agent._build_opener(lead) if lead else "Hi — this is AADOS calling from Algonox."
        opener_audio_url = await agent.tts_audio_url(call_id=call.id, text=opener_text)

        twiml = agent.build_initial_twiml(
            call_id=call.id,
            opener_text=opener_text,
            opener_audio_url=opener_audio_url,
        )
        return Response(content=twiml, media_type="application/xml")

    except Exception as e:
        logger.error(f"Twilio webhook error: {str(e)}")
        return Response(content="<Response></Response>", media_type="application/xml")


@router.post("/{call_id}/webhook/turn")
async def twilio_turn(call_id: int, request: Request, db: Session = Depends(get_db)):
    import time
    turn_start = time.time()

    call = db.query(Call).filter(Call.id == call_id).first()
    if not call:
        return Response(content="<Response></Response>", media_type="application/xml")

    try:
        form = await request.form()
        user_speech = (form.get("SpeechResult") or "").strip()

        agent = VoiceAgent(db)

        if user_speech:
            agent.append_to_call_transcript(call, speaker="LEAD", text=user_speech)
            await manager.broadcast({
                "type": "call_transcript_update",
                "call_id": call.id,
                "lead_id": call.lead_id,
                "delta": f"LEAD: {user_speech}",
            })

        reply = await agent.generate_reply(call=call, user_input=user_speech)

        reply_clean = (reply or "").strip()
        if reply_clean.upper().startswith("AGENT:"):
            reply_clean = reply_clean.split(":", 1)[1].strip()

        agent.append_to_call_transcript(call, speaker="AGENT", text=reply_clean)
        _upsert_transcript(db, call)

        await manager.broadcast({
            "type": "call_transcript_update",
            "call_id": call.id,
            "lead_id": call.lead_id,
            "delta": f"AGENT: {reply_clean}",
        })

        # ✅ CRITICAL FIX: generate OpenAI TTS and pass as <Play>
        agent_audio_url = await agent.tts_audio_url(call_id=call.id, text=reply_clean)

        twiml = agent.build_turn_twiml(
            call_id=call.id,
            agent_text=reply_clean,
            agent_audio_url=agent_audio_url,
        )

        # Log total turn latency and cache stats
        turn_elapsed = (time.time() - turn_start) * 1000
        cache_stats = get_response_cache().get_stats()
        logger.info(f"[TELEMETRY] Turn complete in {turn_elapsed:.2f}ms | Cache stats: {cache_stats}")

        return Response(content=twiml, media_type="application/xml")

    except Exception as e:
        turn_elapsed = (time.time() - turn_start) * 1000
        logger.error(f"Turn webhook error after {turn_elapsed:.2f}ms: {str(e)}")
        return Response(content="<Response></Response>", media_type="application/xml")


@router.post("/{call_id}/webhook/status")
async def twilio_status(call_id: int, request: Request, db: Session = Depends(get_db)):
    call = db.query(Call).filter(Call.id == call_id).first()
    if not call:
        return {"ok": False}

    try:
        form = await request.form()
        status = (form.get("CallStatus") or "").strip()
        sid = (form.get("CallSid") or "").strip()

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

        if status == "completed":
            asyncio.create_task(_post_call_pipeline(call.id))

        return {"ok": True}

    except Exception as e:
        logger.error(f"Status webhook error: {str(e)}")
        return {"ok": False}


@router.post("/{call_id}/webhook/recording")
async def twilio_recording(call_id: int, request: Request, db: Session = Depends(get_db)):
    call = db.query(Call).filter(Call.id == call_id).first()
    if not call:
        return {"ok": False}

    try:
        form = await request.form()
        recording_url = (form.get("RecordingUrl") or "").strip()
        recording_sid = (form.get("RecordingSid") or "").strip()

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


@router.post("/{call_id}/analyze")
async def analyze_call(call_id: int, db: Session = Depends(get_db)):
    call = db.query(Call).filter(Call.id == call_id).first()
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")

    try:
        agent = VoiceAgent(db)
        if hasattr(agent, "end_call_and_analyze"):
            await agent.end_call_and_analyze(call)  # type: ignore
            db.commit()
            db.refresh(call)

        await _ensure_call_analysis(db, call)
        _upsert_transcript(db, call)

        return {"ok": True, "call_id": call.id}

    except Exception as e:
        logger.error(f"Analyze call error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{call_id}/linkedin-pack/pdf")
async def generate_linkedin_pack_pdf(call_id: int, db: Session = Depends(get_db)):
    if PDFService is None:
        raise HTTPException(status_code=500, detail="PDFService not available/import failed")

    call = db.query(Call).filter(Call.id == call_id).first()
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")

    lead = db.query(Lead).filter(Lead.id == call.lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found for call")

    await _ensure_call_analysis(db, call)

    packet = db.query(DataPacket).filter(DataPacket.lead_id == lead.id).first()
    if packet is None and DataPacketAgent is not None:
        try:
            packet = await DataPacketAgent(db).create_data_packet(lead)  # type: ignore
        except Exception as e:
            logger.error(f"DataPacket generation failed for lead_id={lead.id}: {e}")

    linkedin_row = None
    if LinkedInAgent is not None and packet is not None:
        try:
            li = LinkedInAgent(db)
            if hasattr(li, "generate_linkedin_scripts"):
                linkedin_row = await li.generate_linkedin_scripts(lead=lead, data_packet=packet, call=call)  # type: ignore
            elif hasattr(li, "generate_linkedin_messages"):
                linkedin_row = await li.generate_linkedin_messages(lead=lead, data_packet=packet, call=call)  # type: ignore
        except Exception as e:
            logger.error(f"LinkedIn script generation failed: {e}")

    if linkedin_row is None and LinkedInMessage is not None:
        linkedin_row = (
            db.query(LinkedInMessage)
            .filter(LinkedInMessage.lead_id == lead.id)
            .order_by(LinkedInMessage.generated_at.desc())
            .first()
        )

    pack_dict = {
        "bd_summary": (call.transcript_summary or "").strip(),
        "connection_request": getattr(linkedin_row, "connection_request", "") if linkedin_row else "",
        "use_case_1_message": getattr(linkedin_row, "use_case_1_message", "") if linkedin_row else "",
        "use_case_2_message": getattr(linkedin_row, "use_case_2_message", "") if linkedin_row else "",
        "use_case_3_message": getattr(linkedin_row, "use_case_3_message", "") if linkedin_row else "",
        "follow_up_1": getattr(linkedin_row, "follow_up_1", "") if linkedin_row else "",
        "follow_up_2": getattr(linkedin_row, "follow_up_2", "") if linkedin_row else "",
    }

    lead_dict = {
        "id": lead.id,
        "name": lead.name,
        "email": getattr(lead, "email", None),
        "phone": getattr(lead, "phone", None),
        "company": getattr(lead, "company", None),
        "title": getattr(lead, "title", None),
        "company_industry": getattr(lead, "company_industry", None),
    }
    call_dict = {
        "id": call.id,
        "status": call.status,
        "duration": call.duration,
        "lead_interest_level": call.lead_interest_level,
        "sentiment": call.sentiment,
    }

    pdf = PDFService()
    filepath = pdf.generate_linkedin_pack_pdf(
        lead=lead_dict,
        call=call_dict,
        linkedin_pack=pack_dict,
    )

    if hasattr(call, "pdf_generated"):
        call.pdf_generated = True
    if hasattr(call, "pdf_path"):
        call.pdf_path = filepath
    db.commit()

    await manager.broadcast({
        "type": "linkedin_pack_ready",
        "call_id": call.id,
        "lead_id": lead.id,
        "download_url": f"/api/calls/{call.id}/linkedin-pack/pdf",
        "pdf_path": filepath,
    })

    return {"ok": True, "call_id": call.id, "lead_id": lead.id, "pdf_path": filepath}


@router.get("/{call_id}/linkedin-pack/pdf")
async def download_linkedin_pack_pdf(call_id: int, db: Session = Depends(get_db)):
    call = db.query(Call).filter(Call.id == call_id).first()
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")

    path = (getattr(call, "pdf_path", "") or "").strip()
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="PDF not found. Generate it first.")

    filename = os.path.basename(path)
    return FileResponse(path, media_type="application/pdf", filename=filename)
