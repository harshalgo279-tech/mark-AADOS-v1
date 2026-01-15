# backend/app/api/leads.py
from __future__ import annotations

import asyncio
import hashlib
import logging
import secrets
from datetime import datetime
from typing import List, Optional, Any, Dict

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import SessionLocal, get_db
from app.models.lead import Lead
from app.models.data_packet import DataPacket
from app.api.websocket import broadcast_activity
from app.utils.normalize import normalize_industry
from app.utils.logger import logger as app_logger
from app.config import settings

from app.pipelines.call_pipeline import DataPacketAgent
from app.services.firecrawl_service import FirecrawlService

# Authentication imports
from app.auth.dependencies import get_current_user
from app.auth.models import UserInDB


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/leads", tags=["leads"])

# Maximum pagination limit to prevent DoS
MAX_PAGINATION_LIMIT = 500


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
    return bool(e) and ("@" in e) and ("." in e.split("@")[-1])


def _default_company_description(company: str, industry: Optional[str], title: Optional[str]) -> str:
    company = (company or "").strip() or "the company"
    industry = (industry or "").strip() or "their industry"
    title = (title or "").strip() or "the team"
    return (
        f"{company} operates in {industry}. This lead ({title}) is being contacted for outbound automation and "
        f"AI-assisted workflows that improve prospecting, follow-ups, and sales operations efficiency."
    )


def _ensure_dict(v: Any) -> Dict[str, Any]:
    if v is None:
        return {}
    if isinstance(v, dict):
        return v
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return {}
        try:
            import json
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


# ✅ Stronger extractor (fixes “has_result=false” due to response shape mismatch)
def _extract_markdown_text(scraped: Any) -> str:
    if not scraped:
        return ""

    if isinstance(scraped, str):
        return scraped

    if isinstance(scraped, dict):
        # direct
        if isinstance(scraped.get("markdown"), str) and scraped.get("markdown"):
            return scraped["markdown"]

        # nested dict
        data = scraped.get("data")
        if isinstance(data, dict):
            if isinstance(data.get("markdown"), str) and data.get("markdown"):
                return data["markdown"]

        # nested list (common!)
        if isinstance(data, list) and data:
            first = data[0]
            if isinstance(first, dict):
                if isinstance(first.get("markdown"), str) and first.get("markdown"):
                    return first["markdown"]
                for k in ("content", "text", "body"):
                    if isinstance(first.get(k), str) and first.get(k):
                        return first[k]

        # other fallbacks
        for k in ("content", "text", "body"):
            if isinstance(scraped.get(k), str) and scraped.get(k):
                return scraped[k]

    return ""


def _firecrawl_enrich_company_description(db: Session, lead: Lead) -> Dict[str, Any]:
    """
    Runs Firecrawl scrape for lead.company_website.
    - Saves raw result to iip_data["firecrawl"]
    - Saves errors to iip_data["firecrawl_error"]
    - Only replaces company_description if empty/placeholder/unknown
    - Never overwrites manual descriptions
    Returns debug dict for API visibility.
    """
    company_website = (getattr(lead, "company_website", None) or "").strip()
    out: Dict[str, Any] = {
        "lead_id": lead.id,
        "company_website": company_website,
        "enabled": False,
        "has_result": False,
        "company_description_source": None,
        "company_description_preview": None,
        "firecrawl_error": None,
    }

    if not company_website:
        return out

    svc = FirecrawlService()
    out["enabled"] = svc.is_enabled()
    if not svc.is_enabled():
        return out

    iip = _ensure_dict(getattr(lead, "iip_data", None))
    existing_desc = (iip.get("company_description") or "").strip()
    source = (iip.get("company_description_source") or "").strip().lower()

    out["company_description_source"] = source or None
    out["company_description_preview"] = (existing_desc[:200] + "...") if existing_desc and len(existing_desc) > 200 else existing_desc

    # Never overwrite manual description
    if existing_desc and source == "manual":
        out["has_result"] = False
        return out

    try:
        scraped = svc.scrape_markdown(company_website, timeout_ms=20000)

        # Always store raw scrape (even if markdown extraction fails)
        iip["firecrawl"] = {
            "company_website": company_website,
            "result": scraped or {},
        }

        md = _compact_text(_extract_markdown_text(scraped), limit=4500)

        if md:
            out["has_result"] = True

            # Only set description if empty or placeholder/unknown
            if (not existing_desc) or (source in ("placeholder", "", "unknown")):
                iip["company_description"] = md
                iip["company_description_source"] = "firecrawl"
                out["company_description_source"] = "firecrawl"
                out["company_description_preview"] = md[:200] + "..." if len(md) > 200 else md

        lead.iip_data = iip
        db.add(lead)
        db.commit()
        db.refresh(lead)

        return out

    except Exception as e:
        # Save error into iip_data so you can see it later
        iip["firecrawl_error"] = str(e)
        lead.iip_data = iip
        db.add(lead)
        db.commit()
        db.refresh(lead)

        out["firecrawl_error"] = str(e)
        app_logger.error(f"Firecrawl enrichment failed lead_id={lead.id} website={company_website}: {e}")
        return out


