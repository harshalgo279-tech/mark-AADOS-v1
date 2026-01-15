# backend/app/models/learning_event.py

from sqlalchemy import Column, Integer, String, DateTime, Text, Float, JSON
from sqlalchemy.sql import func

from app.database import Base


class LearningEvent(Base):
    """
    Track AI model changes and their impact (FRD FR-37, FR-41)

    - event_type: icp_update, script_update, learning_cycle_completed, rollback, etc.
    - previous_config/new_config: JSON configs of prompts/thresholds/filters
    - baseline_metric/new_metric/improvement: for demo rate or any chosen metric
    - status: active/rolled_back/superseded
    """

    __tablename__ = "learning_events"

    id = Column(Integer, primary_key=True, index=True)

    event_type = Column(String(100), nullable=False)
    change_description = Column(Text, nullable=False)
    rationale = Column(Text, nullable=True)

    previous_config = Column(JSON, nullable=True)
    new_config = Column(JSON, nullable=True)

    baseline_metric = Column(Float, nullable=True)
    new_metric = Column(Float, nullable=True)
    improvement = Column(Float, nullable=True)

    status = Column(String(50), nullable=False, server_default="active")
    rollback_reason = Column(Text, nullable=True)

    implemented_at = Column(DateTime, server_default=func.now(), nullable=False)
    evaluated_at = Column(DateTime, nullable=True)
    rolled_back_at = Column(DateTime, nullable=True)
