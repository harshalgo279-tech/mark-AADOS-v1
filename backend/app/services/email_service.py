# backend/app/services/email_service.py
from __future__ import annotations

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Optional
from email.utils import formataddr

from app.config import settings
from app.utils.logger import logger

try:
    import aiosmtplib  # type: ignore
except Exception:
    aiosmtplib = None  # type: ignore



class EmailService:
    async def send_email(
        self,
        to_email: str,
        to_name: str,
        subject: str,
        html_body: str,
        text_body: str,
        attachments: Optional[List[str]] = None,  # kept for compatibility (unused here)
    ) -> bool:
        """
        Sends an email via SMTP (Gmail supported).
        Returns True/False only to avoid breaking existing callers.
        """
        if aiosmtplib is None:
            logger.error("aiosmtplib is not installed. Cannot send email.")
            return False

        to_email = (to_email or "").strip()
        subject = (subject or "").strip()
        html_body = (html_body or "").strip()
        text_body = (text_body or "").strip()

        if not to_email or not subject or (not html_body and not text_body):
            logger.error("Missing to_email/subject/body for send_email")
            return False

        smtp_host = (getattr(settings, "SMTP_HOST", "") or "").strip()
        smtp_port = int(getattr(settings, "SMTP_PORT", 587) or 587)
        smtp_user = (getattr(settings, "SMTP_USER", "") or "").strip()
        smtp_password = (getattr(settings, "SMTP_PASSWORD", "") or "").strip()

        if not smtp_host or not smtp_user or not smtp_password:
            logger.error("SMTP config missing: SMTP_HOST/SMTP_USER/SMTP_PASSWORD")
            return False

        # Defaults are correct for Gmail SMTP (587 + STARTTLS)
        smtp_starttls = bool(getattr(settings, "SMTP_STARTTLS", True))
        smtp_use_ssl = bool(getattr(settings, "SMTP_USE_SSL", False))

        from_email = (getattr(settings, "EMAIL_FROM", "") or smtp_user).strip()
        from_name = (getattr(settings, "EMAIL_FROM_NAME", "") or "Algonox").strip()

        # Build MIME message
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = formataddr((from_name, from_email))
        msg["To"] = formataddr(((to_name or "").strip() or "there", to_email))


        # Attach plaintext first, then HTML
        if text_body:
            msg.attach(MIMEText(text_body, "plain", "utf-8"))
        if html_body:
            msg.attach(MIMEText(html_body, "html", "utf-8"))

        try:
            await aiosmtplib.send(
                msg,
                hostname=smtp_host,
                port=smtp_port,
                username=smtp_user,
                password=smtp_password,
                start_tls=smtp_starttls,
                use_tls=smtp_use_ssl,
                timeout=20,
            )
            logger.info(f"SMTP email sent to {to_email}")
            return True
        except Exception as e:
            logger.error(f"SMTP send failed to {to_email}: {str(e)}")
            return False
