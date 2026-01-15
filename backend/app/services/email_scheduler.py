# backend/app/services/email_scheduler.py
"""
Email Scheduler Service
=======================

Background service that:
1. Sends scheduled emails when their time arrives
2. Schedules follow-up emails with configurable delays
3. Respects lead unsubscribe status and email throttling

Usage:
    - Start scheduler with: asyncio.create_task(start_email_scheduler())
    - Stop scheduler with: stop_email_scheduler()
    - Schedule emails with: schedule_followup_emails(db, call_id)
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.email import Email
from app.models.lead import Lead
from app.services.email_service import EmailService, generate_tracking_id
from app.utils.logger import logger


# =============================================================================
# Configuration
# =============================================================================

# Delay between sequence emails (in days)
SEQUENCE_DELAYS = {
    "follow_up_1": 3,  # 3 days after primary email
    "follow_up_2": 5,  # 5 days after follow_up_1 (8 total)
}

# How often to check for scheduled emails (seconds)
SCHEDULER_CHECK_INTERVAL = 60  # 1 minute

# Global scheduler state
_scheduler_task: Optional[asyncio.Task] = None
_scheduler_running = False


# =============================================================================
# Scheduler Control
# =============================================================================

async def start_email_scheduler():
    """
    Start the background email scheduler.
    Should be called once on application startup.
    """
    global _scheduler_task, _scheduler_running

    if _scheduler_running:
        logger.warning("Email scheduler already running")
        return

    _scheduler_running = True
    _scheduler_task = asyncio.create_task(_scheduler_loop())
    logger.info("Email scheduler started")


def stop_email_scheduler():
    """
    Stop the background email scheduler.
    Should be called on application shutdown.
    """
    global _scheduler_task, _scheduler_running

    _scheduler_running = False
    if _scheduler_task and not _scheduler_task.done():
        _scheduler_task.cancel()
        logger.info("Email scheduler stopped")


async def _scheduler_loop():
    """
    Main scheduler loop. Checks for and sends scheduled emails.
    """
    email_service = EmailService()

    while _scheduler_running:
        try:
            await _process_scheduled_emails(email_service)
        except Exception as e:
            logger.error(f"Email scheduler error: {e}")

        # Wait before next check
        await asyncio.sleep(SCHEDULER_CHECK_INTERVAL)


async def _process_scheduled_emails(email_service: EmailService):
    """
    Find and send all emails whose scheduled_for time has passed.
    """
    db: Session = SessionLocal()

    try:
        now = datetime.utcnow()

        # Find emails that are due
        scheduled_emails = (
            db.query(Email)
            .filter(
                Email.status == "draft",
                Email.scheduled_for.isnot(None),
                Email.scheduled_for <= now,
            )
            .order_by(Email.scheduled_for.asc())
            .limit(10)  # Process in batches
            .all()
        )

        if not scheduled_emails:
            return

        logger.info(f"Processing {len(scheduled_emails)} scheduled emails")

        for email in scheduled_emails:
            await _send_scheduled_email(db, email, email_service)

    finally:
        db.close()


async def _send_scheduled_email(
    db: Session,
    email: Email,
    email_service: EmailService,
):
    """
    Send a single scheduled email, respecting unsubscribe and validity.
    """
    try:
        # Get lead
        lead = db.query(Lead).filter(Lead.id == email.lead_id).first()
        if not lead:
            logger.warning(f"Lead not found for scheduled email {email.id}")
            email.status = "failed"
            email.error_message = "Lead not found"
            db.commit()
            return

        # Check unsubscribe
        if lead.unsubscribed_at:
            logger.info(f"Skipping email {email.id} - lead unsubscribed")
            email.status = "cancelled"
            email.error_message = "Lead unsubscribed"
            db.commit()
            return

        # Check email validity
        if hasattr(lead, "email_valid") and lead.email_valid is False:
            logger.info(f"Skipping email {email.id} - lead email invalid")
            email.status = "cancelled"
            email.error_message = "Lead email invalid"
            db.commit()
            return

        # Check if lead has already responded (opened/clicked previous email)
        # This is optional optimization - skip follow-ups if lead engaged
        if email.email_type in ("follow_up_1", "follow_up_2"):
            previous_engagement = (
                db.query(Email)
                .filter(
                    Email.lead_id == lead.id,
                    Email.call_id == email.call_id,
                    Email.status == "sent",
                    Email.created_at < email.created_at,
                )
                .filter(
                    (Email.replied_at.isnot(None))
                )
                .first()
            )
            if previous_engagement:
                logger.info(f"Skipping follow-up {email.id} - lead already replied")
                email.status = "cancelled"
                email.error_message = "Lead already replied"
                db.commit()
                return

        # Generate tracking ID if missing
        if not email.tracking_id:
            email.tracking_id = generate_tracking_id()
            db.commit()

        # Send the email
        success, tracking_id, error_category = await email_service.send_email(
            to_email=lead.email,
            to_name=lead.name or "there",
            subject=email.subject or "",
            html_body=email.body_html or "",
            text_body=email.body_text or "",
            lead_id=lead.id,
            tracking_id=email.tracking_id,
            preview_text=getattr(email, "preview_text", "") or "",
            use_template=True,
        )

        if success:
            email.status = "sent"
            email.sent_at = datetime.utcnow()
            logger.info(f"Scheduled email {email.id} sent to {lead.email}")
        else:
            email.status = "failed"
            email.error_category = error_category
            email.retry_count = (email.retry_count or 0) + 1
            logger.error(f"Scheduled email {email.id} failed: {error_category}")

            # Mark email invalid on recipient error
            if error_category == "recipient":
                lead.email_valid = False
                logger.warning(f"Lead {lead.id} email marked invalid")

        db.commit()

    except Exception as e:
        logger.error(f"Error sending scheduled email {email.id}: {e}")
        email.status = "failed"
        email.error_message = str(e)[:500]
        db.commit()


# =============================================================================
# Scheduling Functions
# =============================================================================

def schedule_followup_emails(db: Session, call_id: int) -> int:
    """
    Schedule follow-up emails for a call based on SEQUENCE_DELAYS.

    This should be called after the primary email is sent.
    Returns the number of emails scheduled.

    Args:
        db: Database session
        call_id: Call ID to schedule follow-ups for

    Returns:
        Number of emails scheduled
    """
    # Get all draft emails for this call
    emails = (
        db.query(Email)
        .filter(Email.call_id == call_id, Email.status == "draft")
        .order_by(Email.created_at.asc())
        .all()
    )

    if not emails:
        return 0

    # Find the primary email (first sent or first in sequence)
    primary_email = (
        db.query(Email)
        .filter(
            Email.call_id == call_id,
            Email.status == "sent",
        )
        .order_by(Email.sent_at.asc())
        .first()
    )

    # Use primary email sent_at or now as base time
    base_time = primary_email.sent_at if primary_email else datetime.utcnow()
    scheduled_count = 0

    for email in emails:
        email_type = email.email_type or ""

        # Get delay for this email type
        delay_days = SEQUENCE_DELAYS.get(email_type)

        if delay_days and not email.scheduled_for:
            # Calculate scheduled time
            if email_type == "follow_up_1":
                email.scheduled_for = base_time + timedelta(days=delay_days)
            elif email_type == "follow_up_2":
                # follow_up_2 is relative to follow_up_1
                fu1 = next((e for e in emails if e.email_type == "follow_up_1"), None)
                if fu1 and fu1.scheduled_for:
                    email.scheduled_for = fu1.scheduled_for + timedelta(days=delay_days)
                else:
                    email.scheduled_for = base_time + timedelta(days=8)  # Default

            scheduled_count += 1
            logger.info(
                f"Scheduled email {email.id} ({email_type}) for {email.scheduled_for}"
            )

    if scheduled_count > 0:
        db.commit()

    return scheduled_count


def cancel_scheduled_emails(db: Session, lead_id: int, reason: str = "cancelled") -> int:
    """
    Cancel all scheduled emails for a lead.

    Use when:
    - Lead unsubscribes
    - Lead books a demo (no need for follow-ups)
    - Lead replies to an email

    Returns number of emails cancelled.
    """
    result = (
        db.query(Email)
        .filter(
            Email.lead_id == lead_id,
            Email.status == "draft",
            Email.scheduled_for.isnot(None),
        )
        .update({
            Email.status: "cancelled",
            Email.error_message: reason,
        })
    )

    if result > 0:
        db.commit()
        logger.info(f"Cancelled {result} scheduled emails for lead {lead_id}")

    return result


def get_scheduled_email_count() -> int:
    """
    Get count of pending scheduled emails (for monitoring).
    """
    db: Session = SessionLocal()
    try:
        now = datetime.utcnow()
        return (
            db.query(Email)
            .filter(
                Email.status == "draft",
                Email.scheduled_for.isnot(None),
                Email.scheduled_for > now,
            )
            .count()
        )
    finally:
        db.close()


def get_overdue_email_count() -> int:
    """
    Get count of overdue scheduled emails (should be 0 if scheduler is running).
    """
    db: Session = SessionLocal()
    try:
        now = datetime.utcnow()
        return (
            db.query(Email)
            .filter(
                Email.status == "draft",
                Email.scheduled_for.isnot(None),
                Email.scheduled_for <= now,
            )
            .count()
        )
    finally:
        db.close()


# =============================================================================
# Health Check
# =============================================================================

def get_scheduler_status() -> dict:
    """
    Get scheduler status for health checks.
    """
    return {
        "running": _scheduler_running,
        "scheduled_count": get_scheduled_email_count(),
        "overdue_count": get_overdue_email_count(),
    }
