# backend/app/services/email_service.py
"""
Enhanced Email Service with:
- Retry logic with exponential backoff
- Email throttling (rate limiting)
- CAN-SPAM compliant HTML templates with unsubscribe link
- Open/click tracking support
- Error categorization
- Test/staging mode support
"""

from __future__ import annotations

import asyncio
import hashlib
import html
import secrets
import time
from collections import defaultdict
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote, urljoin

from app.config import settings
from app.utils.logger import logger
from app.utils.retry import async_retry, RetryError

try:
    import aiosmtplib  # type: ignore
except Exception:
    aiosmtplib = None  # type: ignore


# ==================== Email Throttling ====================

class EmailThrottler:
    """
    In-memory email rate limiter.
    Limits sends to EMAIL_MAX_PER_HOUR (default 50) per hour.
    """

    def __init__(self):
        self._send_times: Dict[str, List[float]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def can_send(self, sender: str) -> Tuple[bool, int]:
        """
        Check if sender can send another email.

        Returns:
            (can_send, seconds_until_available)
        """
        async with self._lock:
            now = time.time()
            one_hour_ago = now - 3600

            # Clean old entries
            self._send_times[sender] = [
                t for t in self._send_times[sender] if t > one_hour_ago
            ]

            current_count = len(self._send_times[sender])
            max_per_hour = getattr(settings, "EMAIL_MAX_PER_HOUR", 50) or 50

            if current_count >= max_per_hour:
                # Calculate when the oldest entry expires
                oldest = min(self._send_times[sender])
                wait_seconds = int(oldest + 3600 - now) + 1
                return False, max(1, wait_seconds)

            return True, 0

    async def record_send(self, sender: str) -> None:
        """Record a send for throttling."""
        async with self._lock:
            self._send_times[sender].append(time.time())

    async def get_remaining_quota(self, sender: str) -> int:
        """Get remaining sends available this hour."""
        async with self._lock:
            now = time.time()
            one_hour_ago = now - 3600

            self._send_times[sender] = [
                t for t in self._send_times[sender] if t > one_hour_ago
            ]

            max_per_hour = getattr(settings, "EMAIL_MAX_PER_HOUR", 50) or 50
            return max(0, max_per_hour - len(self._send_times[sender]))


# Global throttler instance
_throttler = EmailThrottler()


# ==================== Error Categories ====================

class EmailErrorCategory:
    CONNECTION = "connection"  # Network/SMTP connection issues (retry)
    AUTH = "auth"  # Authentication failures (alert, don't retry)
    RECIPIENT = "recipient"  # Invalid recipient (mark email_valid=False)
    CONTENT = "content"  # Content issues (log and skip)
    THROTTLE = "throttle"  # Rate limited (wait and retry)
    UNKNOWN = "unknown"  # Unknown errors


def categorize_smtp_error(error: Exception) -> Tuple[str, str]:
    """
    Categorize SMTP error for proper handling.

    Returns:
        (category, description)
    """
    error_str = str(error).lower()

    # Connection errors
    if any(x in error_str for x in ["connection", "timeout", "refused", "network", "eof"]):
        return EmailErrorCategory.CONNECTION, "SMTP connection failed"

    # Authentication errors
    if any(x in error_str for x in ["auth", "credential", "password", "login", "535"]):
        return EmailErrorCategory.AUTH, "SMTP authentication failed"

    # Recipient errors (bounces)
    if any(x in error_str for x in ["550", "551", "552", "553", "554", "user unknown", "mailbox", "recipient"]):
        return EmailErrorCategory.RECIPIENT, "Invalid recipient address"

    # Content/format errors
    if any(x in error_str for x in ["552", "message size", "content", "spam"]):
        return EmailErrorCategory.CONTENT, "Email content rejected"

    # Rate limiting
    if any(x in error_str for x in ["421", "450", "rate", "limit", "too many"]):
        return EmailErrorCategory.THROTTLE, "SMTP rate limited"

    return EmailErrorCategory.UNKNOWN, f"SMTP error: {str(error)[:100]}"


# ==================== HTML Email Templates ====================

def get_email_base_template() -> str:
    """
    Returns the base HTML email template with responsive design.
    Includes placeholders for content, tracking pixel, and unsubscribe link.
    """
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="X-UA-Compatible" content="IE=edge">
    <title>{subject}</title>
    <!--[if mso]>
    <style type="text/css">
        table {{ border-collapse: collapse; }}
        .button {{ padding: 12px 24px !important; }}
    </style>
    <![endif]-->
    <style>
        /* Reset styles */
        body, table, td, p, a {{ -webkit-text-size-adjust: 100%; -ms-text-size-adjust: 100%; }}
        table, td {{ mso-table-lspace: 0pt; mso-table-rspace: 0pt; }}
        img {{ -ms-interpolation-mode: bicubic; border: 0; height: auto; line-height: 100%; outline: none; text-decoration: none; }}
        body {{ margin: 0 !important; padding: 0 !important; width: 100% !important; }}

        /* Base styles */
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            font-size: 16px;
            line-height: 1.6;
            color: #333333;
            background-color: #f4f4f4;
        }}

        .email-container {{
            max-width: 600px;
            margin: 0 auto;
            background-color: #ffffff;
        }}

        .email-header {{
            padding: 30px 40px 20px;
            text-align: left;
            border-bottom: 1px solid #eeeeee;
        }}

        .email-body {{
            padding: 30px 40px;
        }}

        .email-footer {{
            padding: 20px 40px;
            background-color: #f8f9fa;
            text-align: center;
            font-size: 12px;
            color: #666666;
        }}

        .logo {{
            font-size: 24px;
            font-weight: 700;
            color: #1a1a1a;
            text-decoration: none;
        }}

        .logo-accent {{
            color: #41FFFF;
        }}

        .button {{
            display: inline-block;
            padding: 14px 28px;
            background-color: #1a1a1a;
            color: #ffffff !important;
            text-decoration: none;
            border-radius: 6px;
            font-weight: 600;
            font-size: 14px;
            margin: 20px 0;
        }}

        .button:hover {{
            background-color: #333333;
        }}

        .button-secondary {{
            background-color: transparent;
            border: 2px solid #1a1a1a;
            color: #1a1a1a !important;
        }}

        .signature {{
            margin-top: 30px;
            padding-top: 20px;
            border-top: 1px solid #eeeeee;
        }}

        .signature-name {{
            font-weight: 600;
            color: #1a1a1a;
        }}

        .unsubscribe-link {{
            color: #999999;
            text-decoration: underline;
        }}

        .preheader {{
            display: none !important;
            visibility: hidden;
            mso-hide: all;
            font-size: 1px;
            line-height: 1px;
            max-height: 0;
            max-width: 0;
            opacity: 0;
            overflow: hidden;
        }}

        /* Mobile responsive */
        @media screen and (max-width: 600px) {{
            .email-container {{
                width: 100% !important;
            }}
            .email-header, .email-body, .email-footer {{
                padding-left: 20px !important;
                padding-right: 20px !important;
            }}
            .button {{
                display: block;
                text-align: center;
            }}
        }}
    </style>
