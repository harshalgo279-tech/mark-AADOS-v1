from sqlalchemy import Column, Integer, Float, DateTime, Text, JSON, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class DataPacket(Base):
    __tablename__ = "data_packets"

    id = Column(Integer, primary_key=True, index=True)
    lead_id = Column(Integer, ForeignKey("leads.id", ondelete="CASCADE"), unique=True)

    company_analysis = Column(Text)
    pain_points = Column(JSON)

    use_case_1_title = Column(Text)
    use_case_1_description = Column(Text)
    use_case_1_impact = Column(Text)

    use_case_2_title = Column(Text)
    use_case_2_description = Column(Text)
    use_case_2_impact = Column(Text)

    use_case_3_title = Column(Text)
    use_case_3_description = Column(Text)
    use_case_3_impact = Column(Text)

    solution_1_title = Column(Text)
    solution_1_description = Column(Text)
    solution_1_roi = Column(Text)

    solution_2_title = Column(Text)
    solution_2_description = Column(Text)
    solution_2_roi = Column(Text)

    solution_3_title = Column(Text)
    solution_3_description = Column(Text)
    solution_3_roi = Column(Text)

    generated_at = Column(DateTime, server_default=func.now())
    confidence_score = Column(Float, default=0.0)

    lead = relationship("Lead", back_populates="data_packet")
