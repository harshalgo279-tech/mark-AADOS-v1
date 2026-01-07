from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


class Email(Base):
    __tablename__ = "emails"

    id = Column(Integer, primary_key=True, index=True)

    lead_id = Column(Integer, ForeignKey("leads.id", ondelete="CASCADE"), nullable=False)
    call_id = Column(Integer, ForeignKey("calls.id", ondelete="SET NULL"))

    subject = Column(Text, nullable=False)
    body_html = Column(Text, nullable=False)
    body_text = Column(Text)

    email_type = Column(String(100))

    sent_at = Column(DateTime)
    delivered_at = Column(DateTime)
    opened_at = Column(DateTime)
    clicked_at = Column(DateTime)
    replied_at = Column(DateTime)

    status = Column(String(50), default="pending")

    pdf_attached = Column(Boolean, default=False)
    pdf_path = Column(Text)

    created_at = Column(DateTime)

    lead = relationship("Lead", back_populates="emails")
    call = relationship("Call", back_populates="emails")
