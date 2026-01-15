# backend/app/auth/dependencies.py
"""
FastAPI dependencies for authentication.

Provides reusable dependencies for protecting endpoints:
- get_current_user: Requires authentication
- get_current_user_optional: Authentication optional
- get_api_key: For API key authentication
- require_admin: Requires admin privileges
"""

from datetime import datetime
from typing import Optional

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, APIKeyHeader
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth.jwt_handler import verify_token, verify_api_key
from app.auth.models import User, APIKey, TokenData, UserInDB

# Security schemes
bearer_scheme = HTTPBearer(auto_error=False)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    api_key: Optional[str] = Depends(api_key_header),
    db: Session = Depends(get_db),
) -> UserInDB:
    """
    Get the current authenticated user.

    Supports both JWT Bearer token and API key authentication.

    Args:
        credentials: Bearer token credentials
        api_key: API key from header
        db: Database session

    Returns:
        UserInDB object representing the authenticated user

    Raises:
        HTTPException: If authentication fails
    """
    # Check for webhook paths that should bypass auth
    path = request.url.path
    webhook_paths = [
        "/api/calls/elevenlabs/post-call",
        "/webhook",
        "/status",
        "/recording",
    ]
    if any(wp in path for wp in webhook_paths):
        # Return a system user for webhooks (they have their own signature verification)
        return UserInDB(
            id=0,
            email="system@webhook",
            full_name="Webhook System",
            is_active=True,
            is_admin=False,
            is_superuser=False,
        )

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # Try API key first
    if api_key:
        user = await _authenticate_api_key(api_key, db)
        if user:
            return user

    # Try Bearer token
    if credentials:
        user = await _authenticate_bearer(credentials.credentials, db)
        if user:
            return user

    raise credentials_exception


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    api_key: Optional[str] = Depends(api_key_header),
    db: Session = Depends(get_db),
) -> Optional[UserInDB]:
    """
    Get the current user if authenticated, None otherwise.

    Use this for endpoints that work both authenticated and unauthenticated.
    """
    if api_key:
        user = await _authenticate_api_key(api_key, db)
        if user:
            return user

    if credentials:
        user = await _authenticate_bearer(credentials.credentials, db)
        if user:
            return user

    return None


async def get_api_key(
    api_key: str = Depends(api_key_header),
    db: Session = Depends(get_db),
) -> UserInDB:
    """
    Require API key authentication specifically.

    Use this for programmatic endpoints that must use API keys.
    """
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required",
            headers={"WWW-Authenticate": "X-API-Key"},
        )

    user = await _authenticate_api_key(api_key, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "X-API-Key"},
        )

    return user


async def require_admin(
    current_user: UserInDB = Depends(get_current_user),
) -> UserInDB:
    """
    Require the current user to be an admin.

    Use this for admin-only endpoints.
    """
    if not current_user.is_admin and not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    return current_user


# ==================== Internal Helper Functions ====================

async def _authenticate_bearer(token: str, db: Session) -> Optional[UserInDB]:
    """Authenticate using Bearer token."""
    payload = verify_token(token)
    if not payload:
        return None

    user_id = payload.get("user_id")
    if not user_id:
        return None

    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.is_active:
        return None

    return UserInDB.model_validate(user)


async def _authenticate_api_key(key: str, db: Session) -> Optional[UserInDB]:
    """Authenticate using API key."""
    if not key:
        return None

    # Get key prefix for lookup
    key_prefix = key[:20] if len(key) >= 20 else key

    # Find potential matching keys by prefix
    api_keys = db.query(APIKey).filter(
        APIKey.key_prefix == key_prefix,
        APIKey.is_active == True
    ).all()

    for api_key in api_keys:
        # Check expiration
        if api_key.expires_at and api_key.expires_at < datetime.utcnow():
            continue

        # Verify the key hash
        if verify_api_key(key, api_key.key_hash):
            # Update last used timestamp
            api_key.last_used_at = datetime.utcnow()
            db.commit()

            # Get the associated user
            user = db.query(User).filter(User.id == api_key.user_id).first()
            if user and user.is_active:
                # Return user with admin status from API key permissions
                return UserInDB(
                    id=user.id,
                    email=user.email,
                    full_name=user.full_name,
                    is_active=user.is_active,
                    is_admin=api_key.can_admin or user.is_admin,
                    is_superuser=user.is_superuser,
                )

    return None
