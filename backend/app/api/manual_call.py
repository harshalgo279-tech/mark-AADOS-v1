# backend/app/api/manual_call.py
#check
import logging
import asyncio
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.database import get_db, SessionLocal
from app.models.lead import Lead
from app.models.call import Call
from app.api.websocket import broadcast_activity
from app.config import settings
from app.utils.logger import logger
from app.utils.rate_limit import user_action_rate_limit
from app.auth.dependencies import get_current_user
from app.auth.models import UserInDB
from app.utils.validators import validate_phone_number, validate_email

# Optional pipeline deps
try:
    from app.models.data_packet import DataPacket
except Exception:
    DataPacket = None  # type: ignore

try:
    from app.pipelines.call_pipeline import DataPacketAgent
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
    from app.services.email_service import EmailService
except Exception:
    EmailService = None  # type: ignore

try:
    from app.agents.voice_agent import VoiceAgent
except Exception:
    VoiceAgent = None  # type: ignore


router = APIRouter(prefix="/api/manual-call", tags=["manual-call"])
logger_std = logging.getLogger(__name__)


def _looks_like_email(email: str) -> bool:
    if not email or "@" not in email:
        return False
    parts = email.split("@")
    if len(parts) != 2:
        return False
    return "." in parts[1]


def _safe_company_description(company: str, industry: Optional[str], title: Optional[str]) -> str:
    ind = (industry or "").strip()
    tit = (title or "").strip()
    if ind and tit:
        return f"{company} appears to operate in the {ind} space. This lead is a {tit}, likely responsible for key operational and growth initiatives."
    if ind:
        return f"{company} appears to operate in the {ind} space."
    return f"{company} is a business entity. (Auto-generated description; replace with researched company summary later.)"


def _store_company_description_iip(lead: Lead, company_description: Optional[str], industry: Optional[str], title: Optional[str]) -> None:
    desc = (company_description or "").strip()
    if not desc:
        desc = _safe_company_description(lead.company or "Company", industry, title)

    if hasattr(lead, "iip_data"):
        existing = getattr(lead, "iip_data", None) or {}
        if not isinstance(existing, dict):
            existing = {}
        existing["company_description"] = desc
        lead.iip_data = existing


def _bd_recipients() -> List[str]:
    raw = (getattr(settings, "BD_EMAIL_TO", "") or "").strip()
    if not raw:
        return []
    return [x.strip() for x in raw.split(",") if x.strip()]


def _lead_block(lead: Lead) -> str:
    return (
        f"Name: {lead.name}\n"
        f"Email: {lead.email}\n"
        f"Phone: {lead.phone}\n"
        f"Company: {lead.company}\n"
        f"Title: {lead.title}\n"
        f"Industry: {getattr(lead, 'company_industry', '') or ''}\n"
    )


def _packet_block(packet) -> str:
    if not packet:
        return "[No DataPacket yet]\n"
    return (
        f"Use Case 1: {packet.use_case_1_title} — {packet.use_case_1_impact}\n"
        f"Use Case 2: {packet.use_case_2_title} — {packet.use_case_2_impact}\n"
        f"Use Case 3: {packet.use_case_3_title} — {packet.use_case_3_impact}\n"
    )


def _linkedin_block(li_row) -> str:
    if not li_row:
        return "[No LinkedIn messages yet]\n"
    # support both single row (with fields) and list
    fields = [
        ("connection_request", getattr(li_row, "connection_request", "")),
        ("use_case_1_message", getattr(li_row, "use_case_1_message", "")),
        ("use_case_2_message", getattr(li_row, "use_case_2_message", "")),
        ("use_case_3_message", getattr(li_row, "use_case_3_message", "")),
        ("follow_up_1", getattr(li_row, "follow_up_1", "")),
        ("follow_up_2", getattr(li_row, "follow_up_2", "")),
    ]
    out = []
    for k, v in fields:
        v = (v or "").strip()
        if v:
            out.append(f"{k}:\n{v}\n")
    return "\n".join(out) if out else "[LinkedIn row exists but empty]\n"


