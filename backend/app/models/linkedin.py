# backend/app/models/linkedin.py
from sqlalchemy import Column, Integer, DateTime, Text, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class LinkedInMessage(Base):
    __tablename__ = "linkedin_messages"

    id = Column(Integer, primary_key=True, index=True)
    lead_id = Column(Integer, ForeignKey("leads.id", ondelete="CASCADE"), nullable=False)

    # Existing columns
    use_case_1_message = Column(Text)
    use_case_2_message = Column(Text)
    use_case_3_message = Column(Text)

    connection_request = Column(Text)  # connection_request_1
    follow_up_1 = Column(Text)
    follow_up_2 = Column(Text)

    # ✅ New columns (Option B)
    connection_request_2 = Column(Text, nullable=True)
    connection_request_3 = Column(Text, nullable=True)
    follow_up_3 = Column(Text, nullable=True)
    bd_summary = Column(Text, nullable=True)

    generated_at = Column(DateTime, server_default=func.now())

    lead = relationship("Lead", back_populates="linkedin_messages")
