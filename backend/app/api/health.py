# backend/app/api/health.py
"""
Health Check Endpoints for All Integrations

Provides detailed health status for:
- Database (MySQL)
- Twilio API
- OpenAI API
- OpenAI Realtime WebSocket
- SMTP Email Service
- Webhook URL accessibility

These endpoints help monitor system health and diagnose integration issues.
"""

from datetime import datetime
from typing import Dict, Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
import httpx

from app.config import settings
from app.database import get_db
from app.utils.logger import logger

router = APIRouter(prefix="/api/health", tags=["health"])


async def check_database(db: Session) -> Dict[str, Any]:
    """Check MySQL database connectivity"""
    try:
        from sqlalchemy import text
        # Simple query to test connection
        result = db.execute(text("SELECT 1 as test")).fetchone()
        return {
            "status": "healthy" if result else "unhealthy",
            "message": "Database connection successful",
            "details": {"test_query": "passed"}
        }
    except Exception as e:
        logger.error(f"[Health Check] Database failed: {e}")
        return {
            "status": "unhealthy",
            "message": f"Database connection failed: {str(e)}",
            "details": {"error": str(e)}
        }


async def check_twilio() -> Dict[str, Any]:
    """Check Twilio API connectivity and credentials"""
    try:
        account_sid = getattr(settings, "TWILIO_ACCOUNT_SID", None)
        auth_token = getattr(settings, "TWILIO_AUTH_TOKEN", None)
        phone_number = getattr(settings, "TWILIO_PHONE_NUMBER", None)

        if not account_sid or not auth_token:
            return {
                "status": "unconfigured",
                "message": "Twilio credentials not configured",
                "details": {
                    "account_sid_configured": bool(account_sid),
                    "auth_token_configured": bool(auth_token),
                    "phone_number_configured": bool(phone_number)
                }
            }

        # Test API connectivity by fetching account info
        url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}.json"
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, auth=(account_sid, auth_token))

            if response.status_code == 200:
                data = response.json()
                return {
                    "status": "healthy",
                    "message": "Twilio API accessible",
                    "details": {
                        "account_sid": account_sid,
                        "phone_number": phone_number,
                        "account_status": data.get("status"),
                        "account_type": data.get("type")
                    }
                }
            else:
                return {
                    "status": "unhealthy",
                    "message": f"Twilio API returned {response.status_code}",
                    "details": {
                        "status_code": response.status_code,
                        "error": response.text[:200]
                    }
                }

    except Exception as e:
        logger.error(f"[Health Check] Twilio failed: {e}")
        return {
            "status": "unhealthy",
            "message": f"Twilio check failed: {str(e)}",
            "details": {"error": str(e)}
        }


async def check_openai() -> Dict[str, Any]:
    """Check OpenAI API connectivity and credentials"""
    try:
        api_key = getattr(settings, "OPENAI_API_KEY", None)

        if not api_key:
            return {
                "status": "unconfigured",
                "message": "OpenAI API key not configured",
                "details": {}
            }

        # Test API by listing models (lightweight endpoint)
        url = "https://api.openai.com/v1/models"
        headers = {"Authorization": f"Bearer {api_key}"}

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers=headers)

            if response.status_code == 200:
                data = response.json()
                model_count = len(data.get("data", []))
                return {
                    "status": "healthy",
                    "message": "OpenAI API accessible",
                    "details": {
                        "api_key_configured": True,
                        "models_available": model_count,
                        "primary_model": getattr(settings, "OPENAI_MODEL", "gpt-4o-mini")
                    }
                }
            else:
                return {
                    "status": "unhealthy",
                    "message": f"OpenAI API returned {response.status_code}",
                    "details": {
                        "status_code": response.status_code,
                        "error": response.text[:200]
                    }
                }

    except Exception as e:
        logger.error(f"[Health Check] OpenAI failed: {e}")
        return {
            "status": "unhealthy",
            "message": f"OpenAI check failed: {str(e)}",
            "details": {"error": str(e)}
        }


async def check_openai_realtime() -> Dict[str, Any]:
    """Check OpenAI Realtime configuration"""
    try:
        api_key = getattr(settings, "OPENAI_API_KEY", None)
        enabled = getattr(settings, "OPENAI_REALTIME_ENABLED", False)
        model = getattr(settings, "OPENAI_REALTIME_MODEL", "gpt-4o-realtime-preview")

        if not api_key:
            return {
                "status": "unconfigured",
                "message": "OpenAI API key not configured",
                "details": {}
            }

        # Note: We don't actually connect to WebSocket here (too expensive for health checks)
        # Just verify configuration
        return {
            "status": "configured" if enabled else "disabled",
            "message": "OpenAI Realtime configured" if enabled else "OpenAI Realtime disabled",
            "details": {
                "enabled": enabled,
                "model": model,
                "api_key_configured": bool(api_key)
            }
        }

    except Exception as e:
        logger.error(f"[Health Check] OpenAI Realtime failed: {e}")
        return {
            "status": "error",
            "message": f"OpenAI Realtime check failed: {str(e)}",
            "details": {"error": str(e)}
        }


