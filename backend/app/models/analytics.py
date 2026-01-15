from sqlalchemy import Column, Integer, String, Float, DateTime, Text, JSON
from sqlalchemy.sql import func
from app.database import Base


class AnalyticsEvent(Base):
    """Analytics Event model"""
    __tablename__ = "analytics_events"
    
    id = Column(Integer, primary_key=True, index=True)
    event_type = Column(String(100), nullable=False, index=True)
    metric_name = Column(String(255), nullable=False)
    metric_value = Column(Float)
    context = Column(JSON)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)


class LearningEvent(Base):
    """Learning Event model for tracking model changes"""
    __tablename__ = "learning_events"
    
    id = Column(Integer, primary_key=True, index=True)
    event_type = Column(String(100), nullable=False)  # icp_update, script_update, email_update
    change_description = Column(Text, nullable=False)
    rationale = Column(Text)
    
    # Before/After
    previous_config = Column(JSON)
    new_config = Column(JSON)
    
    # Performance Impact
    baseline_metric = Column(Float)
    new_metric = Column(Float)
    improvement = Column(Float)
    
    # Status
    status = Column(String(50), default="active")  # active, rolled_back, superseded
    rollback_reason = Column(Text)
    
    # Timestamps
    implemented_at = Column(DateTime(timezone=True), server_default=func.now())
    evaluated_at = Column(DateTime(timezone=True))
    rolled_back_at = Column(DateTime(timezone=True))