async def _pre_call_pipeline(call_id: int) -> None:
    """
    Runs after manual call is created:
    - ensure DataPacket exists
    - generate LinkedIn messages (if available)
    - send BD email (NO DB storage)
    """
    db = SessionLocal()
    try:
        call = db.query(Call).filter(Call.id == call_id).first()
        if not call:
            return
        lead = db.query(Lead).filter(Lead.id == call.lead_id).first()
        if not lead:
            return

        # 1) Ensure DataPacket
        packet = None
        if DataPacket is not None:
            packet = db.query(DataPacket).filter(DataPacket.lead_id == lead.id).first()

        if packet is None and DataPacketAgent is not None:
            try:
                agent = DataPacketAgent(db)
                # support multiple method names safely
                if hasattr(agent, "create_data_packet"):
                    packet = await agent.create_data_packet(lead)  # type: ignore
                elif hasattr(agent, "generate_for_lead"):
                    packet = await agent.generate_for_lead(lead_id=lead.id)  # type: ignore
                elif hasattr(agent, "generate_and_store"):
                    packet = await agent.generate_and_store(lead_id=lead.id)  # type: ignore
            except Exception as e:
                logger.error(f"Pre-call pipeline: data_packet generation failed lead_id={lead.id}: {e}")

        # 2) Generate LinkedIn messages (optional)
        linkedin_row = None
        if packet is not None and LinkedInAgent is not None:
            try:
                li = LinkedInAgent(db)
                if hasattr(li, "generate_linkedin_scripts"):
                    linkedin_row = await li.generate_linkedin_scripts(lead=lead, data_packet=packet, call=call)  # type: ignore
                elif hasattr(li, "generate_linkedin_messages"):
                    linkedin_row = await li.generate_linkedin_messages(lead=lead, data_packet=packet, call=call)  # type: ignore
            except Exception as e:
                logger.error(f"Pre-call pipeline: linkedin generation failed call_id={call.id}: {e}")

        if linkedin_row is None and LinkedInMessage is not None:
            linkedin_row = (
                db.query(LinkedInMessage)
                .filter(LinkedInMessage.lead_id == lead.id)
                .order_by(LinkedInMessage.generated_at.desc())
                .first()
            )

        # 3) Send BD mail (no DB store)
        bds = _bd_recipients()
        if bds and EmailService is not None:
            subject = f"[AADOS] New Manual Lead + Call Started: {lead.name} @ {lead.company} (call_id={call.id})"
            body_text = (
                "AADOS — New Manual Call Started\n\n"
                "LEAD\n"
                + _lead_block(lead)
                + "\nDATA PACKET\n"
                + _packet_block(packet)
                + "\nLINKEDIN MESSAGES\n"
                + _linkedin_block(linkedin_row)
                + f"\nCall ID: {call.id}\n"
                + f"Started At: {call.started_at}\n"
            )
            body_html = "<pre>" + body_text + "</pre>"

            ok = await EmailService().send_to_many(
                to_emails=bds,
                subject=subject,
                html_body=body_html,
                text_body=body_text,
                to_name="BD",
            )

            await broadcast_activity({
                "type": "bd_email_sent",
                "call_id": call.id,
                "lead_id": lead.id,
                "ok": bool(ok),
                "message": "BD kickoff email sent" if ok else "BD kickoff email failed",
            })

        await broadcast_activity({
            "type": "pre_call_pipeline_done",
            "call_id": call.id,
            "lead_id": lead.id,
            "message": "Pre-call pipeline complete",
        })

    except Exception as e:
        logger.error(f"Pre-call pipeline fatal error call_id={call_id}: {e}")
    finally:
        try:
            db.close()
        except Exception:
            pass


class ManualCallInitiateRequest(BaseModel):
    contact_name: str
    email: str
    phone_number: str
    company_name: str
    title: str

    industry: Optional[str] = None
    company_description: Optional[str] = None
    lead_id: Optional[int] = None


@router.get("/initiate")
async def initiate_call_get_hint():
    return {"detail": "Use POST /api/manual-call/initiate with JSON body. GET does not start calls."}


