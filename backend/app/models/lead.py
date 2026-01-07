# backend/app/models/lead.py

from sqlalchemy import Column, Integer, String, Float, DateTime, Text, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class Lead(Base):
    __tablename__ = "leads"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    # ✅ REQUIRED
    name = Column(String(255), nullable=False)

    # ✅ REQUIRED + UNIQUE
    email = Column(String(255), unique=True, index=True, nullable=False)

    # ✅ REQUIRED
    phone = Column(String(50), nullable=False)

    # ✅ REQUIRED
    company = Column(String(255), nullable=False)

    # ✅ REQUIRED (role)
    title = Column(String(255), nullable=False)

    seniority = Column(String(100))
    linkedin_url = Column(String(500))

    status = Column(String(50), default="new", index=True)

    score = Column(Float, default=0.0)
    confidence = Column(Float, default=0.0)
    sentiment = Column(String(50))

    # ✅ Store enrichment like company_description here
    iip_data = Column(JSON)

    source = Column(String(100), default="apollo")
    apollo_id = Column(String(100))

    demo_scheduled_at = Column(DateTime(timezone=True))
    demo_notes = Column(Text)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    last_contacted_at = Column(DateTime(timezone=True))

    company_size = Column(String(100))
    company_industry = Column(String(255))
    company_location = Column(String(255))
    company_website = Column(String(500))

    campaign_id = Column(String(100))
    assigned_rep = Column(String(255))

    # ================= Relationships =================

    data_packet = relationship(
        "DataPacket",
        back_populates="lead",
        uselist=False,
        cascade="all, delete-orphan",
    )

    calls = relationship(
        "Call",
        back_populates="lead",
        cascade="all, delete-orphan",
    )

    emails = relationship(
        "Email",
        back_populates="lead",
        cascade="all, delete-orphan",
    )

    linkedin_messages = relationship(
        "LinkedInMessage",
        back_populates="lead",
        cascade="all, delete-orphan",
    )

    transcripts = relationship(
        "Transcript",
        back_populates="lead",
        cascade="all, delete-orphan",
    )
