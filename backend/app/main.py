import logging
from fastapi import FastAPI, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import Base, engine, get_db

from app.api import (
    leads,
    data_packets,
    calls,
    reports,
    database,
    manual_call,
    websocket,
    analyst,
    agent_config,  # Sales control plane config
    emails,  # Email tracking and management
    email_intelligence,  # AI-powered email optimization
)

# Rate limiting
from app.utils.rate_limit import get_limiter, RATE_LIMITING_AVAILABLE
try:
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded
except ImportError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("app.main")

app = FastAPI(title="Algonox AADOS Backend", version="1.0.0")

# Configure rate limiting
if RATE_LIMITING_AVAILABLE:
    limiter = get_limiter()
    if limiter:
        app.state.limiter = limiter
        app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
        logger.info("Rate limiting enabled")
else:
    logger.warning("Rate limiting disabled - install slowapi: pip install slowapi")


@app.on_event("startup")
async def startup_event():
    logger.info("Algonox AADOS Backend Starting...")

    # Validate configuration (don't raise in dev mode)
    from app.config import validate_config, ConfigValidationError

    try:
        result = validate_config(raise_on_error=settings.ENVIRONMENT == "production")
        for warning in result.get("warnings", []):
            logger.warning(f"Config warning: {warning}")
        if result.get("errors"):
            for error in result["errors"]:
                logger.error(f"Config error: {error}")
    except ConfigValidationError as e:
        logger.critical(f"FATAL: {e}")
        raise SystemExit(1)

    # Create database tables
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created/verified")

    # Start email scheduler
    try:
        from app.services.email_scheduler import start_email_scheduler
        await start_email_scheduler()
        logger.info("Email scheduler started")
    except Exception as e:
        logger.error(f"Failed to start email scheduler: {e}")

    logger.info("Algonox AADOS Backend Started")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup resources on shutdown."""
    logger.info("Algonox AADOS Backend Shutting Down...")

    # Stop email scheduler
    try:
        from app.services.email_scheduler import stop_email_scheduler
        stop_email_scheduler()
        logger.info("Email scheduler stopped")
    except Exception as e:
        logger.error(f"Error stopping email scheduler: {e}")

    # Cleanup active monitors
    try:
        from app.services.realtime_monitor import cleanup_all_monitors
        monitor_count = await cleanup_all_monitors()
        if monitor_count > 0:
            logger.info(f"Cleaned up {monitor_count} active monitors")
    except Exception as e:
        logger.error(f"Error cleaning up monitors: {e}")

    # Cleanup conversation trackers
    try:
        from app.agents.sales_control_plane import cleanup_all_trackers
        tracker_count = await cleanup_all_trackers()
        if tracker_count > 0:
            logger.info(f"Cleaned up {tracker_count} conversation trackers")
    except Exception as e:
        logger.error(f"Error cleaning up trackers: {e}")

    logger.info("Algonox AADOS Backend Shutdown Complete")


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(leads.router)
app.include_router(data_packets.router)
app.include_router(calls.router)
app.include_router(reports.router)
app.include_router(database.router)
app.include_router(manual_call.router)
app.include_router(websocket.router)
app.include_router(analyst.router)
app.include_router(agent_config.router)  # Sales control plane config
app.include_router(emails.router)  # Email tracking and management
app.include_router(email_intelligence.router)  # AI-powered email optimization


@app.get("/")
async def root():
    return {"message": "Algonox AADOS API", "status": "running", "version": "1.0.0"}


@app.get("/health")
async def health(db: Session = Depends(get_db)):
    """
    Comprehensive health check endpoint.

    Returns status of all system components including:
    - Database connectivity
    - Configuration status
    - Active monitors/connections
    """
    from datetime import datetime
    from sqlalchemy import text
    from app.config import get_config_status
    from app.agents.sales_control_plane import get_tracker_count
    from app.services.realtime_monitor import get_active_monitor_count

    health_status = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0",
        "checks": {},
    }

    # Database check
    try:
        db.execute(text("SELECT 1"))
        health_status["checks"]["database"] = "ok"
    except Exception as e:
        health_status["checks"]["database"] = f"error: {str(e)[:100]}"
        health_status["status"] = "degraded"

    # Configuration status
    config_status = get_config_status()
    health_status["checks"]["config"] = config_status

    # Active resources
    health_status["checks"]["active_trackers"] = get_tracker_count()
    health_status["checks"]["active_monitors"] = get_active_monitor_count()

    # WebSocket connections (if available)
    try:
        from app.api.websocket import manager
        health_status["checks"]["websocket_connections"] = len(manager.active_connections)
    except Exception:
        health_status["checks"]["websocket_connections"] = "unknown"

    # Overall status
    if not config_status.get("database_configured"):
        health_status["status"] = "unhealthy"
    elif not config_status.get("twilio_configured") or not config_status.get("elevenlabs_configured"):
        health_status["status"] = "degraded"

    return health_status


@app.get("/health/simple")
async def health_simple():
    """Simple health check for load balancers."""
    return {"status": "ok"}