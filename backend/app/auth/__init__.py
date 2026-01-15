# backend/app/auth/__init__.py
"""
Authentication module for AADOS API.

Provides JWT-based authentication with API key support for programmatic access.
"""

from app.auth.jwt_handler import (
    create_access_token,
    verify_token,
    get_password_hash,
    verify_password,
)
from app.auth.dependencies import (
    get_current_user,
    get_current_user_optional,
    get_api_key,
    require_admin,
)
from app.auth.models import (
    TokenData,
    UserInDB,
    APIKeyInDB,
)

__all__ = [
    "create_access_token",
    "verify_token",
    "get_password_hash",
    "verify_password",
    "get_current_user",
    "get_current_user_optional",
    "get_api_key",
    "require_admin",
    "TokenData",
    "UserInDB",
    "APIKeyInDB",
]
