# backend/app/api/email_intelligence.py
"""
Email Intelligence API endpoints.

Provides AI-powered email optimization including:
- Engagement scoring
- Send time optimization
- Reply analysis
- A/B testing
- Deliverability health
- Adaptive sequence recommendations
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.lead import Lead
from app.models.email import Email
from app.models.email_ab_test import EmailABTest, EmailABTestVariant, EmailReply, EmailWarmupLog
from app.agents.email_intelligence_agent import (
    EmailIntelligenceAgent,
    get_lead_email_intelligence,
    ReplyIntent,
    EngagementLevel,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/email-intelligence", tags=["email-intelligence"])


# =============================================================================
# Request/Response Models
# =============================================================================

class ReplyAnalysisRequest(BaseModel):
    reply_text: str
    email_id: Optional[int] = None
    lead_id: Optional[int] = None


class SubjectVariantRequest(BaseModel):
    original_subject: str
    email_type: str
    lead_id: int
    num_variants: int = 3


class ContentAnalysisRequest(BaseModel):
    subject: str
    body_html: str
    email_type: str = "follow_up"


class ABTestCreateRequest(BaseModel):
    name: str
    email_type: str
    test_type: str = "subject"  # subject, content, send_time
    variants: List[dict]  # [{name, content, approach}]
    min_sample_size: int = 50


# =============================================================================
# Lead Intelligence Endpoints
# =============================================================================

@router.get("/lead/{lead_id}")
async def get_lead_intelligence(
    lead_id: int,
    db: Session = Depends(get_db),
):
    """
    Get comprehensive email intelligence for a lead.

    Returns:
    - Engagement score and level
    - Optimal send time
    - Next recommended action
    - Recent email performance
    """
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    intelligence = await get_lead_email_intelligence(db, lead_id)

    # Add lead context
    intelligence["lead"] = {
        "name": lead.name,
        "company": lead.company,
        "email": lead.email,
        "industry": lead.company_industry,
        "unsubscribed": lead.unsubscribed_at is not None,
        "email_valid": lead.email_valid,
    }

    return intelligence


@router.post("/lead/{lead_id}/refresh-engagement")
async def refresh_lead_engagement(
    lead_id: int,
    db: Session = Depends(get_db),
):
    """
    Recalculate and store engagement score for a lead.

    This updates the lead's engagement_score and engagement_level fields.
    """
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    agent = EmailIntelligenceAgent(db)
    engagement = await agent.calculate_engagement_score(lead_id)

    # Update lead record
    lead.email_engagement_score = engagement["score"]
    lead.email_engagement_level = engagement["level"]
    lead.engagement_calculated_at = datetime.utcnow()

    # Update optimal send time
    optimal_time = await agent.get_optimal_send_time(lead_id)
    lead.email_optimal_hour = optimal_time.hour
    lead.email_optimal_day = optimal_time.weekday()

    db.commit()

    return {
        "lead_id": lead_id,
        "engagement": engagement,
        "optimal_send_time": optimal_time.isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
    }


@router.get("/lead/{lead_id}/optimal-send-time")
async def get_optimal_send_time(
    lead_id: int,
    prefer_within_hours: int = Query(48, ge=1, le=168),
    db: Session = Depends(get_db),
):
    """
    Get the optimal time to send an email to this lead.

    Based on:
    - Lead's past email engagement patterns
    - Industry defaults
    - Time constraints
    """
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    agent = EmailIntelligenceAgent(db)
    optimal_time = await agent.get_optimal_send_time(lead_id, prefer_within_hours)

    return {
        "lead_id": lead_id,
        "optimal_send_time": optimal_time.isoformat(),
        "optimal_hour_utc": optimal_time.hour,
        "optimal_day": optimal_time.strftime("%A"),
        "based_on": "lead_behavior" if lead.email_engagement_score > 0 else "industry_defaults",
    }


@router.get("/lead/{lead_id}/next-action")
async def get_next_action_for_lead(
    lead_id: int,
    call_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """
    Get AI-recommended next action for a lead's email sequence.

    Returns adaptive branching decision based on engagement.
    """
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    agent = EmailIntelligenceAgent(db)
    next_step = await agent.determine_next_sequence_step(lead_id, call_id)

    return {
        "lead_id": lead_id,
        "recommendation": next_step,
    }


# =============================================================================
# Reply Analysis Endpoints
# =============================================================================

@router.post("/analyze-reply")
async def analyze_email_reply(
    request: ReplyAnalysisRequest,
    db: Session = Depends(get_db),
):
    """
    Analyze an email reply using AI.

    Determines:
    - Intent (interested, objection, OOO, etc.)
    - Sentiment score
    - Recommended next action
    - Key points
    """
    agent = EmailIntelligenceAgent(db)
    analysis = await agent.analyze_reply(request.reply_text, request.email_id)

    # Store analysis if we have lead/email context
    if request.email_id and request.lead_id:
        reply_record = EmailReply(
            email_id=request.email_id,
            lead_id=request.lead_id,
            reply_body=request.reply_text,
            reply_received_at=datetime.utcnow(),
            intent=analysis.get("intent"),
            sentiment=analysis.get("sentiment"),
            confidence=analysis.get("confidence"),
            key_points=analysis.get("key_points"),
            objections=analysis.get("objections"),
            questions=analysis.get("questions"),
            recommended_action=analysis.get("next_action"),
            urgency=analysis.get("urgency"),
            processed=True,
            processed_at=datetime.utcnow(),
        )
        db.add(reply_record)

        # Update email with reply info
        email = db.query(Email).filter(Email.id == request.email_id).first()
        if email and not email.replied_at:
            email.replied_at = datetime.utcnow()

        # Update lead with reply sentiment
        lead = db.query(Lead).filter(Lead.id == request.lead_id).first()
        if lead:
            lead.last_reply_sentiment = analysis.get("sentiment")
            lead.last_reply_intent = analysis.get("intent")

        db.commit()

    return analysis


@router.get("/replies/{lead_id}")
async def get_lead_replies(
    lead_id: int,
    db: Session = Depends(get_db),
):
    """Get all analyzed replies for a lead."""
    replies = (
        db.query(EmailReply)
        .filter(EmailReply.lead_id == lead_id)
        .order_by(EmailReply.created_at.desc())
        .all()
    )

    return {
        "lead_id": lead_id,
        "replies": [
            {
                "id": r.id,
                "email_id": r.email_id,
                "intent": r.intent,
                "sentiment": r.sentiment,
                "key_points": r.key_points,
                "recommended_action": r.recommended_action,
                "urgency": r.urgency,
                "received_at": r.reply_received_at.isoformat() if r.reply_received_at else None,
            }
            for r in replies
        ],
    }


# =============================================================================
# A/B Testing Endpoints
# =============================================================================

@router.post("/ab-test")
async def create_ab_test(
    request: ABTestCreateRequest,
    db: Session = Depends(get_db),
):
    """
    Create a new A/B test for email optimization.

    Test types:
    - subject: Test different subject lines
    - content: Test different email body content
    - send_time: Test different send times
    """
    # Create test
    test = EmailABTest(
        name=request.name,
        email_type=request.email_type,
        test_type=request.test_type,
        min_sample_size=request.min_sample_size,
        status="active",
        started_at=datetime.utcnow(),
    )
    db.add(test)
    db.flush()

    # Create variants
    for i, v in enumerate(request.variants):
        variant = EmailABTestVariant(
            test_id=test.id,
            variant_name=v.get("name", chr(65 + i)),  # A, B, C...
            variant_content=v.get("content", ""),
            variant_approach=v.get("approach"),
            is_control=v.get("is_control", i == 0),
        )
        db.add(variant)

    db.commit()

    return {
        "test_id": test.id,
        "name": test.name,
        "status": test.status,
        "variants_created": len(request.variants),
    }


@router.get("/ab-test/{test_id}")
async def get_ab_test(
    test_id: int,
    db: Session = Depends(get_db),
):
    """Get A/B test details and current results."""
    test = db.query(EmailABTest).filter(EmailABTest.id == test_id).first()
    if not test:
        raise HTTPException(status_code=404, detail="Test not found")

    variants = (
        db.query(EmailABTestVariant)
        .filter(EmailABTestVariant.test_id == test_id)
        .all()
    )

    return {
        "test": {
            "id": test.id,
            "name": test.name,
            "email_type": test.email_type,
            "test_type": test.test_type,
            "status": test.status,
            "min_sample_size": test.min_sample_size,
            "started_at": test.started_at.isoformat() if test.started_at else None,
            "completed_at": test.completed_at.isoformat() if test.completed_at else None,
        },
        "variants": [
            {
                "id": v.id,
                "name": v.variant_name,
                "content": v.variant_content[:100] + "..." if len(v.variant_content) > 100 else v.variant_content,
                "approach": v.variant_approach,
                "is_control": v.is_control,
                "is_winner": v.is_winner,
                "metrics": {
                    "sent": v.emails_sent,
                    "opened": v.emails_opened,
                    "clicked": v.emails_clicked,
                    "open_rate": round(v.open_rate * 100, 1),
                    "click_rate": round(v.click_rate * 100, 1),
                },
                "lift_vs_control": v.lift_vs_control,
            }
            for v in variants
        ],
    }


@router.post("/ab-test/{test_id}/record")
async def record_ab_test_result(
    test_id: int,
    variant_id: int = Query(...),
    event: str = Query(..., regex="^(sent|opened|clicked|replied|converted)$"),
    db: Session = Depends(get_db),
):
    """Record an event for an A/B test variant."""
    variant = (
        db.query(EmailABTestVariant)
        .filter(
            EmailABTestVariant.id == variant_id,
            EmailABTestVariant.test_id == test_id,
        )
        .first()
    )
    if not variant:
        raise HTTPException(status_code=404, detail="Variant not found")

    # Increment counter
    if event == "sent":
        variant.emails_sent += 1
    elif event == "opened":
        variant.emails_opened += 1
    elif event == "clicked":
        variant.emails_clicked += 1
    elif event == "replied":
        variant.emails_replied += 1
    elif event == "converted":
        variant.emails_converted += 1

    # Update rates
    if variant.emails_sent > 0:
        variant.open_rate = variant.emails_opened / variant.emails_sent
        variant.click_rate = variant.emails_clicked / variant.emails_sent
        variant.reply_rate = variant.emails_replied / variant.emails_sent
        variant.conversion_rate = variant.emails_converted / variant.emails_sent

    db.commit()

    return {"status": "recorded", "variant_id": variant_id, "event": event}


@router.get("/ab-tests")
async def list_ab_tests(
    status: Optional[str] = Query(None, regex="^(active|paused|completed)$"),
    email_type: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """List all A/B tests."""
    query = db.query(EmailABTest)

    if status:
        query = query.filter(EmailABTest.status == status)
    if email_type:
        query = query.filter(EmailABTest.email_type == email_type)

    tests = query.order_by(EmailABTest.created_at.desc()).all()

    return {
        "tests": [
            {
                "id": t.id,
                "name": t.name,
                "email_type": t.email_type,
                "test_type": t.test_type,
                "status": t.status,
                "started_at": t.started_at.isoformat() if t.started_at else None,
            }
            for t in tests
        ]
    }


# =============================================================================
# Subject Line Generation
# =============================================================================

@router.post("/generate-subjects")
async def generate_subject_variants(
    request: SubjectVariantRequest,
    db: Session = Depends(get_db),
):
    """
    Generate A/B test subject line variants using AI.

    Creates variations with different approaches:
    - Curiosity-driven
    - Benefit-focused
    - Question-based
    - Personalized
    """
    lead = db.query(Lead).filter(Lead.id == request.lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    agent = EmailIntelligenceAgent(db)
    variants = await agent.generate_subject_variants(
        original_subject=request.original_subject,
        email_type=request.email_type,
        lead=lead,
        num_variants=request.num_variants,
    )

    return {"variants": variants}


# =============================================================================
# Content Analysis
# =============================================================================

@router.post("/analyze-content")
async def analyze_email_content(
    request: ContentAnalysisRequest,
    db: Session = Depends(get_db),
):
    """
    Analyze email content for optimization opportunities.

    Checks:
    - Spam trigger words
    - Length optimization
    - Personalization level
    - CTA clarity
    """
    agent = EmailIntelligenceAgent(db)
    analysis = await agent.analyze_email_content(
        subject=request.subject,
        body_html=request.body_html,
        email_type=request.email_type,
    )

    return analysis


# =============================================================================
# Deliverability Health
# =============================================================================

@router.get("/health")
async def get_deliverability_health(
    db: Session = Depends(get_db),
):
    """
    Get overall email deliverability health metrics.

    Monitors:
    - Bounce rate
    - Open rate trends
    - Domain warmup status
    - Recommendations
    """
    agent = EmailIntelligenceAgent(db)
    health = await agent.get_deliverability_health()

    return health


@router.get("/warmup-status")
async def get_warmup_status(
    db: Session = Depends(get_db),
):
    """
    Get detailed domain warmup status and history.
    """
    # Get last 30 days of warmup logs
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)

    logs = (
        db.query(EmailWarmupLog)
        .filter(EmailWarmupLog.date >= thirty_days_ago)
        .order_by(EmailWarmupLog.date.asc())
        .all()
    )

    # Calculate trend
    if len(logs) >= 7:
        recent_avg = sum(l.emails_sent for l in logs[-7:]) / 7
        earlier_avg = sum(l.emails_sent for l in logs[:7]) / 7
        volume_trend = "increasing" if recent_avg > earlier_avg else "stable"
    else:
        volume_trend = "insufficient_data"

    return {
        "warmup_logs": [
            {
                "date": l.date.isoformat(),
                "sent": l.emails_sent,
                "delivered": l.emails_delivered,
                "bounced": l.emails_bounced,
                "bounce_rate": l.bounce_rate,
                "health_score": l.health_score,
            }
            for l in logs
        ],
        "volume_trend": volume_trend,
        "total_days_tracked": len(logs),
    }


# =============================================================================
# Bulk Operations
# =============================================================================

@router.post("/refresh-all-engagement")
async def refresh_all_engagement_scores(
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    """
    Refresh engagement scores for all active leads.

    This is a batch operation that should be run periodically.
    """
    # Get leads that need refresh (not calculated recently)
    threshold = datetime.utcnow() - timedelta(hours=24)

    leads = (
        db.query(Lead)
        .filter(
            Lead.unsubscribed_at.is_(None),
            Lead.email_valid == True,
        )
        .filter(
            (Lead.engagement_calculated_at.is_(None))
            | (Lead.engagement_calculated_at < threshold)
        )
        .limit(limit)
        .all()
    )

    agent = EmailIntelligenceAgent(db)
    updated = 0

    for lead in leads:
        try:
            engagement = await agent.calculate_engagement_score(lead.id)
            lead.email_engagement_score = engagement["score"]
            lead.email_engagement_level = engagement["level"]
            lead.engagement_calculated_at = datetime.utcnow()
            updated += 1
        except Exception as e:
            logger.error(f"Failed to update engagement for lead {lead.id}: {e}")

    db.commit()

    return {
        "updated": updated,
        "total_processed": len(leads),
    }


# =============================================================================
# Reply Webhook (for email service providers)
# =============================================================================

class InboundReplyWebhook(BaseModel):
    """Webhook payload for inbound email replies."""
    from_email: str
    to_email: str
    subject: str
    body_text: Optional[str] = None
    body_html: Optional[str] = None
    message_id: Optional[str] = None
    in_reply_to: Optional[str] = None
    received_at: Optional[str] = None


@router.post("/webhook/reply")
async def process_inbound_reply(
    payload: InboundReplyWebhook,
    db: Session = Depends(get_db),
):
    """
    Webhook endpoint for processing inbound email replies.

    This endpoint should be configured in your email service provider
    (e.g., SendGrid, Postmark, Mailgun) to forward replies.

    The system will:
    1. Match the reply to the original email/lead
    2. Analyze the reply using AI
    3. Update lead engagement scores
    4. Trigger appropriate follow-up actions
    """
    logger.info(f"Received reply webhook from {payload.from_email}")

    # Find the lead by email
    lead = db.query(Lead).filter(Lead.email == payload.from_email).first()
    if not lead:
        logger.warning(f"No lead found for reply from {payload.from_email}")
        return {"status": "ignored", "reason": "lead_not_found"}

    # Find the most recent email sent to this lead
    recent_email = (
        db.query(Email)
        .filter(
            Email.lead_id == lead.id,
            Email.status == "sent",
        )
        .order_by(Email.sent_at.desc())
        .first()
    )

    if not recent_email:
        logger.warning(f"No sent emails found for lead {lead.id}")
        return {"status": "ignored", "reason": "no_sent_emails"}

    # Extract reply text
    reply_text = payload.body_text or ""
    if not reply_text and payload.body_html:
        # Strip HTML tags for analysis
        import re
        reply_text = re.sub(r'<[^>]+>', ' ', payload.body_html)
        reply_text = re.sub(r'\s+', ' ', reply_text).strip()

    if not reply_text:
        return {"status": "ignored", "reason": "empty_reply"}

    # Analyze the reply
    agent = EmailIntelligenceAgent(db)
    analysis = await agent.analyze_reply(reply_text, recent_email.id)

    # Store the reply analysis
    reply_record = EmailReply(
        email_id=recent_email.id,
        lead_id=lead.id,
        reply_subject=payload.subject,
        reply_body=reply_text[:5000],  # Limit storage
        reply_received_at=datetime.fromisoformat(payload.received_at) if payload.received_at else datetime.utcnow(),
        intent=analysis.get("intent"),
        sentiment=analysis.get("sentiment"),
        confidence=analysis.get("confidence"),
        key_points=analysis.get("key_points"),
        objections=analysis.get("objections"),
        questions=analysis.get("questions"),
        recommended_action=analysis.get("next_action"),
        urgency=analysis.get("urgency"),
        processed=True,
        processed_at=datetime.utcnow(),
    )
    db.add(reply_record)

    # Update email with reply info
    if not recent_email.replied_at:
        recent_email.replied_at = datetime.utcnow()

    # Update lead with reply sentiment
    lead.last_reply_sentiment = analysis.get("sentiment")
    lead.last_reply_intent = analysis.get("intent")

    # Cancel scheduled follow-ups if reply was positive
    if analysis.get("intent") in ["interested", "meeting_request", "more_info"]:
        from app.services.email_scheduler import cancel_scheduled_emails
        cancelled = cancel_scheduled_emails(db, lead.id, "positive_reply_received")
        logger.info(f"Cancelled {cancelled} scheduled emails for lead {lead.id} due to positive reply")

    # Refresh engagement score
    engagement = await agent.calculate_engagement_score(lead.id)
    lead.email_engagement_score = engagement["score"]
    lead.email_engagement_level = engagement["level"]
    lead.engagement_calculated_at = datetime.utcnow()

    db.commit()

    logger.info(f"Processed reply from {payload.from_email}: intent={analysis.get('intent')}, sentiment={analysis.get('sentiment')}")

    return {
        "status": "processed",
        "lead_id": lead.id,
        "email_id": recent_email.id,
        "reply_id": reply_record.id,
        "analysis": {
            "intent": analysis.get("intent"),
            "sentiment": analysis.get("sentiment"),
            "recommended_action": analysis.get("next_action"),
            "urgency": analysis.get("urgency"),
        },
        "engagement_updated": {
            "score": engagement["score"],
            "level": engagement["level"],
        },
    }


@router.get("/engagement-summary")
async def get_engagement_summary(
    db: Session = Depends(get_db),
):
    """
    Get summary of lead engagement across all levels.
    """
    # Count leads by engagement level
    level_counts = (
        db.query(
            Lead.email_engagement_level,
            func.count(Lead.id).label("count"),
        )
        .filter(
            Lead.unsubscribed_at.is_(None),
            Lead.email_valid == True,
        )
        .group_by(Lead.email_engagement_level)
        .all()
    )

    summary = {level.value: 0 for level in EngagementLevel}
    for row in level_counts:
        if row.email_engagement_level:
            summary[row.email_engagement_level] = row.count

    # Get top engaged leads
    top_leads = (
        db.query(Lead)
        .filter(
            Lead.email_engagement_level.in_(["hot", "warm"]),
            Lead.unsubscribed_at.is_(None),
        )
        .order_by(Lead.email_engagement_score.desc())
        .limit(10)
        .all()
    )

    return {
        "by_level": summary,
        "total_active": sum(summary.values()),
        "top_engaged_leads": [
            {
                "id": l.id,
                "name": l.name,
                "company": l.company,
                "score": l.email_engagement_score,
                "level": l.email_engagement_level,
            }
            for l in top_leads
        ],
    }
