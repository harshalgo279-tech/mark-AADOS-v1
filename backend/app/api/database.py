from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session
from typing import Any, Dict, Set
import re

from app.database import get_db
from app.utils.logger import logger
from app.auth.dependencies import require_admin
from app.auth.models import UserInDB

router = APIRouter(prefix="/api/database", tags=["database"])

# Security: Valid SQL identifier pattern (letters, numbers, underscores only)
VALID_IDENTIFIER_PATTERN = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')


def _validate_table_name(table_name: str, allowed_tables: Set[str]) -> str:
    """
    Validate table name against whitelist and pattern to prevent SQL injection.

    Args:
        table_name: The table name to validate
        allowed_tables: Set of allowed table names from database inspector

    Returns:
        The validated table name

    Raises:
        HTTPException: If table name is invalid or not in allowed list
    """
    # Check against whitelist first
    if table_name not in allowed_tables:
        raise HTTPException(status_code=404, detail="Table not found")

    # Additional safety: validate identifier pattern
    if not VALID_IDENTIFIER_PATTERN.match(table_name):
        logger.warning(f"Invalid table name format attempted: {table_name}")
        raise HTTPException(status_code=400, detail="Invalid table name format")

    return table_name


@router.get("/tables")
async def get_tables(
    admin_user: UserInDB = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """List all database tables. Admin only."""
    try:
        inspector = inspect(db.bind)
        logger.info(f"Admin {admin_user.email} listed database tables")
        return {"tables": inspector.get_table_names()}
    except Exception as e:
        logger.error(f"Error getting tables: {str(e)[:100]}")
        raise HTTPException(status_code=500, detail="Database error")


@router.get("/table/{table_name}")
async def get_table_data(
    table_name: str,
    limit: int = 50,
    admin_user: UserInDB = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Get data from a specific table. Admin only."""
    try:
        inspector = inspect(db.bind)
        allowed_tables = set(inspector.get_table_names())

        # Validate table name to prevent SQL injection
        validated_name = _validate_table_name(table_name, allowed_tables)

        columns = [c["name"] for c in inspector.get_columns(validated_name)]

        # Use double quotes for PostgreSQL identifier quoting
        q = text(f'SELECT * FROM "{validated_name}" LIMIT :limit')
        rows = db.execute(q, {"limit": limit}).fetchall()

        data = [dict(zip(columns, row)) for row in rows]
        logger.info(f"Admin {admin_user.email} queried table {validated_name}")
        return {"table": validated_name, "columns": columns, "data": data}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting table data: {str(e)[:100]}")
        raise HTTPException(status_code=500, detail="Database error")


@router.get("/stats")
async def get_database_stats(
    admin_user: UserInDB = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Get row counts for all tables. Admin only."""
    try:
        inspector = inspect(db.bind)
        tables = inspector.get_table_names()
        allowed_tables = set(tables)
        stats: Dict[str, Any] = {}

        for t in tables:
            # Validate each table name for safety
            validated_name = _validate_table_name(t, allowed_tables)
            # Use double quotes for PostgreSQL identifier quoting
            q = text(f'SELECT COUNT(*) as c FROM "{validated_name}"')
            stats[validated_name] = db.execute(q).scalar()

        logger.info(f"Admin {admin_user.email} queried database stats")
        return {"tables": stats}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting DB stats: {str(e)[:100]}")
        raise HTTPException(status_code=500, detail="Database error")
