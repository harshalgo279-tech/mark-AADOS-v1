from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, ForeignKey, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class Email(Base):
    __tablename__ = "emails"

    id = Column(Integer, primary_key=True, index=True)

    lead_id = Column(Integer, ForeignKey("leads.id", ondelete="CASCADE"), nullable=False)
    call_id = Column(Integer, ForeignKey("calls.id", ondelete="SET NULL"))

    subject = Column(Text, nullable=False)
    body_html = Column(Text, nullable=False)
    body_text = Column(Text)

    # Preview text (preheader) for email clients
    preview_text = Column(String(255), nullable=True)

    email_type = Column(String(100))

    # Scheduling: when this email should be sent (for automated sequences)
    scheduled_for = Column(DateTime(timezone=True), nullable=True, index=True)

    # Unique tracking ID for open/click tracking
    tracking_id = Column(String(64), unique=True, nullable=True, index=True)

    sent_at = Column(DateTime(timezone=True))
    delivered_at = Column(DateTime(timezone=True))
    opened_at = Column(DateTime(timezone=True))
    clicked_at = Column(DateTime(timezone=True))
    replied_at = Column(DateTime(timezone=True))
    bounced_at = Column(DateTime(timezone=True))

    # Error tracking
    error_message = Column(Text, nullable=True)
    error_category = Column(String(50), nullable=True)  # connection, auth, recipient, content
    retry_count = Column(Integer, default=0)

    status = Column(String(50), default="pending")  # pending, draft, scheduled, sent, failed, bounced

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    lead = relationship("Lead", back_populates="emails")
    call = relationship("Call", back_populates="emails")

    # Composite index for duplicate prevention: same lead + email_type within 24h
    __table_args__ = (
        Index('ix_emails_lead_type_date', 'lead_id', 'email_type', 'created_at'),
    )
