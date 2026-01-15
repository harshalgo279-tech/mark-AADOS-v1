# backend/app/api/analyst.py

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.agents.analyst_agent import AnalystAgent
from app.models.learning_event import LearningEvent


router = APIRouter(prefix="/api/analyst", tags=["analyst"])


@router.post("/learning-cycle")
async def run_learning_cycle(db: Session = Depends(get_db)):
    """
    Trigger learning cycle manually (normally weekly).
    Returns:
    - calls analyzed
    - recommendations
    - pattern analysis
    """
    try:
        agent = AnalystAgent(db)
        result = await agent.run_learning_cycle()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/performance-monitor")
async def monitor_performance(db: Session = Depends(get_db)):
    """
    Check if recent changes degraded performance and rollback if needed.
    """
    try:
        agent = AnalystAgent(db)
        result = await agent.monitor_performance_and_rollback()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/learning-events")
async def get_learning_events(limit: int = 20, db: Session = Depends(get_db)):
    """
    Get recent learning events for dashboard visibility.
    """
    try:
        events = (
            db.query(LearningEvent)
            .order_by(LearningEvent.implemented_at.desc())
            .limit(limit)
            .all()
        )

        return [
            {
                "id": e.id,
                "type": e.event_type,
                "description": e.change_description,
                "rationale": e.rationale,
                "status": e.status,
                "baseline_metric": e.baseline_metric,
                "new_metric": e.new_metric,
                "improvement": e.improvement,
                "implemented_at": e.implemented_at.isoformat() if e.implemented_at else None,
                "evaluated_at": e.evaluated_at.isoformat() if e.evaluated_at else None,
                "rolled_back_at": e.rolled_back_at.isoformat() if e.rolled_back_at else None,
                "rollback_reason": e.rollback_reason,
            }
            for e in events
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
