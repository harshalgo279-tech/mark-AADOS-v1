# backend/app/api/data_packets.py
from __future__ import annotations

import json
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.data_packet import DataPacket
from app.models.lead import Lead
from app.pipelines.call_pipeline import DataPacketAgent  # keep existing logic
from app.utils.logger import logger

from app.services.firecrawl_service import FirecrawlService  # ✅ NEW

router = APIRouter(prefix="/api/data-packet", tags=["data_packets"])


def packet_to_dict(p: DataPacket):
    return {
        "id": p.id,
        "lead_id": p.lead_id,
        "company_analysis": p.company_analysis,
        "pain_points": p.pain_points,
        "use_case_1_title": p.use_case_1_title,
        "use_case_1_description": p.use_case_1_description,
        "use_case_1_impact": p.use_case_1_impact,
        "use_case_2_title": p.use_case_2_title,
        "use_case_2_description": p.use_case_2_description,
        "use_case_2_impact": p.use_case_2_impact,
        "use_case_3_title": p.use_case_3_title,
        "use_case_3_description": p.use_case_3_description,
        "use_case_3_impact": p.use_case_3_impact,
        "solution_1_title": p.solution_1_title,
        "solution_1_description": p.solution_1_description,
        "solution_1_roi": p.solution_1_roi,
        "solution_2_title": p.solution_2_title,
        "solution_2_description": p.solution_2_description,
        "solution_2_roi": p.solution_2_roi,
        "solution_3_title": p.solution_3_title,
        "solution_3_description": p.solution_3_description,
        "solution_3_roi": p.solution_3_roi,
        "confidence_score": p.confidence_score,
        "generated_at": p.generated_at.isoformat() if p.generated_at else None,
    }


@router.get("/{lead_id}")
async def get_data_packet(lead_id: int, db: Session = Depends(get_db)):
    packet = db.query(DataPacket).filter(DataPacket.lead_id == lead_id).first()
    if not packet:
        raise HTTPException(status_code=404, detail="Data packet not found")
    return packet_to_dict(packet)


def _ensure_dict(v: Any) -> Dict[str, Any]:
    """
    Lead.iip_data might be dict (JSON column) or sometimes a JSON string.
    Normalize safely to a dict.
    """
    if v is None:
        return {}
    if isinstance(v, dict):
        return v
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return {}
        try:
            obj = json.loads(s)
            return obj if isinstance(obj, dict) else {}
        except Exception:
            return {}
    return {}


def _compact_text(text: str, limit: int = 4500) -> str:
    s = (text or "").strip()
    if len(s) <= limit:
        return s
    return s[:limit].rsplit(" ", 1)[0] + "..."


def _extract_markdown_text(scraped: Any) -> str:
    """
    Firecrawl scrape_url result shape can vary slightly by SDK version.
    Try common locations to retrieve markdown text.
    """
    if not scraped:
        return ""

    # Sometimes result is directly a dict with "markdown"
    if isinstance(scraped, dict):
        if isinstance(scraped.get("markdown"), str):
            return scraped.get("markdown", "") or ""

        # Sometimes nested under "data"
        data = scraped.get("data")
        if isinstance(data, dict) and isinstance(data.get("markdown"), str):
            return data.get("markdown", "") or ""

        # Fallback keys
        for k in ("content", "text", "body"):
            if isinstance(scraped.get(k), str):
                return scraped.get(k, "") or ""

    # If SDK returned string (unlikely but safe)
    if isinstance(scraped, str):
        return scraped

    return ""


@router.post("/generate/{lead_id}")
async def generate_data_packet(lead_id: int, db: Session = Depends(get_db)):
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    # ✅ Keep current behavior: if already created, just return it
    existing = db.query(DataPacket).filter(DataPacket.lead_id == lead.id).first()
    if existing:
        return packet_to_dict(existing)

    # -------------------------
    # ✅ Firecrawl enrichment BEFORE DataPacket creation
    # -------------------------
    company_website = (getattr(lead, "company_website", None) or "").strip()

    firecrawl = FirecrawlService()
    if company_website and firecrawl.is_enabled():
        try:
            scraped = firecrawl.scrape_markdown(company_website, timeout_ms=20000)
            markdown = _compact_text(_extract_markdown_text(scraped), limit=4500)

            if markdown:
                iip = _ensure_dict(getattr(lead, "iip_data", None))

                # ✅ DataPacketAgent already reads iip_data["company_description"]
                # Fill it if absent/empty (don’t overwrite user-provided description)
                if not (iip.get("company_description") or "").strip():
                    iip["company_description"] = markdown

                # Store raw scrape for debugging/future use
                iip["firecrawl"] = {
                    "company_website": company_website,
                    "result": scraped,
                }

                setattr(lead, "iip_data", iip)
                db.commit()
                db.refresh(lead)

        except Exception as e:
            # Non-fatal: DataPacketAgent will still run with fallback behavior
            logger.error(f"Firecrawl enrichment failed lead_id={lead.id} website={company_website}: {e}")

    # -------------------------
    # Existing DataPacket generation logic (unchanged)
    # -------------------------
    packet = await DataPacketAgent(db).create_data_packet(lead)
    return packet_to_dict(packet)
