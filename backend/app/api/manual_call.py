# backend/app/api/manual_call.py
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.database import get_db
from app.models.lead import Lead
from app.models.call import Call
from app.api.websocket import broadcast_activity

try:
    from app.agents.voice_agent import VoiceAgent
except Exception:
    VoiceAgent = None  # type: ignore

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/manual-call", tags=["manual-call"])


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


class ManualCallInitiateRequest(BaseModel):
    # required
    contact_name: str
    email: str
    phone_number: str
    company_name: str
    title: str

    # optional
    industry: Optional[str] = None
    company_description: Optional[str] = None
    lead_id: Optional[int] = None


@router.get("/initiate")
async def initiate_call_get_hint():
    return {
        "detail": "Use POST /api/manual-call/initiate with JSON body. GET does not start calls."
    }


@router.post("/initiate")
async def initiate_call(payload: ManualCallInitiateRequest, db: Session = Depends(get_db)):
    """
    Flow:
    1) Find lead by lead_id OR email
    2) Create/update lead fields
    3) Create Call row
    4) Kick VoiceAgent (Twilio) if available
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
        if not email or not _looks_like_email(email):
            raise HTTPException(status_code=422, detail="Valid email is required")
        if not phone:
            raise HTTPException(status_code=422, detail="phone_number is required")
        if not company:
            raise HTTPException(status_code=422, detail="company_name is required")
        if not title:
            raise HTTPException(status_code=422, detail="title is required")

        # 1) Resolve lead
        lead: Optional[Lead] = None

        if payload.lead_id:
            lead = db.query(Lead).filter(Lead.id == int(payload.lead_id)).first()

        if not lead:
            # prefer email as stable key (since it's required and unique)
            lead = db.query(Lead).filter(Lead.email == email).first()

        if lead:
            # update it
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
            # create lead
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

        # 3) Trigger VoiceAgent/Twilio
        twilio_started = False
        twilio_error = None
        twilio_sid = None

        if VoiceAgent is not None:
            try:
                agent = VoiceAgent(db)

                # ✅ standardize on this method name in your VoiceAgent
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
                logger.exception("Twilio/VoiceAgent start failed: %s", e)

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
        logger.exception("IntegrityError in manual-call initiate: %s", e)
        raise HTTPException(status_code=409, detail="Integrity error (possible duplicate email).")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Manual call initiate failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