async def check_smtp() -> Dict[str, Any]:
    """Check SMTP email service configuration"""
    try:
        smtp_host = getattr(settings, "SMTP_HOST", None)
        smtp_port = getattr(settings, "SMTP_PORT", None)
        smtp_user = getattr(settings, "SMTP_USER", None)
        smtp_password = getattr(settings, "SMTP_PASSWORD", None)

        configured = bool(smtp_host and smtp_user and smtp_password)

        if not configured:
            return {
                "status": "unconfigured",
                "message": "SMTP not fully configured",
                "details": {
                    "smtp_host_configured": bool(smtp_host),
                    "smtp_user_configured": bool(smtp_user),
                    "smtp_password_configured": bool(smtp_password),
                    "smtp_port": smtp_port
                }
            }

        # Note: We don't actually connect to SMTP here (avoid rate limiting)
        # Just verify configuration
        return {
            "status": "configured",
            "message": "SMTP configured",
            "details": {
                "smtp_host": smtp_host,
                "smtp_port": smtp_port,
                "smtp_user": smtp_user,
                "from_email": getattr(settings, "EMAIL_FROM", smtp_user)
            }
        }

    except Exception as e:
        logger.error(f"[Health Check] SMTP failed: {e}")
        return {
            "status": "error",
            "message": f"SMTP check failed: {str(e)}",
            "details": {"error": str(e)}
        }


async def check_webhook_url() -> Dict[str, Any]:
    """Check Twilio webhook URL accessibility"""
    try:
        webhook_url = getattr(settings, "TWILIO_WEBHOOK_URL", None)

        if not webhook_url:
            return {
                "status": "unconfigured",
                "message": "Webhook URL not configured",
                "details": {}
            }

        # Test if webhook URL is accessible
        health_url = f"{webhook_url.rstrip('/')}/health"

        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(health_url)

            if response.status_code == 200:
                return {
                    "status": "healthy",
                    "message": "Webhook URL accessible",
                    "details": {
                        "webhook_url": webhook_url,
                        "health_endpoint": health_url,
                        "status_code": response.status_code
                    }
                }
            else:
                return {
                    "status": "warning",
                    "message": f"Webhook URL returned {response.status_code}",
                    "details": {
                        "webhook_url": webhook_url,
                        "status_code": response.status_code
                    }
                }

    except Exception as e:
        logger.error(f"[Health Check] Webhook URL failed: {e}")
        return {
            "status": "unhealthy",
            "message": f"Webhook URL not accessible: {str(e)}",
            "details": {
                "webhook_url": getattr(settings, "TWILIO_WEBHOOK_URL", None),
                "error": str(e)
            }
        }


@router.get("")
@router.get("/")
async def health_check_all(db: Session = Depends(get_db)):
    """
    Comprehensive health check for all integrations.

    Returns detailed status for:
    - Database
    - Twilio API
    - OpenAI API
    - OpenAI Realtime
    - SMTP
    - Webhook URL

    Status values:
    - healthy: Fully operational
    - configured: Configured but not tested
    - unconfigured: Missing configuration
    - unhealthy: Connection failed
    - error: Unexpected error
    """
    results = {
        "timestamp": datetime.utcnow().isoformat(),
        "overall_status": "unknown",
        "integrations": {}
    }

    # Run all checks
    results["integrations"]["database"] = await check_database(db)
    results["integrations"]["twilio"] = await check_twilio()
    results["integrations"]["openai"] = await check_openai()
    results["integrations"]["openai_realtime"] = await check_openai_realtime()
    results["integrations"]["smtp"] = await check_smtp()
    results["integrations"]["webhook_url"] = await check_webhook_url()

    # Determine overall status
    statuses = [check["status"] for check in results["integrations"].values()]

    if all(s in ("healthy", "configured", "disabled") for s in statuses):
        results["overall_status"] = "healthy"
    elif any(s == "unhealthy" for s in statuses):
        results["overall_status"] = "unhealthy"
    elif any(s == "unconfigured" for s in statuses):
        results["overall_status"] = "partially_configured"
    else:
        results["overall_status"] = "degraded"

    return results


@router.get("/database")
async def health_check_database(db: Session = Depends(get_db)):
    """Check database health only"""
    return await check_database(db)


@router.get("/twilio")
async def health_check_twilio():
    """Check Twilio API health only"""
    return await check_twilio()


@router.get("/openai")
async def health_check_openai():
    """Check OpenAI API health only"""
    return await check_openai()


@router.get("/openai-realtime")
async def health_check_openai_realtime():
    """Check OpenAI Realtime configuration only"""
    return await check_openai_realtime()


@router.get("/smtp")
async def health_check_smtp():
    """Check SMTP configuration only"""
    return await check_smtp()


@router.get("/webhook-url")
async def health_check_webhook_url():
    """Check webhook URL accessibility only"""
    return await check_webhook_url()
