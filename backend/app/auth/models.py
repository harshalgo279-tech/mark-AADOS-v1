# backend/app/auth/models.py
"""
Authentication models for database storage.
"""

from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, EmailStr
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.database import Base


# ==================== SQLAlchemy Models ====================

class User(Base):
    """User model for authentication."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=True)

    is_active = Column(Boolean, default=True, nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)
    is_superuser = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    last_login_at = Column(DateTime(timezone=True), nullable=True)

    # Relationship to API keys
    api_keys = relationship("APIKey", back_populates="user", cascade="all, delete-orphan")


class APIKey(Base):
    """API Key model for programmatic access."""
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # We store a prefix for identification and the hash for verification
    key_prefix = Column(String(20), nullable=False)  # e.g., "aados_abc123..."
    key_hash = Column(String(255), nullable=False)

    name = Column(String(255), nullable=False)  # Descriptive name for the key
    description = Column(Text, nullable=True)

    is_active = Column(Boolean, default=True, nullable=False)

    # Permissions
    can_read = Column(Boolean, default=True, nullable=False)
    can_write = Column(Boolean, default=True, nullable=False)
    can_call = Column(Boolean, default=True, nullable=False)
    can_admin = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)

    # Relationship to user
    user = relationship("User", back_populates="api_keys")


# ==================== Pydantic Models ====================

class TokenData(BaseModel):
    """Token payload data."""
    sub: Optional[str] = None  # Subject (user email or API key ID)
    user_id: Optional[int] = None
    is_admin: bool = False
    is_api_key: bool = False
    permissions: List[str] = []


class UserInDB(BaseModel):
    """User data from database."""
    id: int
    email: str
    full_name: Optional[str] = None
    is_active: bool = True
    is_admin: bool = False
    is_superuser: bool = False

    class Config:
        from_attributes = True


class APIKeyInDB(BaseModel):
    """API Key data from database."""
    id: int
    user_id: int
    key_prefix: str
    name: str
    is_active: bool = True
    can_read: bool = True
    can_write: bool = True
    can_call: bool = True
    can_admin: bool = False

    class Config:
        from_attributes = True


# ==================== Request/Response Models ====================

class UserCreate(BaseModel):
    """Request model for creating a user."""
    email: EmailStr
    password: str
    full_name: Optional[str] = None
    is_admin: bool = False


class UserLogin(BaseModel):
    """Request model for user login."""
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """Response model for token generation."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class APIKeyCreate(BaseModel):
    """Request model for creating an API key."""
    name: str
    description: Optional[str] = None
    can_read: bool = True
    can_write: bool = True
    can_call: bool = True
    can_admin: bool = False
    expires_in_days: Optional[int] = None


class APIKeyResponse(BaseModel):
    """Response model for API key creation (shows key only once)."""
    id: int
    key: str  # Only shown once at creation
    key_prefix: str
    name: str
    created_at: datetime


class UserResponse(BaseModel):
    """Response model for user data."""
    id: int
    email: str
    full_name: Optional[str] = None
    is_active: bool
    is_admin: bool
    created_at: datetime

    class Config:
        from_attributes = True
