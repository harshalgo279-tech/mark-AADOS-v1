# backend/app/middleware/security.py
"""
Security Headers Middleware.

Implements enterprise-grade HTTP security headers:
- Content-Security-Policy (CSP)
- X-Content-Type-Options
- X-Frame-Options
- X-XSS-Protection
- Strict-Transport-Security (HSTS)
- Referrer-Policy
- Permissions-Policy
"""

from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.config import settings


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware to add security headers to all responses.

    These headers protect against common web vulnerabilities:
    - XSS (Cross-Site Scripting)
    - Clickjacking
    - MIME type sniffing
    - Information disclosure
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)

        # Determine if we're in production
        is_production = getattr(settings, "ENVIRONMENT", "development") == "production"

        # X-Content-Type-Options: Prevent MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # X-Frame-Options: Prevent clickjacking (being embedded in iframes)
        response.headers["X-Frame-Options"] = "DENY"

        # X-XSS-Protection: Enable browser XSS filtering (legacy but still useful)
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Referrer-Policy: Control how much referrer info is sent
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Permissions-Policy: Restrict browser features
        response.headers["Permissions-Policy"] = (
            "accelerometer=(), "
            "camera=(), "
            "geolocation=(), "
            "gyroscope=(), "
            "magnetometer=(), "
            "microphone=(), "
            "payment=(), "
            "usb=()"
        )

        # Content-Security-Policy: Control resources the browser can load
        # This is a relatively permissive CSP - tighten for your specific needs
        csp_directives = [
            "default-src 'self'",
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'",  # Needed for React
            "style-src 'self' 'unsafe-inline'",  # Needed for inline styles
            "img-src 'self' data: https:",
            "font-src 'self' data:",
            "connect-src 'self' https://api.elevenlabs.io https://api.twilio.com wss:",
            "frame-ancestors 'none'",
            "base-uri 'self'",
            "form-action 'self'",
        ]
        response.headers["Content-Security-Policy"] = "; ".join(csp_directives)

        # Strict-Transport-Security (HSTS): Force HTTPS
        # Only set in production to avoid issues with local development
        if is_production:
            # max-age=31536000 (1 year), includeSubDomains for full protection
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains; preload"
            )

        # Cache-Control for API responses
        # Prevent caching of authenticated responses
        if "/api/" in str(request.url.path):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"

        return response
