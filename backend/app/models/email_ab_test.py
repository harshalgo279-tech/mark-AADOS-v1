# backend/app/models/email_ab_test.py
"""
A/B Testing model for email subject lines and content.

Tracks:
- Subject line variants and their performance
- Content variations
- Statistical significance of results
"""

from sqlalchemy import Column, Integer, String, DateTime, Text, Float, Boolean, JSON, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class EmailABTest(Base):
    """
    Tracks A/B tests for email optimization.

    Each test can have multiple variants, and the system
    automatically tracks performance and determines winners.
    """
    __tablename__ = "email_ab_tests"

    id = Column(Integer, primary_key=True, index=True)

    # Test identification
    name = Column(String(255), nullable=False)
    email_type = Column(String(100), nullable=False)  # e.g., "follow_up_1"
    test_type = Column(String(50), nullable=False)  # "subject", "content", "send_time"

    # Test status
    status = Column(String(20), default="active")  # active, paused, completed
    winner_variant_id = Column(Integer, nullable=True)

    # Test configuration
    min_sample_size = Column(Integer, default=50)  # Per variant
    confidence_threshold = Column(Float, default=0.95)  # 95% confidence

    # Timing
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))

    # Results summary (updated periodically)
    results_summary = Column(JSON)

    # Relationships
    variants = relationship(
        "EmailABTestVariant",
        back_populates="test",
        cascade="all, delete-orphan",
    )


class EmailABTestVariant(Base):
    """
    Individual variant in an A/B test.

    For subject line tests:
    - variant_content = the subject line

    For content tests:
    - variant_content = the email body (HTML)
    """
    __tablename__ = "email_ab_test_variants"

    id = Column(Integer, primary_key=True, index=True)
    test_id = Column(Integer, ForeignKey("email_ab_tests.id", ondelete="CASCADE"), nullable=False)

    # Variant content
    variant_name = Column(String(100), nullable=False)  # "A", "B", "Control"
    variant_content = Column(Text, nullable=False)  # Subject line or body
    variant_approach = Column(String(100))  # e.g., "curiosity", "benefit", "question"
    is_control = Column(Boolean, default=False)

    # Performance metrics
    emails_sent = Column(Integer, default=0)
    emails_opened = Column(Integer, default=0)
    emails_clicked = Column(Integer, default=0)
    emails_replied = Column(Integer, default=0)
    emails_converted = Column(Integer, default=0)  # Meeting booked

    # Calculated rates (updated periodically)
    open_rate = Column(Float, default=0.0)
    click_rate = Column(Float, default=0.0)
    reply_rate = Column(Float, default=0.0)
    conversion_rate = Column(Float, default=0.0)

    # Statistical significance
    is_winner = Column(Boolean, default=False)
    lift_vs_control = Column(Float)  # Percentage improvement over control

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    test = relationship("EmailABTest", back_populates="variants")


class EmailWarmupLog(Base):
    """
    Tracks daily email sending volume for domain warmup monitoring.

    Best practice is to gradually increase volume:
    - Week 1: 10-20 emails/day
    - Week 2: 20-40 emails/day
    - Week 3: 40-80 emails/day
    - Week 4+: Scale to target volume
    """
    __tablename__ = "email_warmup_logs"

    id = Column(Integer, primary_key=True, index=True)

    # Date tracking
    date = Column(DateTime(timezone=True), nullable=False, index=True)

    # Volume metrics
    emails_sent = Column(Integer, default=0)
    emails_delivered = Column(Integer, default=0)
    emails_bounced = Column(Integer, default=0)
    emails_opened = Column(Integer, default=0)
    emails_clicked = Column(Integer, default=0)

    # Rate metrics (calculated)
    delivery_rate = Column(Float, default=0.0)
    bounce_rate = Column(Float, default=0.0)
    open_rate = Column(Float, default=0.0)

    # Reputation indicators
    spam_complaints = Column(Integer, default=0)
    spam_complaint_rate = Column(Float, default=0.0)

    # Warmup status
    warmup_day = Column(Integer)  # Day number since warmup started
    recommended_daily_limit = Column(Integer)  # Based on warmup progress
    actual_vs_recommended = Column(Float)  # Ratio of actual to recommended

    # Health assessment
    health_score = Column(Integer)  # 0-100
    health_status = Column(String(20))  # healthy, warning, critical
    health_notes = Column(Text)

    created_at = Column(DateTime(timezone=True), server_default=func.now())


class EmailReply(Base):
    """
    Stores analyzed email replies for intelligence.

    When a reply is detected (via email webhook or manual input),
    the AI analyzes it and stores the results here.
    """
    __tablename__ = "email_replies"

    id = Column(Integer, primary_key=True, index=True)

    # Link to original email
    email_id = Column(Integer, ForeignKey("emails.id", ondelete="CASCADE"), nullable=False)
    lead_id = Column(Integer, ForeignKey("leads.id", ondelete="CASCADE"), nullable=False)

    # Reply content
    reply_subject = Column(String(500))
    reply_body = Column(Text)
    reply_received_at = Column(DateTime(timezone=True))

    # AI Analysis results
    intent = Column(String(50))  # interested, objection, not_now, etc.
    sentiment = Column(Float)  # -1 to 1
    confidence = Column(Float)  # 0 to 1

    # Extracted information
    key_points = Column(JSON)  # List of important points
    objections = Column(JSON)  # Any objections raised
    questions = Column(JSON)  # Questions asked

    # Recommended action
    recommended_action = Column(String(50))  # call_immediately, send_info, etc.
    urgency = Column(String(20))  # high, medium, low

    # Processing status
    processed = Column(Boolean, default=False)
    processed_at = Column(DateTime(timezone=True))
    action_taken = Column(String(100))
    action_taken_at = Column(DateTime(timezone=True))

    created_at = Column(DateTime(timezone=True), server_default=func.now())