</head>
<body>
    <!-- Preheader text (shown in email preview) -->
    <div class="preheader">{preview_text}</div>

    <!-- Email container -->
    <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="background-color: #f4f4f4;">
        <tr>
            <td style="padding: 20px 0;">
                <table role="presentation" cellspacing="0" cellpadding="0" border="0" class="email-container" align="center" style="background-color: #ffffff; border-radius: 8px; overflow: hidden;">

                    <!-- Header -->
                    <tr>
                        <td class="email-header">
                            <a href="https://algonox.com" class="logo">
                                Algo<span class="logo-accent">nox</span>
                            </a>
                        </td>
                    </tr>

                    <!-- Body -->
                    <tr>
                        <td class="email-body">
                            {body_content}

                            <!-- Signature -->
                            <div class="signature">
                                <p class="signature-name">{sender_name}</p>
                                <p style="margin: 0; color: #666666;">{sender_title}</p>
                                <p style="margin: 0; color: #666666;">Algonox</p>
                            </div>
                        </td>
                    </tr>

                    <!-- Footer -->
                    <tr>
                        <td class="email-footer">
                            <p style="margin: 0 0 10px 0;">{company_address}</p>
                            <p style="margin: 0;">
                                <a href="{unsubscribe_url}" class="unsubscribe-link">Unsubscribe</a>
                                {privacy_link}
                            </p>
                            {tracking_pixel}
                        </td>
                    </tr>

                </table>
            </td>
        </tr>
    </table>
