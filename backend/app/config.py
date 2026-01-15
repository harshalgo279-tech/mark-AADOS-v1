# backend/app/config.py
import os
from pathlib import Path
from dotenv import load_dotenv
from urllib.parse import quote_plus

BACKEND_DIR = Path(__file__).resolve().parents[1]   # backend/
REPO_DIR = BACKEND_DIR.parent                        # repo root

ENV_BACKEND = BACKEND_DIR / ".env"
ENV_REPO = REPO_DIR / ".env"
ENV_FILE = ENV_BACKEND if ENV_BACKEND.exists() else ENV_REPO

load_dotenv(dotenv_path=str(ENV_FILE), override=True)


def _build_database_url() -> str:
    """Build PostgreSQL URL for Supabase or use DATABASE_URL directly."""
    # Check for direct DATABASE_URL first (Render/Supabase style)
    direct_url = os.getenv("DATABASE_URL")
    if direct_url:
        return direct_url

    # Fallback to individual components (PostgreSQL)
    host = os.getenv("DB_HOST", "127.0.0.1")
    port = os.getenv("DB_PORT", "5432")
    user = os.getenv("DB_USER", "postgres")
    password_raw = os.getenv("DB_PASSWORD", "")
    db = os.getenv("DB_NAME", "postgres")
    password = quote_plus(password_raw)
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


def _parse_origins(raw: str) -> list[str]:
    # split, strip, drop empties, drop trailing slashes
    out = []
    for o in (raw or "").split(","):
        o = (o or "").strip().rstrip("/")
        if o:
            out.append(o)
    return out


