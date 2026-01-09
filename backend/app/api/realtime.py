# backend/app/api/realtime.py
"""
OpenAI Realtime API endpoint for generating ephemeral keys.

This endpoint creates ephemeral (temporary) API keys that allow the frontend
to establish a direct WebRTC connection to OpenAI's Realtime API without
exposing the main API key to the client.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import httpx
from typing import Optional

from app.config import settings
from app.utils.logger import logger

router = APIRouter()


class SessionResponse(BaseModel):
    """Response model for session creation"""
    ephemeral_key: str
    expires_at: int


@router.post("/session", response_model=SessionResponse)
async def create_realtime_session():
    """
    Create an ephemeral key for OpenAI Realtime API.

    This endpoint:
    1. Uses the main OpenAI API key to request an ephemeral key
    2. Returns the ephemeral key to the frontend
    3. The frontend uses this key to establish a WebRTC connection directly to OpenAI

    Security:
    - The main API key never leaves the server
    - Ephemeral keys expire automatically (typically after 60 seconds)
    - Each session gets a unique ephemeral key

    Returns:
        SessionResponse: Contains the ephemeral key and expiration timestamp

    Raises:
        HTTPException: If the OpenAI API key is not configured or request fails
    """

    # Verify OpenAI API key is configured
    if not settings.OPENAI_API_KEY:
        logger.error("OpenAI API key not configured")
        raise HTTPException(
            status_code=500,
            detail="OpenAI API key not configured"
        )

    try:
        # Request ephemeral key from OpenAI
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.openai.com/v1/realtime/sessions",
                headers={
                    "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "gpt-4o-realtime-preview-2024-12-17",
                    "voice": "alloy"
                },
                timeout=10.0
            )

            if response.status_code != 200:
                error_detail = response.text
                logger.error(f"OpenAI API error: {error_detail}")
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Failed to create session: {error_detail}"
                )

            data = response.json()

            # Extract ephemeral key and expiration
            ephemeral_key = data.get("client_secret", {}).get("value")
            expires_at = data.get("client_secret", {}).get("expires_at", 0)

            if not ephemeral_key:
                logger.error("No ephemeral key in OpenAI response")
                raise HTTPException(
                    status_code=500,
                    detail="Invalid response from OpenAI API"
                )

            logger.info(f"Created ephemeral key, expires at: {expires_at}")

            return SessionResponse(
                ephemeral_key=ephemeral_key,
                expires_at=expires_at
            )

    except httpx.TimeoutException:
        logger.error("Timeout connecting to OpenAI API")
        raise HTTPException(
            status_code=504,
            detail="Timeout connecting to OpenAI API"
        )
    except httpx.HTTPError as e:
        logger.error(f"HTTP error connecting to OpenAI API: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error connecting to OpenAI API: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error creating session: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected error: {str(e)}"
        )
