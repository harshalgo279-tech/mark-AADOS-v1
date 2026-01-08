# backend/app/config.py
import os
from pathlib import Path
from dotenv import load_dotenv
from urllib.parse import quote_plus

# ✅ Locate .env in backend/ first, else repo root
BACKEND_DIR = Path(__file__).resolve().parents[1]   # backend/
REPO_DIR = BACKEND_DIR.parent                        # repo root

ENV_BACKEND = BACKEND_DIR / ".env"
ENV_REPO = REPO_DIR / ".env"
ENV_FILE = ENV_BACKEND if ENV_BACKEND.exists() else ENV_REPO

load_dotenv(dotenv_path=str(ENV_FILE), override=True)


def _build_mysql_url() -> str:
    host = os.getenv("MYSQL_HOST", "127.0.0.1")
    port = os.getenv("MYSQL_PORT", "3306")
    user = os.getenv("MYSQL_USER", "root")
    password_raw = os.getenv("MYSQL_PASSWORD", "")
    db = os.getenv("MYSQL_DATABASE", "algonox_aados")
    password = quote_plus(password_raw)
    return f"mysql+pymysql://{user}:{password}@{host}:{port}/{db}?charset=utf8mb4"


class Settings:
    # ✅ DB
    DATABASE_URL: str = _build_mysql_url()

    # ✅ APIs
    OPENAI_API_KEY: str | None = os.getenv("OPENAI_API_KEY")

    TWILIO_ACCOUNT_SID: str | None = os.getenv("TWILIO_ACCOUNT_SID")
    TWILIO_AUTH_TOKEN: str | None = os.getenv("TWILIO_AUTH_TOKEN")
    TWILIO_PHONE_NUMBER: str | None = os.getenv("TWILIO_PHONE_NUMBER")
    TWILIO_WEBHOOK_URL: str | None = os.getenv("TWILIO_WEBHOOK_URL")

    # ✅ PDF output directory (Windows absolute path supported)
    PDF_OUTPUT_DIR: str | None = os.getenv("PDF_OUTPUT_DIR")

    # ✅ CORS
    CORS_ORIGINS: list[str] = os.getenv(
        "CORS_ORIGINS",
        "http://127.0.0.1:5173,http://localhost:5173,http://127.0.0.1:3000,http://localhost:3000",
    ).split(",")

    SMTP_HOST: str | None = os.getenv("SMTP_HOST")
    SMTP_PORT: int | None = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: str | None = os.getenv("SMTP_USER")
    SMTP_PASSWORD: str | None = os.getenv("SMTP_PASSWORD")
    SMTP_TLS: bool | None = os.getenv("SMTP_TLS") == "True"
    EMAIL_FROM: str | None = os.getenv("EMAIL_FROM")
    EMAIL_FROM_NAME: str | None = os.getenv("EMAIL_FROM_NAME")
    # Comma-separated BD recipients, e.g. bd1@example.com,bd2@example.com
    BD_EMAIL_TO: str | None = os.getenv("BD_EMAIL_TO")


settings = Settings()

print(f">>> .env loaded from: {ENV_FILE}")
print(f">>> DATABASE_URL in use: {settings.DATABASE_URL}")
print(f">>> PDF_OUTPUT_DIR in use: {settings.PDF_OUTPUT_DIR}")
