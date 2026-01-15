# backend/app/models/call.py

from sqlalchemy import Column, Integer, String, Float, DateTime, Text, JSON, Boolean, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.database import Base


class Call(Base):
    __tablename__ = "calls"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    lead_id = Column(Integer, ForeignKey("leads.id", ondelete="CASCADE"), nullable=False)

    twilio_call_sid = Column(String(100), unique=True, index=True)
    elevenlabs_conversation_id = Column(String(100), index=True)  # For real-time transcript streaming
    phone_number = Column(String(50))
    duration = Column(Integer)
    status = Column(String(50), index=True)

    full_transcript = Column(Text)
    transcript_summary = Column(Text)

    script_used = Column(Text)

    lead_interest_level = Column(String(50))
    objections_raised = Column(JSON)
    questions_asked = Column(JSON)
    sentiment = Column(String(50))

    demo_requested = Column(Boolean, default=False)
    follow_up_requested = Column(Boolean, default=False)
    use_cases_discussed = Column(JSON)

    started_at = Column(DateTime)
    ended_at = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now())

    recording_url = Column(String(500))

    # ------------------------------------------------------------------
    # ✅ FRD ENHANCEMENTS (BANT + Conversation Tracking)
    # NOTE: These require DB migration to exist in MySQL.
    # ------------------------------------------------------------------

    # BANT scores (0-100)
    bant_budget = Column(Integer, nullable=False, server_default="0")
    bant_authority = Column(Integer, nullable=False, server_default="0")
    bant_need = Column(Integer, nullable=False, server_default="0")
    bant_timeline = Column(Integer, nullable=False, server_default="0")
    bant_overall = Column(Float, nullable=False, server_default="0")

    # Conversation metadata
    conversation_phase = Column(String(50), nullable=True)  # opening/discovery/presentation/objection_handling/closing
    turn_count = Column(Integer, nullable=False, server_default="0")
    pain_points_count = Column(Integer, nullable=False, server_default="0")
    objections_count = Column(Integer, nullable=False, server_default="0")
    buying_signals_count = Column(Integer, nullable=False, server_default="0")

    # Sentiment trajectory (e.g. [60, 58, 65, 70, 73])
    sentiment_trajectory = Column(JSON, nullable=True)

    # Relationships
    lead = relationship("Lead", back_populates="calls")
    emails = relationship("Email", back_populates="call")

    # transcripts table relation (doesn't change existing schema unless migrated)
    transcripts = relationship(
        "Transcript",
        back_populates="call",
        cascade="all, delete-orphan",
    )
