# backend/app/database.py
import logging
from contextlib import contextmanager
from typing import Generator, Optional, Tuple

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from sqlalchemy.exc import SQLAlchemyError, IntegrityError, OperationalError

from app.config import settings  # OK: config should NOT import app.database

logger = logging.getLogger(__name__)

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=3600,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_db_context() -> Generator[Session, None, None]:
    """
    Context manager for database sessions.

    Usage:
        with get_db_context() as db:
            db.query(...)
            db.commit()

    Automatically handles session cleanup on exit.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def safe_commit(db: Session, operation: str = "database operation") -> Tuple[bool, Optional[str]]:
    """
    Safely commit a database transaction with rollback on failure.

    Args:
        db: SQLAlchemy Session
        operation: Description of the operation for logging

    Returns:
        Tuple of (success: bool, error_message: Optional[str])

    Usage:
        db.add(model)
        success, error = safe_commit(db, "create lead")
        if not success:
            logger.error(f"Failed to create lead: {error}")
            raise HTTPException(status_code=500, detail=error)
    """
    try:
        db.commit()
        return True, None
    except IntegrityError as e:
        db.rollback()
        error_msg = f"Integrity error during {operation}: {str(e.orig)[:200]}"
        logger.error(error_msg)
        return False, error_msg
    except OperationalError as e:
        db.rollback()
        error_msg = f"Database operational error during {operation}: {str(e.orig)[:200]}"
        logger.error(error_msg)
        return False, error_msg
    except SQLAlchemyError as e:
        db.rollback()
        error_msg = f"Database error during {operation}: {str(e)[:200]}"
        logger.error(error_msg)
        return False, error_msg
    except Exception as e:
        db.rollback()
        error_msg = f"Unexpected error during {operation}: {str(e)[:200]}"
        logger.error(error_msg)
        return False, error_msg


def safe_refresh(db: Session, instance, operation: str = "refresh") -> Tuple[bool, Optional[str]]:
    """
    Safely refresh an instance from the database.

    Args:
        db: SQLAlchemy Session
        instance: Model instance to refresh
        operation: Description for logging

    Returns:
        Tuple of (success: bool, error_message: Optional[str])
    """
    try:
        db.refresh(instance)
        return True, None
    except SQLAlchemyError as e:
        error_msg = f"Database error during {operation}: {str(e)[:200]}"
        logger.error(error_msg)
        return False, error_msg
    except Exception as e:
        error_msg = f"Unexpected error during {operation}: {str(e)[:200]}"
        logger.error(error_msg)
        return False, error_msg