class Settings:
    DATABASE_URL: str = _build_database_url()

    OPENAI_API_KEY: str | None = os.getenv("OPENAI_API_KEY")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    TWILIO_ACCOUNT_SID: str | None = os.getenv("TWILIO_ACCOUNT_SID")
    TWILIO_AUTH_TOKEN: str | None = os.getenv("TWILIO_AUTH_TOKEN")
    TWILIO_PHONE_NUMBER: str | None = os.getenv("TWILIO_PHONE_NUMBER")
    TWILIO_WEBHOOK_URL: str | None = os.getenv("TWILIO_WEBHOOK_URL")

    # ================= ElevenLabs Configuration =================
    # API key for ElevenLabs services
    ELEVENLABS_API_KEY: str | None = os.getenv("ELEVENLABS_API_KEY")

    # Agent ID for the configured sales agent
    ELEVENLABS_AGENT_ID: str | None = os.getenv("ELEVENLABS_AGENT_ID")

    # Webhook secret for verifying post-call webhooks
    ELEVENLABS_WEBHOOK_SECRET: str | None = os.getenv("ELEVENLABS_WEBHOOK_SECRET")

    # Voice ID for TTS (optional, uses agent default if not set)
    ELEVENLABS_VOICE_ID: str | None = os.getenv("ELEVENLABS_VOICE_ID")

    # Post-call webhook URL (for configuration reference)
    ELEVENLABS_POST_CALL_WEBHOOK_URL: str | None = os.getenv("ELEVENLABS_POST_CALL_WEBHOOK_URL")

    # Phone number ID for ElevenLabs outbound calls (enables real-time transcript streaming)
    # Get this from ElevenLabs Dashboard > Phone Numbers after importing your Twilio number
    ELEVENLABS_PHONE_NUMBER_ID: str | None = os.getenv("ELEVENLABS_PHONE_NUMBER_ID")

    # ================= Firecrawl Configuration =================
    FIRECRAWL_API_KEY: str | None = os.getenv("FIRECRAWL_API_KEY")

    # IMPORTANT: keep localhost + 127.0.0.1 for Vite dev
    CORS_ORIGINS: list[str] = _parse_origins(
        os.getenv(
            "CORS_ORIGINS",
            "http://127.0.0.1:5173,http://localhost:5173,http://127.0.0.1:3000,http://localhost:3000",
        )
    )

    SMTP_HOST: str | None = os.getenv("SMTP_HOST")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: str | None = os.getenv("SMTP_USER")
    SMTP_PASSWORD: str | None = os.getenv("SMTP_PASSWORD")
    SMTP_TLS: bool = os.getenv("SMTP_TLS") == "True"
    EMAIL_FROM: str | None = os.getenv("EMAIL_FROM")
    EMAIL_FROM_NAME: str | None = os.getenv("EMAIL_FROM_NAME")
    EMAIL_SENDER_NAME: str = os.getenv("EMAIL_SENDER_NAME", "Harsha")
    EMAIL_SENDER_TITLE: str = os.getenv("EMAIL_SENDER_TITLE", "Business Development")
    EMAIL_REPLY_TO: str | None = os.getenv("EMAIL_REPLY_TO")
    BD_EMAIL_TO: str | None = os.getenv("BD_EMAIL_TO")

    # Email environment: production, staging, test
    # test: logs emails instead of sending
    # staging: sends only to test addresses
    EMAIL_ENVIRONMENT: str = os.getenv("EMAIL_ENVIRONMENT", "production")
    EMAIL_TEST_RECIPIENT: str | None = os.getenv("EMAIL_TEST_RECIPIENT")  # For staging mode

    # Email throttling: max emails per hour per sender
    EMAIL_MAX_PER_HOUR: int = int(os.getenv("EMAIL_MAX_PER_HOUR", "50"))

    # Company address for email footer (CAN-SPAM compliance)
    COMPANY_ADDRESS: str = os.getenv(
        "COMPANY_ADDRESS",
        "Algonox Technologies | Hyderabad, India"
    )

    # Base URL for email tracking and unsubscribe links
    EMAIL_TRACKING_BASE_URL: str | None = os.getenv("EMAIL_TRACKING_BASE_URL")

    # ================= Demo Scheduling Configuration =================
    # Placeholder demo scheduling link (replace with actual Calendly/Cal.com link)
    DEMO_SCHEDULING_LINK: str = os.getenv(
        "DEMO_SCHEDULING_LINK",
        "https://calendly.com/algonox/demo"  # Placeholder - update with actual link
    )

    # ================= Algonox Company Information =================
    # Used in automated emails for company description
    ALGONOX_COMPANY_NAME: str = os.getenv("ALGONOX_COMPANY_NAME", "Algonox")
    ALGONOX_COMPANY_DESCRIPTION: str = os.getenv(
        "ALGONOX_COMPANY_DESCRIPTION",
        """Algonox is a leading AI solutions provider specializing in enterprise automation and intelligent agents.
We help businesses transform their operations through cutting-edge AI technology, delivering measurable ROI
through process automation, intelligent assistants, and data-driven insights.

Our core services include:
- AI-Powered Process Automation: Streamline repetitive workflows and reduce operational costs
- Intelligent Virtual Agents: Deploy conversational AI for customer service, sales, and internal support
- Knowledge Management Solutions: Extract insights from documents, calls, and data sources
- Custom AI Development: Tailored solutions for unique business challenges

With a proven track record across industries including healthcare, finance, retail, and manufacturing,
Algonox combines deep technical expertise with practical business acumen to deliver solutions that
drive real results."""
    )


    # ================= Environment Configuration =================
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")

    # ================= Authentication Configuration =================
    # JWT secret key - MUST be set in production via environment variable
    # Generate with: python -c "import secrets; print(secrets.token_urlsafe(32))"
    JWT_SECRET_KEY: str | None = os.getenv("JWT_SECRET_KEY")

    # Access token expiration in minutes (default: 24 hours)
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))

    # Initial admin user (created on first startup if not exists)
    ADMIN_EMAIL: str | None = os.getenv("ADMIN_EMAIL")
    ADMIN_PASSWORD: str | None = os.getenv("ADMIN_PASSWORD")

    # ================= Configurable Values (moved from hardcoded) =================
    MAX_CALL_DURATION_SECONDS: int = int(os.getenv("MAX_CALL_DURATION_SECONDS", "600"))
    ELEVENLABS_LLM_MODEL: str = os.getenv("ELEVENLABS_LLM_MODEL", "gpt-4o")
    ELEVENLABS_LLM_TEMPERATURE: float = float(os.getenv("ELEVENLABS_LLM_TEMPERATURE", "0.7"))
    ELEVENLABS_LLM_MAX_TOKENS: int = int(os.getenv("ELEVENLABS_LLM_MAX_TOKENS", "300"))
    REALTIME_POLL_INTERVAL: float = float(os.getenv("REALTIME_POLL_INTERVAL", "2.0"))
    QUESTION_SIMILARITY_THRESHOLD: float = float(os.getenv("QUESTION_SIMILARITY_THRESHOLD", "0.5"))


settings = Settings()


# =============================================================================
# CONFIGURATION VALIDATION
# =============================================================================

class ConfigValidationError(Exception):
    """Raised when required configuration is missing or invalid."""
    pass


