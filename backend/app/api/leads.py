# backend/app/api/leads.py
from __future__ import annotations

import asyncio
import logging
from typing import List, Optional, Any, Dict

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import SessionLocal, get_db
from app.models.lead import Lead
from app.models.data_packet import DataPacket
from app.agents.data_packet_agent import DataPacketAgent
from app.api.websocket import broadcast_activity
from app.utils.normalize import normalize_industry


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/leads", tags=["leads"])


# -----------------------------
# Helpers (serialization)
# -----------------------------
def lead_to_dict(lead: Lead) -> dict:
    return {
        "id": lead.id,
        "name": getattr(lead, "name", None),
        "email": getattr(lead, "email", None),
        "phone": getattr(lead, "phone", None),
        "company": getattr(lead, "company", None),
        "title": getattr(lead, "title", None),
        "seniority": getattr(lead, "seniority", None),
        "linkedin_url": getattr(lead, "linkedin_url", None),
        "status": getattr(lead, "status", None),
        "score": getattr(lead, "score", None),
        "confidence": getattr(lead, "confidence", None),
        "sentiment": getattr(lead, "sentiment", None),
        "company_size": getattr(lead, "company_size", None),
        "company_industry": getattr(lead, "company_industry", None),
        "company_location": getattr(lead, "company_location", None),
        "company_website": getattr(lead, "company_website", None),
        "created_at": lead.created_at.isoformat() if getattr(lead, "created_at", None) else None,
        "updated_at": lead.updated_at.isoformat() if getattr(lead, "updated_at", None) else None,
    }


def packet_to_dict(packet: DataPacket) -> dict:
    import json

    pain_points = packet.pain_points
    try:
        if isinstance(pain_points, str):
            pain_points = json.loads(pain_points)
    except Exception:
        pass

    return {
        "id": packet.id,
        "lead_id": packet.lead_id,
        "company_analysis": packet.company_analysis,
        "pain_points": pain_points,
        "use_case_1_title": packet.use_case_1_title,
        "use_case_1_description": packet.use_case_1_description,
        "use_case_1_impact": packet.use_case_1_impact,
        "use_case_2_title": packet.use_case_2_title,
        "use_case_2_description": packet.use_case_2_description,
        "use_case_2_impact": packet.use_case_2_impact,
        "use_case_3_title": packet.use_case_3_title,
        "use_case_3_description": packet.use_case_3_description,
        "use_case_3_impact": packet.use_case_3_impact,
        "solution_1_title": packet.solution_1_title,
        "solution_1_description": packet.solution_1_description,
        "solution_1_roi": packet.solution_1_roi,
        "solution_2_title": packet.solution_2_title,
        "solution_2_description": packet.solution_2_description,
        "solution_2_roi": packet.solution_2_roi,
        "solution_3_title": packet.solution_3_title,
        "solution_3_description": packet.solution_3_description,
        "solution_3_roi": packet.solution_3_roi,
        "confidence_score": packet.confidence_score,
        "generated_at": packet.generated_at.isoformat() if getattr(packet, "generated_at", None) else None,
    }


def _basic_email_ok(email: str) -> bool:
    e = (email or "").strip()
    # Avoid EmailStr (email_validator dependency). This is a light check for now.
    return bool(e) and ("@" in e) and ("." in e.split("@")[-1])


def _default_company_description(company: str, industry: Optional[str], title: Optional[str]) -> str:
    # NOTE: This is a placeholder (no web browsing in backend). You can replace later when Apollo enrichment is available.
    company = (company or "").strip() or "the company"
    industry = (industry or "").strip() or "their industry"
    title = (title or "").strip() or "the team"
    return (
        f"{company} operates in {industry}. This lead ({title}) is being contacted for outbound automation and "
        f"AI-assisted workflows that improve prospecting, follow-ups, and sales operations efficiency."
    )


