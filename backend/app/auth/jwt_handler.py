# backend/app/auth/jwt_handler.py
"""
JWT Token handling for authentication.

Enterprise-grade security features:
- HS256 signing with secure secret
- Token expiration
- Secure password hashing with bcrypt
- Timing-safe token verification
"""

import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from jose import jwt, JWTError
from passlib.context import CryptContext

from app.config import settings

# Password hashing context using bcrypt
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT Configuration
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours

# Get secret key from environment or generate a secure one
# In production, always set JWT_SECRET_KEY in environment
JWT_SECRET_KEY = getattr(settings, "JWT_SECRET_KEY", None)
if not JWT_SECRET_KEY:
    # Generate a secure key if not set (will change on restart)
    JWT_SECRET_KEY = secrets.token_urlsafe(32)


def get_password_hash(password: str) -> str:
    """
    Hash a password using bcrypt.

    Args:
        password: Plain text password

    Returns:
        Hashed password string
    """
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a password against its hash.

    Uses timing-safe comparison to prevent timing attacks.

    Args:
        plain_password: Plain text password to verify
        hashed_password: Hashed password to compare against

    Returns:
        True if password matches, False otherwise
    """
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception:
        return False


def create_access_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    Create a JWT access token.

    Args:
        data: Payload data to encode in the token
        expires_delta: Optional custom expiration time

    Returns:
        Encoded JWT token string
    """
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "access"
    })

    encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Verify and decode a JWT token.

    Args:
        token: JWT token string to verify

    Returns:
        Decoded token payload if valid, None otherwise
    """
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None


def create_api_key() -> str:
    """
    Generate a secure API key.

    Returns:
        A cryptographically secure API key string
    """
    return f"aados_{secrets.token_urlsafe(32)}"


def hash_api_key(api_key: str) -> str:
    """
    Hash an API key for storage.

    We store only the hash of API keys for security.
    The full key is shown once at creation and cannot be recovered.

    Args:
        api_key: The API key to hash

    Returns:
        Hashed API key
    """
    return pwd_context.hash(api_key)


def verify_api_key(plain_key: str, hashed_key: str) -> bool:
    """
    Verify an API key against its stored hash.

    Args:
        plain_key: The API key provided by the client
        hashed_key: The stored hash to compare against

    Returns:
        True if key matches, False otherwise
    """
    try:
        return pwd_context.verify(plain_key, hashed_key)
    except Exception:
        return False