def validate_config(raise_on_error: bool = True) -> dict:
    """
    Validate all configuration settings.

    Args:
        raise_on_error: If True, raises ConfigValidationError on critical errors.
                       If False, returns dict with errors and warnings.

    Returns:
        Dict with 'errors' (critical) and 'warnings' (non-critical) lists.

    Raises:
        ConfigValidationError: If raise_on_error=True and critical errors found.
    """
    errors = []
    warnings = []

    # Critical - App won't function
    if not settings.DATABASE_URL:
        errors.append("DATABASE_URL is required")

    # Required for core call functionality
    if not settings.TWILIO_ACCOUNT_SID:
        errors.append("TWILIO_ACCOUNT_SID is required for making calls")
    if not settings.TWILIO_AUTH_TOKEN:
        errors.append("TWILIO_AUTH_TOKEN is required for making calls")
    if not settings.TWILIO_PHONE_NUMBER:
        errors.append("TWILIO_PHONE_NUMBER is required for outbound calls")

    # Required for voice agent
    if not settings.ELEVENLABS_API_KEY:
        errors.append("ELEVENLABS_API_KEY is required for voice agent")
    if not settings.ELEVENLABS_AGENT_ID:
        errors.append("ELEVENLABS_AGENT_ID is required for voice agent")

    # Warnings - Degraded functionality
    if not settings.OPENAI_API_KEY:
        warnings.append("OPENAI_API_KEY missing - AI analysis features may be limited")
    if not settings.SMTP_HOST:
        warnings.append("SMTP_HOST missing - email features disabled")
    if not settings.ELEVENLABS_WEBHOOK_SECRET:
        warnings.append("ELEVENLABS_WEBHOOK_SECRET missing - webhook verification disabled")
    if not settings.ELEVENLABS_PHONE_NUMBER_ID:
        warnings.append("ELEVENLABS_PHONE_NUMBER_ID missing - using legacy call flow")
    if not settings.FIRECRAWL_API_KEY:
        warnings.append("FIRECRAWL_API_KEY missing - web scraping disabled")

    # Production-specific warnings
    if settings.ENVIRONMENT == "production":
        if not settings.CORS_ORIGINS or any("localhost" in o for o in settings.CORS_ORIGINS):
            warnings.append("CORS_ORIGINS includes localhost in production - consider restricting")
        if not settings.TWILIO_WEBHOOK_URL:
            warnings.append("TWILIO_WEBHOOK_URL not set in production")
        if not settings.ELEVENLABS_POST_CALL_WEBHOOK_URL:
            warnings.append("ELEVENLABS_POST_CALL_WEBHOOK_URL not set in production")

    result = {"errors": errors, "warnings": warnings}

    if raise_on_error and errors:
        raise ConfigValidationError(f"Configuration errors: {'; '.join(errors)}")

    return result


def get_config_status() -> dict:
    """
    Get configuration status for health check endpoints.

    Returns:
        Dict with configuration presence and validation status.
    """
    return {
        "environment": settings.ENVIRONMENT,
        "database_configured": bool(settings.DATABASE_URL),
        "twilio_configured": all([
            settings.TWILIO_ACCOUNT_SID,
            settings.TWILIO_AUTH_TOKEN,
            settings.TWILIO_PHONE_NUMBER,
        ]),
        "elevenlabs_configured": all([
            settings.ELEVENLABS_API_KEY,
            settings.ELEVENLABS_AGENT_ID,
        ]),
        "elevenlabs_outbound_configured": all([
            settings.ELEVENLABS_API_KEY,
            settings.ELEVENLABS_AGENT_ID,
            settings.ELEVENLABS_PHONE_NUMBER_ID,
        ]),
        "openai_configured": bool(settings.OPENAI_API_KEY),
        "smtp_configured": bool(settings.SMTP_HOST),
        "firecrawl_configured": bool(settings.FIRECRAWL_API_KEY),
        "webhook_security_enabled": bool(settings.ELEVENLABS_WEBHOOK_SECRET),
    }


# Log configuration on import (development only)
# SECURITY: Never log credentials or connection strings
if settings.ENVIRONMENT != "production":
    def _mask_url(url: str) -> str:
        """Mask sensitive parts of URLs for safe logging."""
        if not url:
            return "[not set]"
        # Mask password in database URLs
        import re
        masked = re.sub(r'://([^:]+):([^@]+)@', r'://\1:****@', url)
        return masked

    print(f">>> .env loaded from: {ENV_FILE}")
    print(f">>> DATABASE_URL configured: {bool(settings.DATABASE_URL)}")
    print(f">>> CORS_ORIGINS in use: {settings.CORS_ORIGINS}")
    print(f">>> FIRECRAWL_API_KEY present: {bool(os.getenv('FIRECRAWL_API_KEY'))}")
    print(f">>> ELEVENLABS_API_KEY present: {bool(settings.ELEVENLABS_API_KEY)}")
    print(f">>> ELEVENLABS_AGENT_ID present: {bool(settings.ELEVENLABS_AGENT_ID)}")
    print(f">>> JWT_SECRET_KEY configured: {bool(settings.JWT_SECRET_KEY)}")

