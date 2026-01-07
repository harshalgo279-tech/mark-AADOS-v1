"""Compatibility router.

Some frontend components call endpoints under `/api/dashboard/...` while
newer code uses `/api/reports/...`. To keep both UIs working without
touching the frontend, we expose `/api/dashboard` as thin wrappers.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.api.reports import (
    dashboard as get_dashboard_stats,
    funnel as get_sales_funnel,
    activity as get_recent_activity,
    call_stats as get_call_stats,
)

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/stats")
async def stats(db: Session = Depends(get_db)):
    return await get_dashboard_stats(db)


@router.get("/funnel")
async def funnel(db: Session = Depends(get_db)):
    return await get_sales_funnel(db)


@router.get("/activity")
async def activity(limit: int = 10, db: Session = Depends(get_db)):
    return await get_recent_activity(limit=limit, db=db)


@router.get("/call-stats")
async def call_stats(db: Session = Depends(get_db)):
    return await get_call_stats(db)
