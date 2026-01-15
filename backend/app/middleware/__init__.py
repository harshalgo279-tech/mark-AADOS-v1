# backend/app/middleware/__init__.py
"""
Custom middleware for AADOS API.
"""

from app.middleware.security import SecurityHeadersMiddleware

__all__ = ["SecurityHeadersMiddleware"]