@router.post("/initiate")
@user_action_rate_limit()
async def initiate_call(
    payload: ManualCallInitiateRequest,
    request: Request,
    current_user: UserInDB = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Flow:
    1) Find lead by lead_id OR email
    2) Create/update lead fields
    3) Create Call row
    4) Kick pre-call pipeline (data packet + linkedin + BD mail)
    5) Kick VoiceAgent/Twilio if available

    Rate limited to prevent spam calls.
    Requires authentication.
    """
    try:
        name = payload.contact_name.strip()
        email = payload.email.strip()
        phone = payload.phone_number.strip()
        company = payload.company_name.strip()
        title = payload.title.strip()

        industry = (payload.industry or "").strip() or None
        company_description = (payload.company_description or "").strip() or None

        if not name:
            raise HTTPException(status_code=422, detail="contact_name is required")

        # Validate email with proper validation
        email_valid, email_error = validate_email(email)
        if not email_valid:
            raise HTTPException(status_code=422, detail=email_error or "Valid email is required")

        # Validate phone number with international format support
        phone_valid, normalized_phone, phone_error = validate_phone_number(phone)
        if not phone_valid:
            raise HTTPException(status_code=422, detail=phone_error or "Valid phone number is required")
        phone = normalized_phone  # Use normalized E.164 format

        if not company:
            raise HTTPException(status_code=422, detail="company_name is required")
        if not title:
            raise HTTPException(status_code=422, detail="title is required")

        logger.info(f"Call initiated by user {current_user.email} to {phone}")

        # 1) Resolve lead
        lead: Optional[Lead] = None
        if payload.lead_id:
            lead = db.query(Lead).filter(Lead.id == int(payload.lead_id)).first()
        if not lead:
            lead = db.query(Lead).filter(Lead.email == email).first()

        if lead:
            lead.name = name
            lead.email = email
            lead.phone = phone
            lead.company = company
            lead.title = title
            lead.company_industry = industry
            lead.status = lead.status or "cold"
            _store_company_description_iip(lead, company_description, industry, title)
            db.commit()
            db.refresh(lead)

            await broadcast_activity({
                "type": "lead_updated_for_call",
                "lead_id": lead.id,
                "company": lead.company,
                "message": f"Lead updated for call: {lead.company}",
            })
        else:
            lead = Lead(
                name=name,
                email=email,
                phone=phone,
                company=company,
                title=title,
                company_industry=industry,
                status="cold",
            )
            if hasattr(lead, "source"):
                lead.source = "manual_call"

            _store_company_description_iip(lead, company_description, industry, title)

            db.add(lead)
            db.commit()
            db.refresh(lead)

            await broadcast_activity({
                "type": "lead_created_for_call",
                "lead_id": lead.id,
                "company": lead.company,
                "message": f"Lead created for call: {lead.company}",
            })

        # 2) Create Call row
        call = Call(
            lead_id=lead.id,
            phone_number=phone,
            status="initiated",
            started_at=datetime.utcnow(),
        )
        db.add(call)
        db.commit()
        db.refresh(call)

        await broadcast_activity({
            "type": "call_initiated",
            "message": f"Call initiated to {phone}",
            "lead_id": lead.id,
            "call_id": call.id,
            "company": lead.company,
        })

        # ✅ 4) PRE-CALL pipeline safely in background using a fresh SessionLocal
        asyncio.create_task(_pre_call_pipeline(call.id))

        # 5) Trigger VoiceAgent/Twilio
        twilio_started = False
        twilio_error = None
        twilio_sid = None

        if VoiceAgent is not None:
            try:
                agent = VoiceAgent(db)
                if hasattr(agent, "initiate_outbound_call"):
                    twilio_sid = await agent.initiate_outbound_call(lead=lead, call=call)
                    twilio_started = True
                else:
                    twilio_error = "VoiceAgent is present but missing initiate_outbound_call()."

                if twilio_started:
                    call.twilio_call_sid = twilio_sid
                    call.status = "queued"
                    db.commit()
                    db.refresh(call)

            except Exception as e:
                db.rollback()
                twilio_error = str(e)
                logger_std.exception("Twilio/VoiceAgent start failed: %s", e)

        return {
            "status": "success",
            "lead_id": lead.id,
            "call_id": call.id,
            "call_status": call.status,
            "twilio_started": twilio_started,
            "twilio_sid": twilio_sid,
            "twilio_error": twilio_error,
        }

    except IntegrityError as e:
        db.rollback()
        logger_std.exception("IntegrityError in manual-call initiate: %s", e)
        raise HTTPException(status_code=409, detail="Integrity error (possible duplicate email).")
    except HTTPException:
        raise
    except Exception as e:
        logger_std.exception("Manual call initiate failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
