# backend/app/models/transcript.py
from sqlalchemy import Column, Integer, Text, DateTime, ForeignKey, String
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.database import Base


class Transcript(Base):
    __tablename__ = "transcripts"

    # ✅ primary key as requested
    twilio_call_sid = Column(String(100), primary_key=True, index=True)

    # Link transcript to call + lead
    call_id = Column(Integer, ForeignKey("calls.id", ondelete="CASCADE"), nullable=False, index=True)
    lead_id = Column(Integer, ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True)

    # Full transcript text
    full_transcript = Column(Text, nullable=False)

    created_at = Column(DateTime, server_default=func.now())

    # Relationships
    call = relationship("Call", back_populates="transcripts")
    lead = relationship("Lead", back_populates="transcripts")