# -----------------------------
# Background packet generation
# -----------------------------
def _run_async(coro):
    """
    Run an async coroutine from sync background function safely.
    """
    try:
        return asyncio.run(coro)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()


def _generate_one_packet_background(lead_id: int):
    db = SessionLocal()
    try:
        lead = db.query(Lead).filter(Lead.id == lead_id).first()
        if not lead:
            return

        exists = db.query(DataPacket).filter(DataPacket.lead_id == lead_id).first()
        if exists:
            return

        agent = DataPacketAgent(db)
        _run_async(agent.create_data_packet(lead))

        logger.info("✅ Data packet created for lead_id=%s", lead_id)

    except Exception as e:
        logger.exception("❌ Data packet generation failed for lead_id=%s: %s", lead_id, e)

        # Optional: store the error in iip_data for debugging
        try:
            lead = db.query(Lead).filter(Lead.id == lead_id).first()
            if lead and hasattr(lead, "iip_data"):
                current = lead.iip_data or {}
                if not isinstance(current, dict):
                    current = {}
                current["data_packet_error"] = str(e)
                lead.iip_data = current
                db.commit()
        except Exception:
            pass

    finally:
        db.close()


def _generate_packets_background(lead_ids: List[int]):
    db = SessionLocal()
    try:
        agent = DataPacketAgent(db)

        for lead_id in lead_ids:
            lead = db.query(Lead).filter(Lead.id == lead_id).first()
            if not lead:
                continue

            exists = db.query(DataPacket).filter(DataPacket.lead_id == lead_id).first()
            if exists:
                continue

            try:
                _run_async(agent.create_data_packet(lead))
                logger.info("✅ Packet created lead_id=%s", lead_id)
            except Exception as e:
                logger.exception("❌ Packet create failed lead_id=%s: %s", lead_id, e)

    except Exception as e:
        logger.exception("Background packet generation error: %s", e)
    finally:
        db.close()


# -----------------------------
# Schemas
# -----------------------------
class ManualLeadCreate(BaseModel):
    # required in your current flow
    phone_number: str
    company_name: str
    contact_name: str
    email: str
    title: str

    # optional
    company_description: Optional[str] = None
    industry: Optional[str] = None


# ✅ IMPORTANT: static routes must appear BEFORE "/{lead_id}"


