# backend/app/api/emails.py
"""
Email API endpoints for:
- Open tracking (pixel)
- Click tracking (redirect)
- Email management
- Analytics
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import unquote

from fastapi import APIRouter, Depends, HTTPException, Query, Path
from fastapi.responses import RedirectResponse, Response
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.email import Email
from app.models.lead import Lead
from app.services.email_service import EmailService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/emails", tags=["emails"])

# 1x1 transparent GIF for tracking pixel
TRACKING_PIXEL = bytes([
    0x47, 0x49, 0x46, 0x38, 0x39, 0x61, 0x01, 0x00,
    0x01, 0x00, 0x80, 0x00, 0x00, 0xff, 0xff, 0xff,
    0x00, 0x00, 0x00, 0x21, 0xf9, 0x04, 0x01, 0x00,
    0x00, 0x00, 0x00, 0x2c, 0x00, 0x00, 0x00, 0x00,
    0x01, 0x00, 0x01, 0x00, 0x00, 0x02, 0x02, 0x44,
    0x01, 0x00, 0x3b
])


# ==================== Tracking Endpoints ====================

@router.get("/track/open/{tracking_id}")
async def track_email_open(
    tracking_id: str = Path(..., description="Email tracking ID"),
    db: Session = Depends(get_db),
):
    """
    Track email opens via invisible pixel.

    When an email client loads images, this endpoint is hit,
    recording the open time.

    Note: Many email clients block images by default or use
    proxy loading, so open tracking is not 100% accurate.
    """
    # Find email by tracking ID
    email = db.query(Email).filter(Email.tracking_id == tracking_id).first()

    if email and not email.opened_at:
        email.opened_at = datetime.utcnow()
        db.commit()
        logger.info(f"Email {email.id} opened (tracking_id={tracking_id})")

    # Always return the tracking pixel, even if email not found
    return Response(
        content=TRACKING_PIXEL,
        media_type="image/gif",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        }
    )


@router.get("/track/click/{tracking_id}")
async def track_email_click(
    tracking_id: str = Path(..., description="Email tracking ID"),
    url: str = Query(..., description="Original URL to redirect to"),
    db: Session = Depends(get_db),
):
    """
    Track email link clicks via redirect.

    All links in emails are rewritten to go through this endpoint,
    which records the click and redirects to the original URL.
    """
    # Decode URL
    original_url = unquote(url)

    # Validate URL (basic security check)
    if not original_url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="Invalid URL")

    # Find email and record click
    email = db.query(Email).filter(Email.tracking_id == tracking_id).first()

    if email and not email.clicked_at:
        email.clicked_at = datetime.utcnow()
        # Also mark as opened if not already
        if not email.opened_at:
            email.opened_at = datetime.utcnow()
        db.commit()
        logger.info(f"Email {email.id} clicked (tracking_id={tracking_id}, url={original_url[:50]})")

    # Redirect to original URL
    return RedirectResponse(url=original_url, status_code=302)


# ==================== Email Management Endpoints ====================

@router.get("/{email_id}")
async def get_email(
    email_id: int,
    db: Session = Depends(get_db),
):
    """Get a single email by ID."""
    email = db.query(Email).filter(Email.id == email_id).first()
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")

    return _email_to_dict(email)


@router.get("/lead/{lead_id}")
async def get_emails_for_lead(
    lead_id: int,
    db: Session = Depends(get_db),
):
    """Get all emails for a specific lead."""
    # Verify lead exists
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    emails = db.query(Email).filter(Email.lead_id == lead_id).order_by(Email.created_at.desc()).all()

    return {
        "lead_id": lead_id,
        "lead_email": lead.email,
        "lead_unsubscribed": lead.unsubscribed_at is not None,
        "emails": [_email_to_dict(e) for e in emails]
    }


class EmailUpdateRequest(BaseModel):
    subject: Optional[str] = None
    body_html: Optional[str] = None
    body_text: Optional[str] = None
    preview_text: Optional[str] = None


@router.patch("/{email_id}")
async def update_email(
    email_id: int,
    update: EmailUpdateRequest,
    db: Session = Depends(get_db),
):
    """
    Update an email before sending.

    Only draft/pending emails can be edited.
    """
    email = db.query(Email).filter(Email.id == email_id).first()
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")

    if email.status not in ("draft", "pending"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot edit email with status '{email.status}'. Only draft/pending emails can be edited."
        )

    # Update fields
    if update.subject is not None:
        email.subject = update.subject
    if update.body_html is not None:
        email.body_html = update.body_html
    if update.body_text is not None:
        email.body_text = update.body_text
    if update.preview_text is not None:
        email.preview_text = update.preview_text

    db.commit()
    db.refresh(email)

    logger.info(f"Email {email_id} updated")

    return _email_to_dict(email)


@router.put("/{email_id}")
async def update_email_put(
    email_id: int,
    update: EmailUpdateRequest,
    db: Session = Depends(get_db),
):
    """
    Update an email before sending (PUT version for frontend compatibility).

    Only draft/pending emails can be edited.
    """
    email = db.query(Email).filter(Email.id == email_id).first()
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")

    if email.status not in ("draft", "pending", "failed"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot edit email with status '{email.status}'. Only draft/pending/failed emails can be edited."
        )

    # Update fields
    if update.subject is not None:
        email.subject = update.subject
    if update.body_html is not None:
        email.body_html = update.body_html
    if update.body_text is not None:
        email.body_text = update.body_text
    if update.preview_text is not None:
        email.preview_text = update.preview_text

    db.commit()
    db.refresh(email)

    logger.info(f"Email {email_id} updated (PUT)")

    return _email_to_dict(email)


@router.post("/{email_id}/send")
async def send_email(
    email_id: int,
    db: Session = Depends(get_db),
):
    """
    Send a draft email immediately.
    """
    from app.agents.email_agent import EmailAgent

    agent = EmailAgent(db)
    result = await agent.send_email_by_id(email_id)

    if not result.get("success"):
        if result.get("blocked"):
            raise HTTPException(status_code=403, detail=result.get("error"))
        raise HTTPException(status_code=400, detail=result.get("error"))

    return result


@router.delete("/{email_id}")
async def delete_email(
    email_id: int,
    db: Session = Depends(get_db),
):
    """
    Delete an email.

    Only draft/pending/failed emails can be deleted.
    """
    email = db.query(Email).filter(Email.id == email_id).first()
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")

    if email.status == "sent":
        raise HTTPException(
            status_code=400,
            detail="Cannot delete sent emails."
        )

    db.delete(email)
    db.commit()

    logger.info(f"Email {email_id} deleted")

    return {"status": "deleted", "email_id": email_id}


# ==================== Analytics Endpoints ====================

@router.get("/analytics/summary")
async def get_email_analytics_summary(
    days: int = Query(30, ge=1, le=365, description="Number of days to analyze"),
    db: Session = Depends(get_db),
):
    """
    Get email analytics summary for the specified period.
    """
    since = datetime.utcnow() - timedelta(days=days)

    # Total counts
    total_sent = db.query(func.count(Email.id)).filter(
        Email.sent_at >= since,
        Email.status == "sent"
    ).scalar() or 0

    total_opened = db.query(func.count(Email.id)).filter(
        Email.sent_at >= since,
        Email.opened_at.isnot(None)
    ).scalar() or 0

    total_clicked = db.query(func.count(Email.id)).filter(
        Email.sent_at >= since,
        Email.clicked_at.isnot(None)
    ).scalar() or 0

    total_bounced = db.query(func.count(Email.id)).filter(
        Email.sent_at >= since,
        Email.bounced_at.isnot(None)
    ).scalar() or 0

    total_failed = db.query(func.count(Email.id)).filter(
        Email.created_at >= since,
        Email.status == "failed"
    ).scalar() or 0

    # Calculate rates
    open_rate = (total_opened / total_sent * 100) if total_sent > 0 else 0
    click_rate = (total_clicked / total_sent * 100) if total_sent > 0 else 0
    bounce_rate = (total_bounced / total_sent * 100) if total_sent > 0 else 0

    # By email type
    by_type = db.query(
        Email.email_type,
        func.count(Email.id).label("sent"),
        func.sum(func.if_(Email.opened_at.isnot(None), 1, 0)).label("opened"),
        func.sum(func.if_(Email.clicked_at.isnot(None), 1, 0)).label("clicked"),
    ).filter(
        Email.sent_at >= since,
        Email.status == "sent"
    ).group_by(Email.email_type).all()

    type_stats = []
    for row in by_type:
        sent = row.sent or 0
        opened = row.opened or 0
        clicked = row.clicked or 0
        type_stats.append({
            "email_type": row.email_type,
            "sent": sent,
            "opened": opened,
            "clicked": clicked,
            "open_rate": round(opened / sent * 100, 1) if sent > 0 else 0,
            "click_rate": round(clicked / sent * 100, 1) if sent > 0 else 0,
        })

    return {
        "period_days": days,
        "summary": {
            "total_sent": total_sent,
            "total_opened": total_opened,
            "total_clicked": total_clicked,
            "total_bounced": total_bounced,
            "total_failed": total_failed,
            "open_rate": round(open_rate, 1),
            "click_rate": round(click_rate, 1),
            "bounce_rate": round(bounce_rate, 1),
        },
        "by_email_type": type_stats,
    }


@router.get("/throttle/status")
async def get_throttle_status():
    """Get current email throttling status."""
    service = EmailService()
    return await service.get_throttle_status()


@router.get("/scheduler/status")
async def get_scheduler_status():
    """Get email scheduler status."""
    from app.services.email_scheduler import get_scheduler_status
    return get_scheduler_status()


@router.post("/schedule/{call_id}")
async def schedule_followup_emails(
    call_id: int,
    db: Session = Depends(get_db),
):
    """
    Schedule follow-up emails for a call.

    This sets the scheduled_for time on follow-up emails
    based on the configured delays (3 days for follow_up_1,
    8 days for follow_up_2).
    """
    from app.services.email_scheduler import schedule_followup_emails as do_schedule

    count = do_schedule(db, call_id)

    return {
        "status": "scheduled",
        "call_id": call_id,
        "emails_scheduled": count,
    }


@router.post("/cancel/{lead_id}")
async def cancel_scheduled_emails(
    lead_id: int,
    reason: str = Query("cancelled", description="Cancellation reason"),
    db: Session = Depends(get_db),
):
    """
    Cancel all scheduled emails for a lead.

    Use when:
    - Lead unsubscribes
    - Lead books a demo
    - Lead replies to an email
    """
    from app.services.email_scheduler import cancel_scheduled_emails as do_cancel

    count = do_cancel(db, lead_id, reason)

    return {
        "status": "cancelled",
        "lead_id": lead_id,
        "emails_cancelled": count,
    }


# ==================== Helper Functions ====================

def _email_to_dict(email: Email) -> dict:
    """Convert Email model to dictionary."""
    return {
        "id": email.id,
        "lead_id": email.lead_id,
        "call_id": email.call_id,
        "subject": email.subject,
        "body_html": email.body_html,
        "body_text": email.body_text,
        "preview_text": email.preview_text,
        "email_type": email.email_type,
        "tracking_id": email.tracking_id,
        "scheduled_for": email.scheduled_for.isoformat() if email.scheduled_for else None,
        "sent_at": email.sent_at.isoformat() if email.sent_at else None,
        "delivered_at": email.delivered_at.isoformat() if email.delivered_at else None,
        "opened_at": email.opened_at.isoformat() if email.opened_at else None,
        "clicked_at": email.clicked_at.isoformat() if email.clicked_at else None,
        "replied_at": email.replied_at.isoformat() if email.replied_at else None,
        "bounced_at": email.bounced_at.isoformat() if email.bounced_at else None,
        "status": email.status,
        "error_message": email.error_message,
        "error_category": email.error_category,
        "retry_count": email.retry_count,
        "created_at": email.created_at.isoformat() if email.created_at else None,
    }
