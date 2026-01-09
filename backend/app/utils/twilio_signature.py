# backend/app/utils/twilio_signature.py
"""
Twilio Request Signature Verification

This module provides utilities to verify that incoming webhook requests
actually come from Twilio and haven't been tampered with.

Security Note:
- Always verify Twilio signatures in production
- This prevents malicious actors from forging webhook requests
- Twilio signs requests using HMAC-SHA256

Reference: https://www.twilio.com/docs/usage/security#validating-requests
"""

import hmac
import hashlib
from typing import Dict, Optional
from urllib.parse import urljoin, urlparse

from app.config import settings
from app.utils.logger import logger


def validate_twilio_signature(
    signature: str,
    url: str,
    params: Dict[str, str],
    auth_token: Optional[str] = None
) -> bool:
    """
    Validate that a request came from Twilio by verifying its signature.

    Args:
        signature: The X-Twilio-Signature header value
        url: The full URL of the webhook (must match what Twilio used)
        params: The POST parameters from the request
        auth_token: Your Twilio auth token (defaults to settings.TWILIO_AUTH_TOKEN)

    Returns:
        bool: True if signature is valid, False otherwise

    Example:
        from fastapi import Request

        @app.post("/webhook")
        async def webhook(request: Request):
            signature = request.headers.get("X-Twilio-Signature", "")
            url = str(request.url)
            form = await request.form()
            params = dict(form)

            if not validate_twilio_signature(signature, url, params):
                raise HTTPException(status_code=403, detail="Invalid signature")

            # Process webhook...
    """
    if not signature:
        logger.warning("[Twilio Security] No X-Twilio-Signature header provided")
        return False

    token = auth_token or getattr(settings, "TWILIO_AUTH_TOKEN", None)
    if not token:
        logger.error("[Twilio Security] TWILIO_AUTH_TOKEN not configured")
        return False

    # Compute expected signature
    expected_signature = compute_twilio_signature(url, params, token)

    # Constant-time comparison to prevent timing attacks
    is_valid = hmac.compare_digest(signature, expected_signature)

    if not is_valid:
        logger.warning(
            f"[Twilio Security] Invalid signature for URL: {url}\n"
            f"Expected: {expected_signature}\n"
            f"Received: {signature}"
        )

    return is_valid


def compute_twilio_signature(
    url: str,
    params: Dict[str, str],
    auth_token: str
) -> str:
    """
    Compute the expected Twilio signature for a request.

    Twilio Signature Algorithm:
    1. Take the full URL (including https://) of the webhook
    2. Sort parameters alphabetically and append each one to the URL string
    3. Sign the resulting string with HMAC-SHA256 using your auth token
    4. Base64 encode the result

    Args:
        url: The full URL of the webhook
        params: Dictionary of POST parameters
        auth_token: Your Twilio auth token

    Returns:
        str: The expected signature (base64-encoded HMAC-SHA256)
    """
    # Start with the full URL
    data = url

    # Append parameters in alphabetical order
    for key in sorted(params.keys()):
        data += f"{key}{params[key]}"

    # Compute HMAC-SHA256
    mac = hmac.new(
        auth_token.encode('utf-8'),
        data.encode('utf-8'),
        hashlib.sha256
    )

    # Return base64-encoded signature
    import base64
    return base64.b64encode(mac.digest()).decode('utf-8')


def get_webhook_url_for_validation(
    request_url: str,
    use_configured_base: bool = True
) -> str:
    """
    Get the URL that should be used for signature validation.

    Important: The URL must EXACTLY match what Twilio used when making the request.
    If you're behind a proxy or using ngrok, the URL seen by Twilio might differ
    from what your application sees.

    Args:
        request_url: The URL as seen by your application
        use_configured_base: If True, use TWILIO_WEBHOOK_URL as the base

    Returns:
        str: The URL to use for signature validation
    """
    if not use_configured_base:
        return request_url

    # Use the configured webhook base URL
    base_url = getattr(settings, "TWILIO_WEBHOOK_URL", "").strip()
    if not base_url:
        logger.warning("[Twilio Security] TWILIO_WEBHOOK_URL not configured, using request URL")
        return request_url

    # Parse the request URL to get the path
    parsed = urlparse(request_url)
    path = parsed.path
    if parsed.query:
        path += f"?{parsed.query}"

    # Combine configured base with request path
    return urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))


def should_validate_signature() -> bool:
    """
    Check if signature validation should be enforced.

    In development, you might want to disable validation.
    In production, it should ALWAYS be enabled.

    Returns:
        bool: True if validation should be enforced
    """
    # Check for explicit disable flag (use with caution!)
    disable_validation = getattr(settings, "TWILIO_DISABLE_SIGNATURE_VALIDATION", False)

    if disable_validation:
        logger.warning(
            "[Twilio Security] Signature validation is DISABLED! "
            "This should only be used in development."
        )
        return False

    return True