</body>
</html>"""


def wrap_in_template(
    body_html: str,
    subject: str,
    preview_text: str = "",
    unsubscribe_url: str = "",
    tracking_pixel_url: str = "",
    sender_name: str = "",
    sender_title: str = "",
) -> str:
    """
    Wraps email body content in the branded HTML template.
    """
    sender_name = sender_name or getattr(settings, "EMAIL_SENDER_NAME", "Harsha")
    sender_title = sender_title or getattr(settings, "EMAIL_SENDER_TITLE", "Business Development")
    company_address = getattr(settings, "COMPANY_ADDRESS", "Algonox Technologies | Hyderabad, India")

    # Generate tracking pixel HTML if URL provided
    tracking_pixel = ""
    if tracking_pixel_url:
        tracking_pixel = f'<img src="{tracking_pixel_url}" width="1" height="1" alt="" style="display:none;"/>'

    # Privacy link (optional)
    privacy_link = ""

    template = get_email_base_template()

    return template.format(
        subject=html.escape(subject),
        preview_text=html.escape(preview_text or subject[:100]),
        body_content=body_html,  # Already HTML
        sender_name=html.escape(sender_name),
        sender_title=html.escape(sender_title),
        company_address=html.escape(company_address),
        unsubscribe_url=unsubscribe_url or "#",
        privacy_link=privacy_link,
        tracking_pixel=tracking_pixel,
    )


def generate_tracking_id() -> str:
    """Generate a unique tracking ID for an email."""
    return secrets.token_urlsafe(32)


def generate_unsubscribe_url(lead_id: int, email: str) -> str:
    """
    Generate a secure unsubscribe URL.
    Uses HMAC to prevent URL guessing/tampering.
    """
    base_url = getattr(settings, "EMAIL_TRACKING_BASE_URL", None)
    if not base_url:
        # Fallback to Twilio webhook URL without the trailing path
        base_url = getattr(settings, "TWILIO_WEBHOOK_URL", "http://localhost:8000")

    # Create a simple hash for verification
    secret = getattr(settings, "ELEVENLABS_WEBHOOK_SECRET", "default-secret")
    token = hashlib.sha256(f"{lead_id}:{email}:{secret}".encode()).hexdigest()[:16]

    return f"{base_url.rstrip('/')}/api/leads/unsubscribe?lead_id={lead_id}&token={token}"


def generate_tracking_pixel_url(tracking_id: str) -> str:
    """Generate URL for open tracking pixel."""
    base_url = getattr(settings, "EMAIL_TRACKING_BASE_URL", None)
    if not base_url:
        base_url = getattr(settings, "TWILIO_WEBHOOK_URL", "http://localhost:8000")

    return f"{base_url.rstrip('/')}/api/emails/track/open/{tracking_id}"


def generate_click_tracking_url(tracking_id: str, original_url: str) -> str:
    """Generate URL for click tracking redirect."""
    base_url = getattr(settings, "EMAIL_TRACKING_BASE_URL", None)
    if not base_url:
        base_url = getattr(settings, "TWILIO_WEBHOOK_URL", "http://localhost:8000")

    encoded_url = quote(original_url, safe="")
    return f"{base_url.rstrip('/')}/api/emails/track/click/{tracking_id}?url={encoded_url}"


# ==================== Email Service ====================

class EmailService:
    """
    Enhanced email service with retry, throttling, templates, and tracking.
    """

    def __init__(self):
        self.throttler = _throttler

    async def send_email(
        self,
        to_email: str,
        to_name: str,
        subject: str,
        html_body: str,
        text_body: str,
        attachments: Optional[List[str]] = None,
        # New parameters
        lead_id: Optional[int] = None,
        tracking_id: Optional[str] = None,
        preview_text: Optional[str] = None,
        use_template: bool = True,
        skip_throttle: bool = False,
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Send an email with retry logic and throttling.

        Args:
            to_email: Recipient email address
            to_name: Recipient name
            subject: Email subject
            html_body: HTML content (will be wrapped in template if use_template=True)
            text_body: Plain text content
            attachments: List of attachment file paths (not implemented)
            lead_id: Lead ID for unsubscribe link
            tracking_id: Unique ID for tracking (generated if not provided)
            preview_text: Preheader text for email clients
            use_template: Whether to wrap content in branded template
            skip_throttle: Skip throttling check (for system emails)

        Returns:
            (success, tracking_id, error_category)
        """
        if aiosmtplib is None:
            logger.error("aiosmtplib is not installed. Cannot send email.")
            return False, None, EmailErrorCategory.UNKNOWN

        to_email = (to_email or "").strip()
        subject = (subject or "").strip()
        html_body = (html_body or "").strip()
        text_body = (text_body or "").strip()

        if not to_email or not subject or (not html_body and not text_body):
            logger.error("Missing to_email/subject/body for send_email")
            return False, None, EmailErrorCategory.CONTENT

        # Get sender info
        smtp_user = (getattr(settings, "SMTP_USER", "") or "").strip()
        from_email = (getattr(settings, "EMAIL_FROM", "") or smtp_user).strip()

        # Check environment mode
        email_env = getattr(settings, "EMAIL_ENVIRONMENT", "production")

        if email_env == "test":
            logger.info(f"[TEST MODE] Would send email to {to_email}: {subject}")
            return True, tracking_id, None

        if email_env == "staging":
            test_recipient = getattr(settings, "EMAIL_TEST_RECIPIENT", None)
            if test_recipient:
                logger.info(f"[STAGING MODE] Redirecting email from {to_email} to {test_recipient}")
                to_email = test_recipient
            else:
                logger.warning("[STAGING MODE] No EMAIL_TEST_RECIPIENT configured, skipping send")
                return True, tracking_id, None

        # Check throttling
        if not skip_throttle:
            can_send, wait_seconds = await self.throttler.can_send(from_email)
            if not can_send:
                logger.warning(f"Email throttled for {from_email}. Wait {wait_seconds}s")
                return False, None, EmailErrorCategory.THROTTLE

        # Generate tracking ID if not provided
        if not tracking_id:
            tracking_id = generate_tracking_id()

        # Build HTML with template
        if use_template and lead_id:
            unsubscribe_url = generate_unsubscribe_url(lead_id, to_email)
            tracking_pixel_url = generate_tracking_pixel_url(tracking_id)

            html_body = wrap_in_template(
                body_html=html_body,
                subject=subject,
                preview_text=preview_text or "",
                unsubscribe_url=unsubscribe_url,
                tracking_pixel_url=tracking_pixel_url,
            )

        # Send with retry
        success, error_category = await self._send_with_retry(
            to_email=to_email,
            to_name=to_name,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
        )

        if success:
            await self.throttler.record_send(from_email)

        return success, tracking_id, error_category

    @async_retry(
        max_attempts=3,
        initial_delay=2.0,
        max_delay=30.0,
        backoff_factor=2.0,
        retryable_exceptions=(ConnectionError, TimeoutError, OSError),
        operation_name="email_send",
    )
    async def _send_smtp(
        self,
        to_email: str,
        to_name: str,
        subject: str,
        html_body: str,
        text_body: str,
    ) -> None:
        """Internal SMTP send with retry decorator."""
        smtp_host = (getattr(settings, "SMTP_HOST", "") or "").strip()
        smtp_port = int(getattr(settings, "SMTP_PORT", 587) or 587)
        smtp_user = (getattr(settings, "SMTP_USER", "") or "").strip()
        smtp_password = (getattr(settings, "SMTP_PASSWORD", "") or "").strip()

        if not smtp_host or not smtp_user or not smtp_password:
            raise ValueError("SMTP config missing: SMTP_HOST/SMTP_USER/SMTP_PASSWORD")

        smtp_starttls = bool(getattr(settings, "SMTP_TLS", True))
        smtp_use_ssl = bool(getattr(settings, "SMTP_USE_SSL", False))

        from_email = (getattr(settings, "EMAIL_FROM", "") or smtp_user).strip()
        from_name = (getattr(settings, "EMAIL_FROM_NAME", "") or "Algonox").strip()
        reply_to = (getattr(settings, "EMAIL_REPLY_TO", "") or from_email).strip()

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = formataddr((from_name, from_email))
        msg["To"] = formataddr(((to_name or "").strip() or "there", to_email))

        # Headers for deliverability
        msg["Reply-To"] = reply_to
        msg["X-Mailer"] = "Algonox AADOS"
        msg["X-Priority"] = "3"
        msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"

        if text_body:
            msg.attach(MIMEText(text_body, "plain", "utf-8"))
        if html_body:
            msg.attach(MIMEText(html_body, "html", "utf-8"))

        await aiosmtplib.send(
            msg,
            hostname=smtp_host,
            port=smtp_port,
            username=smtp_user,
            password=smtp_password,
            start_tls=smtp_starttls,
            use_tls=smtp_use_ssl,
            timeout=30,
        )

    async def _send_with_retry(
        self,
        to_email: str,
        to_name: str,
        subject: str,
        html_body: str,
        text_body: str,
    ) -> Tuple[bool, Optional[str]]:
        """
        Send email with retry and error categorization.

        Returns:
            (success, error_category)
        """
        try:
            await self._send_smtp(to_email, to_name, subject, html_body, text_body)
            logger.info(f"SMTP email sent to {to_email}")
            return True, None

        except RetryError as e:
            category, description = categorize_smtp_error(e.last_exception or e)
            logger.error(f"SMTP send failed after retries to {to_email}: {description}")
            return False, category

        except Exception as e:
            category, description = categorize_smtp_error(e)
            logger.error(f"SMTP send failed to {to_email}: {description}")
            return False, category

    async def send_to_many(
        self,
        to_emails: List[str],
        subject: str,
        html_body: str,
        text_body: str,
        to_name: Optional[str] = None,
        attachments: Optional[List[str]] = None,
    ) -> bool:
        """Send email to multiple recipients. Returns True if at least one succeeded."""
        if not to_emails:
            return False

        success_count = 0
        for email in to_emails:
            email = (email or "").strip()
            if email:
                ok, _, _ = await self.send_email(
                    to_email=email,
                    to_name=to_name or "",
                    subject=subject,
                    html_body=html_body,
                    text_body=text_body,
                    attachments=attachments,
                    use_template=False,  # Don't add template for bulk sends
                    skip_throttle=True,  # System emails skip throttle
                )
                if ok:
                    success_count += 1

        return success_count > 0

    async def get_throttle_status(self) -> Dict:
        """Get current throttling status."""
        smtp_user = (getattr(settings, "SMTP_USER", "") or "").strip()
        from_email = (getattr(settings, "EMAIL_FROM", "") or smtp_user).strip()

        remaining = await self.throttler.get_remaining_quota(from_email)
        max_per_hour = getattr(settings, "EMAIL_MAX_PER_HOUR", 50) or 50

        return {
            "sender": from_email,
            "remaining_this_hour": remaining,
            "max_per_hour": max_per_hour,
            "used_this_hour": max_per_hour - remaining,
        }
