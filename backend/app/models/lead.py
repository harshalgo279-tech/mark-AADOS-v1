# backend/app/models/lead.py

from sqlalchemy import Column, Integer, String, Float, DateTime, Text, JSON, Boolean
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

    # ================= Scraped Company Data (Web Scraping) =================
    # These fields store comprehensive company data extracted from website scraping

    # Company overview extracted from website
    scraped_company_overview = Column(Text)

    # Services offered by the company (JSON array)
    scraped_services = Column(JSON)

    # Products offered by the company (JSON array)
    scraped_products = Column(JSON)

    # Industry/sector detected from website
    scraped_industry = Column(String(255))
    scraped_sector = Column(String(255))

    # Contact information from website
    scraped_contact_email = Column(String(255))
    scraped_contact_phone = Column(String(100))

    # Additional company info
    scraped_headquarters = Column(String(255))
    scraped_founded_year = Column(String(20))
    scraped_company_size = Column(String(100))

    # Business characteristics
    scraped_key_differentiators = Column(JSON)
    scraped_target_customers = Column(Text)
    scraped_technology_stack = Column(JSON)
    scraped_certifications = Column(JSON)
    scraped_partnerships = Column(JSON)

    # Scraping metadata
    scrape_confidence_score = Column(Float, default=0.0)
    scrape_success = Column(Boolean, default=False)
    scrape_errors = Column(JSON)
    scrape_sources = Column(JSON)
    scraped_at = Column(DateTime(timezone=True))

    # Raw markdown from scraping (for reference/debugging)
    scraped_raw_markdown = Column(Text)

    # ================= Email Compliance & Tracking =================
    # CAN-SPAM compliance: when the lead unsubscribed from emails
    unsubscribed_at = Column(DateTime(timezone=True), nullable=True)

    # Email validation: False if email bounced (hard bounce)
    email_valid = Column(Boolean, default=True, nullable=False)

    # ================= Email Engagement Intelligence =================
    # Engagement score (calculated from email interactions)
    email_engagement_score = Column(Integer, default=0)

    # Engagement level: hot, warm, lukewarm, cold, dead
    email_engagement_level = Column(String(20), default="cold")

    # Optimal send time (hour of day in UTC, 0-23)
    email_optimal_hour = Column(Integer, nullable=True)

    # Optimal send day (0=Monday, 6=Sunday)
    email_optimal_day = Column(Integer, nullable=True)

    # Timezone (inferred from company location)
    timezone = Column(String(50), nullable=True)

    # Last engagement score calculation
    engagement_calculated_at = Column(DateTime(timezone=True), nullable=True)

    # Reply sentiment from last email reply (-1 to 1)
    last_reply_sentiment = Column(Float, nullable=True)

    # Reply intent classification
    last_reply_intent = Column(String(50), nullable=True)

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