# -----------------------------
# Background packet generation
# -----------------------------
def _run_async(coro):
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

        # ✅ Firecrawl BEFORE packet creation
        _firecrawl_enrich_company_description(db, lead)

        agent = DataPacketAgent(db)
        _run_async(agent.create_data_packet(lead))

        logger.info("✅ Data packet created for lead_id=%s", lead_id)

    except Exception as e:
        logger.exception("❌ Data packet generation failed for lead_id=%s: %s", lead_id, e)
        try:
            lead = db.query(Lead).filter(Lead.id == lead_id).first()
            if lead:
                current = _ensure_dict(getattr(lead, "iip_data", None))
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

            _firecrawl_enrich_company_description(db, lead)
            _run_async(agent.create_data_packet(lead))

    except Exception as e:
        logger.exception("Background packet generation error: %s", e)
    finally:
        db.close()


# -----------------------------
# Schemas
# -----------------------------
class ManualLeadCreate(BaseModel):
    phone_number: str
    company_name: str
    contact_name: str
    email: str
    title: str

    company_description: Optional[str] = None
    industry: Optional[str] = None
    company_website: Optional[str] = None


# -----------------------------
# List Leads Endpoint (NEW)
# -----------------------------
@router.get("")
@router.get("/")
async def list_leads(
    skip: int = 0,
    limit: int = 100,
    status: Optional[str] = None,
    current_user: UserInDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    List all leads with pagination.
    Requires authentication.
    """
    # Enforce pagination limit
    limit = min(limit, MAX_PAGINATION_LIMIT)

    q = db.query(Lead)
    if status:
        q = q.filter(Lead.status == status)

    leads = q.order_by(Lead.created_at.desc()).offset(skip).limit(limit).all()
    return [lead_to_dict(lead) for lead in leads]


@router.post("/manual")
async def create_manual_lead(
    payload: ManualLeadCreate,
    background_tasks: BackgroundTasks,
    current_user: UserInDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        phone = (payload.phone_number or "").strip()
        company = (payload.company_name or "").strip()
        name = (payload.contact_name or "").strip()
        email = (payload.email or "").strip()
        title = (payload.title or "").strip()

        industry = normalize_industry(payload.industry)
        company_description = (payload.company_description or "").strip() or None
        company_website = (payload.company_website or "").strip() or None

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

        lead = db.query(Lead).filter(Lead.email == email).first()
        created_now = False

        if not lead:
            lead = Lead(
                name=name,
                email=email,
                phone=phone,
                company=company,
                title=title,
                company_industry=industry,
                status="cold",
                source="manual_upload",
            )
            created_now = True
        else:
            lead.name = name or lead.name
            lead.phone = phone or lead.phone
            lead.company = company or lead.company
            lead.title = title or lead.title
            lead.company_industry = industry or lead.company_industry

        if company_website:
            lead.company_website = company_website

        current = _ensure_dict(getattr(lead, "iip_data", None))
        if company_description:
            current["company_description"] = company_description
            current["company_description_source"] = "manual"
        else:
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

        # background generation (firecrawl runs inside)
        background_tasks.add_task(_generate_one_packet_background, lead.id)

        return {"status": "success", "lead": lead_to_dict(lead)}

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Manual lead create failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ✅ Debug endpoint to run Firecrawl and view outcome immediately
@router.get("/{lead_id}/firecrawl")
async def debug_firecrawl(
    lead_id: int,
    current_user: UserInDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    debug = _firecrawl_enrich_company_description(db, lead)
    iip = _ensure_dict(getattr(lead, "iip_data", None))

    return {
        **debug,
        "firecrawl": iip.get("firecrawl") or {},
        "firecrawl_error": iip.get("firecrawl_error"),
    }


@router.get("/{lead_id}/data-packet")
async def get_or_create_lead_data_packet(
    lead_id: int,
    current_user: UserInDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    existing = db.query(DataPacket).filter(DataPacket.lead_id == lead_id).first()
    if existing:
        return packet_to_dict(existing)

    # before creating packet, enrich
    _firecrawl_enrich_company_description(db, lead)

    agent = DataPacketAgent(db)
    packet = await agent.create_data_packet(lead)
    return packet_to_dict(packet)


@router.get("/{lead_id}")
async def get_lead(
    lead_id: int,
    current_user: UserInDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead_to_dict(lead)


# ================= Enhanced Company Scraping =================

@router.post("/{lead_id}/scrape-company")
async def scrape_company_comprehensive(
    lead_id: int,
    background_tasks: BackgroundTasks,
    current_user: UserInDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Triggers comprehensive company web scraping for a lead.

    Extracts:
    - Company overview/description
    - Services offered
    - Products
    - Industry/sector
    - Contact information
    - Key differentiators
    - Target customers
    - And more...

    Results are stored in the lead's scraped_* fields.
    """
    from datetime import datetime
    from app.services.company_scraper_service import CompanyScraperService

    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    company_website = (getattr(lead, "company_website", None) or "").strip()
    if not company_website:
        raise HTTPException(
            status_code=400,
            detail="Lead has no company_website. Add a website URL first."
        )

    scraper = CompanyScraperService()
    if not scraper.is_enabled():
        raise HTTPException(
            status_code=503,
            detail="Company scraping service not available. Check FIRECRAWL_API_KEY."
        )

    # Run the comprehensive scrape
    result = await scraper.scrape_company(
        company_url=company_website,
        company_name=lead.company or "",
    )

    # Update lead with scraped data
    lead.scraped_company_overview = result.company_overview or None
    lead.scraped_services = result.services if result.services else None
    lead.scraped_products = result.products if result.products else None
    lead.scraped_industry = result.industry or None
    lead.scraped_sector = result.sector or None
    lead.scraped_contact_email = result.contact_email or None
    lead.scraped_contact_phone = result.contact_phone or None
    lead.scraped_headquarters = result.headquarters_location or None
    lead.scraped_founded_year = result.founded_year or None
    lead.scraped_company_size = result.company_size or None
    lead.scraped_key_differentiators = result.key_differentiators if result.key_differentiators else None
    lead.scraped_target_customers = result.target_customers or None
    lead.scraped_technology_stack = result.technology_stack if result.technology_stack else None
    lead.scraped_certifications = result.certifications if result.certifications else None
    lead.scraped_partnerships = result.partnerships if result.partnerships else None
    lead.scrape_confidence_score = result.confidence_score
    lead.scrape_success = result.scrape_success
    lead.scrape_errors = result.scrape_errors if result.scrape_errors else None
    lead.scrape_sources = result.sources_scraped if result.sources_scraped else None
    lead.scraped_at = datetime.utcnow()

    # Store raw markdown for reference (truncated if too large)
    if result.raw_markdown:
        lead.scraped_raw_markdown = result.raw_markdown[:50000] if len(result.raw_markdown) > 50000 else result.raw_markdown

    # Also update company_industry if we got better data
    if result.industry and not lead.company_industry:
        lead.company_industry = result.industry

    db.commit()
    db.refresh(lead)

    # Broadcast scrape completion
    await broadcast_activity({
        "type": "company_scraped",
        "lead_id": lead.id,
        "company": lead.company,
        "success": result.scrape_success,
        "confidence": result.confidence_score,
    })

    return {
        "status": "success" if result.scrape_success else "partial",
        "lead_id": lead.id,
        "company": lead.company,
        "website": company_website,
        "scrape_success": result.scrape_success,
        "confidence_score": result.confidence_score,
        "sources_scraped": result.sources_scraped,
        "errors": result.scrape_errors,
        "data": {
            "company_overview": result.company_overview[:500] + "..." if result.company_overview and len(result.company_overview) > 500 else result.company_overview,
            "industry": result.industry,
            "sector": result.sector,
            "services_count": len(result.services) if result.services else 0,
            "products_count": len(result.products) if result.products else 0,
            "contact_email": result.contact_email,
            "contact_phone": result.contact_phone,
        }
    }


@router.get("/{lead_id}/scraped-data")
async def get_lead_scraped_data(
    lead_id: int,
    current_user: UserInDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Returns all scraped company data for a lead.
    """
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    return {
        "lead_id": lead.id,
        "company": lead.company,
        "company_website": lead.company_website,
        "scrape_success": getattr(lead, "scrape_success", False),
        "scrape_confidence": getattr(lead, "scrape_confidence_score", 0.0),
        "scraped_at": lead.scraped_at.isoformat() if getattr(lead, "scraped_at", None) else None,
        "scrape_sources": getattr(lead, "scrape_sources", []),
        "scrape_errors": getattr(lead, "scrape_errors", []),
        "data": {
            "company_overview": getattr(lead, "scraped_company_overview", None),
            "services": getattr(lead, "scraped_services", []),
            "products": getattr(lead, "scraped_products", []),
            "industry": getattr(lead, "scraped_industry", None),
            "sector": getattr(lead, "scraped_sector", None),
            "contact_email": getattr(lead, "scraped_contact_email", None),
            "contact_phone": getattr(lead, "scraped_contact_phone", None),
            "headquarters": getattr(lead, "scraped_headquarters", None),
            "founded_year": getattr(lead, "scraped_founded_year", None),
            "company_size": getattr(lead, "scraped_company_size", None),
            "key_differentiators": getattr(lead, "scraped_key_differentiators", []),
            "target_customers": getattr(lead, "scraped_target_customers", None),
            "technology_stack": getattr(lead, "scraped_technology_stack", []),
            "certifications": getattr(lead, "scraped_certifications", []),
            "partnerships": getattr(lead, "scraped_partnerships", []),
        }
    }


# ================= Playwright-based Web Scraping =================

@router.post("/{lead_id}/scrape-playwright")
async def scrape_company_with_playwright(
    lead_id: int,
    current_user: UserInDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Triggers comprehensive company web scraping using Playwright.

    Playwright handles:
    - JavaScript-rendered content
    - Dynamic pages
    - Single-page applications
    - Content behind basic JavaScript loading

    Extracts:
    - Company overview/description
    - Services offered
    - Products
    - Industry/sector
    - Contact information
    - Key differentiators
    - Target customers
    - Social media links
    - And more...

    Results are stored in the lead's scraped_* fields.
    """
    from datetime import datetime
    from app.services.playwright_scraper_service import PlaywrightScraperService

    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    company_website = (getattr(lead, "company_website", None) or "").strip()
    if not company_website:
        raise HTTPException(
            status_code=400,
            detail="Lead has no company_website. Add a website URL first."
        )

    scraper = PlaywrightScraperService()
    if not scraper.is_enabled():
        raise HTTPException(
            status_code=503,
            detail="Playwright scraping not available. Install with: pip install playwright && playwright install chromium"
        )

    # Run the comprehensive Playwright scrape
    result = await scraper.scrape_company(
        company_url=company_website,
        company_name=lead.company or "",
    )

    # Update lead with scraped data
    lead.scraped_company_overview = result.company_overview or None
    lead.scraped_services = result.services if result.services else None
    lead.scraped_products = result.products if result.products else None
    lead.scraped_industry = result.industry or None
    lead.scraped_sector = result.sector or None
    lead.scraped_contact_email = result.contact_email or None
    lead.scraped_contact_phone = result.contact_phone or None
    lead.scraped_headquarters = result.headquarters_location or None
    lead.scraped_founded_year = result.founded_year or None
    lead.scraped_company_size = result.company_size or None
    lead.scraped_key_differentiators = result.key_differentiators if result.key_differentiators else None
    lead.scraped_target_customers = result.target_customers or None
    lead.scraped_technology_stack = result.technology_stack if result.technology_stack else None
    lead.scraped_certifications = result.certifications if result.certifications else None
    lead.scraped_partnerships = result.partnerships if result.partnerships else None
    lead.scrape_confidence_score = result.confidence_score
    lead.scrape_success = result.scrape_success
    lead.scrape_errors = result.scrape_errors if result.scrape_errors else None
    lead.scrape_sources = result.sources_scraped if result.sources_scraped else None
    lead.scraped_at = datetime.utcnow()

    # Store raw text for reference (truncated)
    if result.raw_text:
        lead.scraped_raw_markdown = result.raw_text[:50000] if len(result.raw_text) > 50000 else result.raw_text

    # Update company_industry if we got better data
    if result.industry and not lead.company_industry:
        lead.company_industry = result.industry

    db.commit()
    db.refresh(lead)

    # Broadcast scrape completion
    await broadcast_activity({
        "type": "company_scraped_playwright",
        "lead_id": lead.id,
        "company": lead.company,
        "success": result.scrape_success,
        "confidence": result.confidence_score,
        "duration_ms": result.scrape_duration_ms,
    })

    return {
        "status": "success" if result.scrape_success else "partial",
        "scraper": "playwright",
        "lead_id": lead.id,
        "company": lead.company,
        "website": company_website,
        "scrape_success": result.scrape_success,
        "confidence_score": result.confidence_score,
        "duration_ms": result.scrape_duration_ms,
        "sources_scraped": result.sources_scraped,
        "errors": result.scrape_errors,
        "social_links": result.social_links,
        "data": {
            "company_overview": result.company_overview[:500] + "..." if result.company_overview and len(result.company_overview) > 500 else result.company_overview,
            "industry": result.industry,
            "sector": result.sector,
            "services_count": len(result.services) if result.services else 0,
            "products_count": len(result.products) if result.products else 0,
            "contact_email": result.contact_email,
            "contact_phone": result.contact_phone,
        }
    }


# ================= Email Unsubscribe (CAN-SPAM Compliance) =================

def _get_unsubscribe_secret() -> str:
    """Get the secret for unsubscribe token generation."""
    # Try dedicated unsubscribe secret first, then JWT secret, then generate a random one
    secret = getattr(settings, "UNSUBSCRIBE_SECRET", None)
    if secret:
        return secret
    secret = getattr(settings, "JWT_SECRET_KEY", None)
    if secret:
        return secret
    # This should never happen in production - log warning
    logger.warning("No UNSUBSCRIBE_SECRET or JWT_SECRET_KEY configured - using random secret (tokens will break on restart)")
    return secrets.token_urlsafe(32)

def _verify_unsubscribe_token(lead_id: int, email: str, token: str) -> bool:
    """Verify the unsubscribe token is valid using constant-time comparison."""
    secret = _get_unsubscribe_secret()
    expected_token = hashlib.sha256(f"{lead_id}:{email}:{secret}".encode()).hexdigest()[:32]
    # Use constant-time comparison to prevent timing attacks
    return secrets.compare_digest(token, expected_token)


@router.get("/unsubscribe", response_class=HTMLResponse)
async def unsubscribe_lead(
    lead_id: int = Query(..., description="Lead ID to unsubscribe"),
    token: str = Query(..., description="Security token"),
    db: Session = Depends(get_db),
):
    """
    Handle email unsubscribe requests (CAN-SPAM compliance).

    This endpoint is linked from all marketing emails. When clicked:
    1. Verifies the token to prevent URL tampering
    2. Marks the lead as unsubscribed
    3. Shows a confirmation page

    Per CAN-SPAM: Must honor unsubscribe within 10 business days.
    We honor it immediately.
    """
    lead = db.query(Lead).filter(Lead.id == lead_id).first()

    if not lead:
        return HTMLResponse(
            content=_unsubscribe_error_page("Lead not found"),
            status_code=404
        )

    # Verify token
    if not _verify_unsubscribe_token(lead_id, lead.email, token):
        return HTMLResponse(
            content=_unsubscribe_error_page("Invalid unsubscribe link"),
            status_code=403
        )

    # Check if already unsubscribed
    if lead.unsubscribed_at:
        return HTMLResponse(
            content=_unsubscribe_success_page(lead.email, already_unsubscribed=True),
            status_code=200
        )

    # Mark as unsubscribed
    lead.unsubscribed_at = datetime.utcnow()
    db.commit()

    logger.info(f"Lead {lead_id} ({lead.email}) unsubscribed from emails")

    # Broadcast activity
    await broadcast_activity({
        "type": "lead_unsubscribed",
        "lead_id": lead.id,
        "email": lead.email,
        "message": f"{lead.email} unsubscribed from emails"
    })

    return HTMLResponse(
        content=_unsubscribe_success_page(lead.email),
        status_code=200
    )


@router.post("/{lead_id}/resubscribe")
async def resubscribe_lead(
    lead_id: int,
    current_user: UserInDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Re-subscribe a lead to emails (admin action).

    Only to be used when a lead explicitly asks to receive emails again.
    """
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    if not lead.unsubscribed_at:
        return {"status": "already_subscribed", "lead_id": lead_id}

    lead.unsubscribed_at = None
    db.commit()

    logger.info(f"Lead {lead_id} ({lead.email}) re-subscribed to emails")

    return {"status": "resubscribed", "lead_id": lead_id, "email": lead.email}


def _unsubscribe_success_page(email: str, already_unsubscribed: bool = False) -> str:
    """Generate HTML page for successful unsubscribe."""
    message = "You were already unsubscribed." if already_unsubscribed else "You have been unsubscribed."
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Unsubscribed - Algonox</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            background-color: #f4f4f4;
            margin: 0;
            padding: 40px 20px;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 80vh;
        }}
        .container {{
            background: white;
            border-radius: 12px;
            padding: 40px;
            max-width: 500px;
            text-align: center;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        .logo {{
            font-size: 28px;
            font-weight: 700;
            margin-bottom: 30px;
        }}
        .logo-accent {{
            color: #41FFFF;
        }}
        .icon {{
            font-size: 48px;
            margin-bottom: 20px;
        }}
        h1 {{
            color: #333;
            font-size: 24px;
            margin-bottom: 10px;
        }}
        p {{
            color: #666;
            line-height: 1.6;
        }}
        .email {{
            color: #333;
            font-weight: 500;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="logo">Algo<span class="logo-accent">nox</span></div>
        <div class="icon">✓</div>
        <h1>Unsubscribed</h1>
        <p>{message}</p>
        <p>You will no longer receive marketing emails at:<br><span class="email">{email}</span></p>
        <p style="margin-top: 30px; font-size: 14px; color: #999;">
            If you unsubscribed by mistake, please contact us.
        </p>
    </div>
</body>
</html>"""


def _unsubscribe_error_page(error: str) -> str:
    """Generate HTML page for unsubscribe errors."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Unsubscribe Error - Algonox</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            background-color: #f4f4f4;
            margin: 0;
            padding: 40px 20px;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 80vh;
        }}
        .container {{
            background: white;
            border-radius: 12px;
            padding: 40px;
            max-width: 500px;
            text-align: center;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        .logo {{
            font-size: 28px;
            font-weight: 700;
            margin-bottom: 30px;
        }}
        .logo-accent {{
            color: #41FFFF;
        }}
        .icon {{
            font-size: 48px;
            margin-bottom: 20px;
            color: #e74c3c;
        }}
        h1 {{
            color: #333;
            font-size: 24px;
            margin-bottom: 10px;
        }}
        p {{
            color: #666;
            line-height: 1.6;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="logo">Algo<span class="logo-accent">nox</span></div>
        <div class="icon">✗</div>
        <h1>Unsubscribe Error</h1>
        <p>{error}</p>
        <p style="margin-top: 30px; font-size: 14px; color: #999;">
            If you continue to receive unwanted emails, please contact us directly.
        </p>
    </div>
</body>
</html>"""
