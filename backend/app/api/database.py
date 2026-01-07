from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session
from typing import Any, Dict

from app.database import get_db
from app.utils.logger import logger

router = APIRouter(prefix="/api/database", tags=["database"])


@router.get("/tables")
async def get_tables(db: Session = Depends(get_db)):
    try:
        inspector = inspect(db.bind)
        return {"tables": inspector.get_table_names()}
    except Exception as e:
        logger.error(f"Error getting tables: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/table/{table_name}")
async def get_table_data(table_name: str, limit: int = 50, db: Session = Depends(get_db)):
    try:
        inspector = inspect(db.bind)
        if table_name not in inspector.get_table_names():
            raise HTTPException(status_code=404, detail="Table not found")

        columns = [c["name"] for c in inspector.get_columns(table_name)]
        q = text(f"SELECT * FROM {table_name} LIMIT :limit")
        rows = db.execute(q, {"limit": limit}).fetchall()

        data = [dict(zip(columns, row)) for row in rows]
        return {"table": table_name, "columns": columns, "data": data}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting table data: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def get_database_stats(db: Session = Depends(get_db)):
    try:
        inspector = inspect(db.bind)
        tables = inspector.get_table_names()
        stats: Dict[str, Any] = {}

        for t in tables:
            q = text(f"SELECT COUNT(*) as c FROM {t}")
            stats[t] = db.execute(q).scalar()

        return {"tables": stats}

    except Exception as e:
        logger.error(f"Error getting DB stats: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
