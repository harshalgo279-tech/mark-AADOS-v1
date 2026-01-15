from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta
import io
import csv
import logging

from app.database import get_db
from app.models.lead import Lead
from app.models.call import Call
from app.models.email import Email
from app.models.data_packet import DataPacket

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/reports",   # ✅ CHANGED HERE
    tags=["reports"]
)


@router.get("/dashboard")
async def dashboard(db: Session = Depends(get_db)):
    try:
        total_leads = db.query(func.count(Lead.id)).scalar() or 0
        data_packets_created = db.query(func.count(DataPacket.id)).scalar() or 0
        calls_total = db.query(func.count(Call.id)).scalar() or 0
        emails_sent = db.query(func.count(Email.id)).scalar() or 0

        return {
            "leads": {"total": total_leads, "data_packets_created": data_packets_created},
            "calls": {"total": calls_total},
            "emails": {"sent": emails_sent},
        }
    except Exception as e:
        logger.error(f"Dashboard error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/funnel")
async def funnel(db: Session = Depends(get_db)):
    try:
        total_leads = db.query(func.count(Lead.id)).scalar() or 0
        packets = db.query(func.count(DataPacket.id)).scalar() or 0
        calls = db.query(func.count(Call.id)).scalar() or 0
        positive = db.query(func.count(Call.id)).filter(Call.sentiment.in_(["positive", "interested"])).scalar() or 0

        return {
            "stages": [
                {"name": "Total Leads", "value": total_leads},
                {"name": "Data Packets", "value": packets},
                {"name": "Calls Made", "value": calls},
                {"name": "Positive Outcome", "value": positive},
            ]
        }
    except Exception as e:
        logger.error(f"Funnel error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/performance")
async def performance(days: int = 30, db: Session = Depends(get_db)):
    try:
        start_date = datetime.utcnow() - timedelta(days=days)

        lead_rows = (
            db.query(func.date(Lead.created_at), func.count(Lead.id))
            .filter(Lead.created_at >= start_date)
            .group_by(func.date(Lead.created_at))
            .all()
        )

        call_rows = (
            db.query(func.date(Call.created_at), func.count(Call.id))
            .filter(Call.created_at >= start_date)
            .group_by(func.date(Call.created_at))
            .all()
        )

        return {
            "leads": [{"date": str(d), "count": c} for d, c in lead_rows],
            "calls": [{"date": str(d), "count": c} for d, c in call_rows],
        }
    except Exception as e:
        logger.error(f"Performance error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/export/leads")
async def export_leads(db: Session = Depends(get_db)):
    try:
        leads = db.query(Lead).all()
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["id", "name", "email", "phone", "company", "title", "created_at"])

        for l in leads:
            writer.writerow([
                l.id, l.name, l.email, l.phone, l.company, l.title,
                l.created_at.isoformat() if l.created_at else ""
            ])

        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=leads.csv"},
        )
    except Exception as e:
        logger.error(f"Export error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))