@router.post("/manual")
async def create_manual_lead(
    payload: ManualLeadCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Create (or reuse) a manual lead and automatically start data_packet generation in background.

    - Avoids Pydantic EmailStr to prevent `email_validator` dependency.
    - If company_description not provided, a safe placeholder is stored in iip_data.company_description.
    """
    try:
        phone = (payload.phone_number or "").strip()
        company = (payload.company_name or "").strip()
        name = (payload.contact_name or "").strip()
        email = (payload.email or "").strip()
        title = (payload.title or "").strip()

        # ✅ NEW (minimal): normalize industry
        industry = normalize_industry(payload.industry)

        company_description = (payload.company_description or "").strip() or None

        if not name:
            raise HTTPException(status_code=422, detail="contact_name is required")
        if not _basic_email_ok(email):
            raise HTTPException(status_code=422, detail="email is required")
        if not phone:
            raise HTTPException(status_code=422, detail="phone_number is required")
        if not company:
            raise HTTPException(status_code=422, detail="company_name is required")
        if not title:
            raise HTTPException(status_code=422, detail="title is required")

        # ✅ UPSERT by email (email is unique + non-null in your Lead model)
        lead = db.query(Lead).filter(Lead.email == email).first()

        created_now = False
        if not lead:
            lead = Lead(
                name=name,
                email=email,
                phone=phone,
                company=company,
                title=title,
                company_industry=industry,   # ✅ normalized
                status="cold",
                source="manual_upload",
            )
            created_now = True
        else:
            # update basics (helpful during manual tests)
            lead.name = name or lead.name
            lead.phone = phone or lead.phone
            lead.company = company or lead.company
            lead.title = title or lead.title
            if hasattr(lead, "company_industry"):
                lead.company_industry = industry or lead.company_industry  # ✅ normalized
            if hasattr(lead, "source") and not lead.source:
                lead.source = "manual_upload"
            if hasattr(lead, "status") and (lead.status in (None, "", "new")):
                lead.status = "cold"

        # store description into iip_data (no DB column needed)
        if hasattr(lead, "iip_data"):
            current = getattr(lead, "iip_data", None) or {}
            if not isinstance(current, dict):
                current = {}
            if company_description:
                current["company_description"] = company_description
                current["company_description_source"] = "manual"
            else:
                # placeholder (replace later with enrichment)
                current["company_description"] = _default_company_description(company, industry, title)
                current["company_description_source"] = "placeholder"
            lead.iip_data = current

        db.add(lead)
        try:
            db.commit()
        except IntegrityError as e:
            db.rollback()
            raise HTTPException(status_code=409, detail=f"Lead with this email already exists. ({str(e)})")

        db.refresh(lead)

        await broadcast_activity(
            {
                "type": "lead_created_manual" if created_now else "lead_updated_manual",
                "lead_id": lead.id,
                "company": getattr(lead, "company", None),
                "message": f"Manual lead {'created' if created_now else 'updated'} for {getattr(lead, 'company', '')}",
            }
        )

        # ✅ AUTO generate data packet for this lead
        background_tasks.add_task(_generate_one_packet_background, lead.id)

        return {"status": "success", "lead": lead_to_dict(lead)}

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Manual lead create failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))



@router.post("/generate-data-packets")
async def generate_data_packets_for_all_leads(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Creates packets for ALL leads that don't have one yet (background).
    """
    lead_ids = [
        r[0]
        for r in (
            db.query(Lead.id)
            .outerjoin(DataPacket, DataPacket.lead_id == Lead.id)
            .filter(DataPacket.id.is_(None))
            .all()
        )
    ]

    if not lead_ids:
        return {"status": "success", "message": "All leads already have data packets.", "count": 0}

    background_tasks.add_task(_generate_packets_background, lead_ids)

    await broadcast_activity(
        {
            "type": "data_packet_generation_started",
            "message": f"Generating data packets for {len(lead_ids)} leads...",
            "count": len(lead_ids),
        }
    )

    return {"status": "success", "message": "Background packet generation started", "count": len(lead_ids)}


@router.get("/")
async def list_leads(
    skip: int = 0,
    limit: int = 100,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
):
    try:
        q = db.query(Lead)
        if status:
            q = q.filter(Lead.status == status)
        leads = q.order_by(Lead.created_at.desc()).offset(skip).limit(limit).all()
        return [lead_to_dict(l) for l in leads]
    except Exception as e:
        logger.exception("Error listing leads: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{lead_id}")
async def get_lead(lead_id: int, db: Session = Depends(get_db)):
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead_to_dict(lead)


@router.get("/{lead_id}/data-packet")
async def get_or_create_lead_data_packet(lead_id: int, db: Session = Depends(get_db)):
    """
    If DataPacket exists -> return it
    If missing -> create it (LLM if configured, else fallback inside the agent)
    """
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    existing = db.query(DataPacket).filter(DataPacket.lead_id == lead_id).first()
    if existing:
        return packet_to_dict(existing)

    try:
        agent = DataPacketAgent(db)
        packet = await agent.create_data_packet(lead)

        await broadcast_activity(
            {
                "type": "data_packet_generated",
                "lead_id": lead.id,
                "company": getattr(lead, "company", None),
                "packet_id": packet.id,
                "message": f"Data packet created for {getattr(lead, 'company', '')}",
            }
        )

        return packet_to_dict(packet)

    except Exception as e:
        logger.exception("Packet generation failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Packet generation failed: {str(e)}")
