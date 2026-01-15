# backend/app/api/auth.py
"""
Authentication API endpoints.

Provides:
- User registration and login
- JWT token generation
- API key management
- Password reset (future)
"""

from datetime import datetime, timedelta
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth.jwt_handler import (
    create_access_token,
    get_password_hash,
    verify_password,
    create_api_key,
    hash_api_key,
    ACCESS_TOKEN_EXPIRE_MINUTES,
)
from app.auth.models import (
    User,
    APIKey,
    UserCreate,
    UserLogin,
    UserResponse,
    TokenResponse,
    APIKeyCreate,
    APIKeyResponse,
    UserInDB,
)
from app.auth.dependencies import get_current_user, require_admin
from app.utils.logger import logger

router = APIRouter(prefix="/api/auth", tags=["authentication"])


# ==================== Public Endpoints ====================

@router.post("/login", response_model=TokenResponse)
async def login(
    credentials: UserLogin,
    db: Session = Depends(get_db),
):
    """
    Authenticate user and return JWT token.

    Args:
        credentials: Email and password

    Returns:
        Access token and expiration info
    """
    user = db.query(User).filter(User.email == credentials.email).first()

    if not user or not verify_password(credentials.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled",
        )

    # Update last login
    user.last_login_at = datetime.utcnow()
    db.commit()

    # Create access token
    access_token = create_access_token(
        data={
            "sub": user.email,
            "user_id": user.id,
            "is_admin": user.is_admin,
        }
    )

    logger.info(f"User {user.email} logged in successfully")

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    user_data: UserCreate,
    admin_user: UserInDB = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Register a new user.

    **Requires admin authentication.**
    Only admins can create new user accounts.
    """
    # Check if user exists
    existing = db.query(User).filter(User.email == user_data.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User with this email already exists",
        )

    # Create user
    user = User(
        email=user_data.email,
        hashed_password=get_password_hash(user_data.password),
        full_name=user_data.full_name,
        is_admin=False,  # New users are not admins by default
        is_active=True,
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    logger.info(f"Admin {admin_user.email} registered new user: {user.email}")

    return UserResponse.model_validate(user)


# ==================== Authenticated Endpoints ====================

@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: UserInDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get current authenticated user info."""
    user = db.query(User).filter(User.id == current_user.id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return UserResponse.model_validate(user)


@router.post("/api-keys", response_model=APIKeyResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key_endpoint(
    key_data: APIKeyCreate,
    current_user: UserInDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Create a new API key for the current user.

    IMPORTANT: The full API key is only shown once. Save it securely.
    """
    # Generate the API key
    raw_key = create_api_key()
    key_prefix = raw_key[:20]
    key_hash = hash_api_key(raw_key)

    # Calculate expiration if specified
    expires_at = None
    if key_data.expires_in_days:
        expires_at = datetime.utcnow() + timedelta(days=key_data.expires_in_days)

    # Create the API key record
    api_key = APIKey(
        user_id=current_user.id,
        key_prefix=key_prefix,
        key_hash=key_hash,
        name=key_data.name,
        description=key_data.description,
        can_read=key_data.can_read,
        can_write=key_data.can_write,
        can_call=key_data.can_call,
        can_admin=key_data.can_admin and current_user.is_admin,  # Only admins can create admin keys
        expires_at=expires_at,
    )

    db.add(api_key)
    db.commit()
    db.refresh(api_key)

    logger.info(f"API key created for user {current_user.email}: {key_data.name}")

    return APIKeyResponse(
        id=api_key.id,
        key=raw_key,  # Only time we return the full key
        key_prefix=key_prefix,
        name=api_key.name,
        created_at=api_key.created_at,
    )


@router.get("/api-keys")
async def list_api_keys(
    current_user: UserInDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all API keys for the current user (without revealing the keys)."""
    keys = db.query(APIKey).filter(APIKey.user_id == current_user.id).all()

    return {
        "api_keys": [
            {
                "id": k.id,
                "key_prefix": k.key_prefix + "...",
                "name": k.name,
                "description": k.description,
                "is_active": k.is_active,
                "can_read": k.can_read,
                "can_write": k.can_write,
                "can_call": k.can_call,
                "can_admin": k.can_admin,
                "created_at": k.created_at.isoformat() if k.created_at else None,
                "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
                "expires_at": k.expires_at.isoformat() if k.expires_at else None,
            }
            for k in keys
        ]
    }


@router.delete("/api-keys/{key_id}")
async def revoke_api_key(
    key_id: int,
    current_user: UserInDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Revoke (delete) an API key."""
    api_key = db.query(APIKey).filter(
        APIKey.id == key_id,
        APIKey.user_id == current_user.id
    ).first()

    if not api_key:
        raise HTTPException(status_code=404, detail="API key not found")

    db.delete(api_key)
    db.commit()

    logger.info(f"API key {key_id} revoked by user {current_user.email}")

    return {"status": "revoked", "key_id": key_id}


# ==================== Admin Endpoints ====================

@router.get("/users", response_model=List[UserResponse])
async def list_users(
    skip: int = 0,
    limit: int = 100,
    admin_user: UserInDB = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """List all users (admin only)."""
    users = db.query(User).offset(skip).limit(limit).all()
    return [UserResponse.model_validate(u) for u in users]


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user_admin(
    user_data: UserCreate,
    admin_user: UserInDB = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Create a new user (admin only). Can create admin users."""
    existing = db.query(User).filter(User.email == user_data.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User with this email already exists",
        )

    user = User(
        email=user_data.email,
        hashed_password=get_password_hash(user_data.password),
        full_name=user_data.full_name,
        is_admin=user_data.is_admin,
        is_active=True,
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    logger.info(f"Admin {admin_user.email} created user: {user.email} (admin={user.is_admin})")

    return UserResponse.model_validate(user)


@router.patch("/users/{user_id}/toggle-active")
async def toggle_user_active(
    user_id: int,
    admin_user: UserInDB = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Enable or disable a user account (admin only)."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.id == admin_user.id:
        raise HTTPException(status_code=400, detail="Cannot disable your own account")

    user.is_active = not user.is_active
    db.commit()

    status_str = "enabled" if user.is_active else "disabled"
    logger.info(f"Admin {admin_user.email} {status_str} user: {user.email}")

    return {"user_id": user_id, "is_active": user.is_active}
