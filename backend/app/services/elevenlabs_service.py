# backend/app/services/elevenlabs_service.py
from __future__ import annotations

import hmac
import time
from hashlib import sha256
from typing import Any, Dict, Optional, Tuple

import httpx

from app.config import settings
from app.utils.logger import logger
from app.utils.retry import (
    async_retry,
    check_rate_limit_response,
    RateLimitError,
    RetryError,
)


class ElevenLabsService:
    def __init__(self):
        self.api_key = (getattr(settings, "ELEVENLABS_API_KEY", "") or "").strip()
        self.agent_id = (getattr(settings, "ELEVENLABS_AGENT_ID", "") or "").strip()
        self.webhook_secret = (getattr(settings, "ELEVENLABS_WEBHOOK_SECRET", "") or "").strip()
        self.phone_number_id = (getattr(settings, "ELEVENLABS_PHONE_NUMBER_ID", "") or "").strip()

        self.base_url = "https://api.elevenlabs.io"
        self._http = httpx.AsyncClient(timeout=25)

        if not self.api_key:
            logger.warning("ELEVENLABS_API_KEY is missing")
        if not self.agent_id:
            logger.warning("ELEVENLABS_AGENT_ID is missing")

    def can_use_outbound_api(self) -> bool:
        """Check if outbound-call API can be used (requires phone_number_id)."""
        return bool(self.api_key and self.agent_id and self.phone_number_id)

    async def make_outbound_call(
        self,
        *,
        to_number: str,
        conversation_initiation_client_data: Optional[Dict[str, Any]] = None,
        agent_id: Optional[str] = None,
        phone_number_id: Optional[str] = None,
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Make outbound call using ElevenLabs API.
        Returns: (success, conversation_id, call_sid)

        This method enables real-time transcript streaming via the monitor WebSocket.
        Includes retry logic with exponential backoff for transient failures.
        """
        agent = (agent_id or self.agent_id).strip()
        phone_id = (phone_number_id or self.phone_number_id).strip()

        if not self.api_key:
            raise RuntimeError("ELEVENLABS_API_KEY missing")
        if not agent:
            raise RuntimeError("ELEVENLABS_AGENT_ID missing")
        if not phone_id:
            raise RuntimeError("ELEVENLABS_PHONE_NUMBER_ID missing for outbound calls")
        if not to_number:
            raise ValueError("to_number is required")

        url = f"{self.base_url}/v1/convai/twilio/outbound-call"
        payload: Dict[str, Any] = {
            "agent_id": agent,
            "agent_phone_number_id": phone_id,
            "to_number": to_number,
        }
        if conversation_initiation_client_data:
            payload["conversation_initiation_client_data"] = conversation_initiation_client_data

        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
        }

        @async_retry(
            max_attempts=3,
            initial_delay=2.0,
            max_delay=30.0,
            backoff_factor=2.0,
            retryable_exceptions=(
                httpx.TimeoutException,
                httpx.ConnectError,
                httpx.ReadError,
                RateLimitError,
            ),
            operation_name="elevenlabs_outbound_call",
        )
        async def _make_call() -> Tuple[bool, Optional[str], Optional[str]]:
            resp = await self._http.post(url, headers=headers, json=payload)

            # Check for rate limiting
            check_rate_limit_response(resp)

            if resp.status_code >= 500:
                # Server error - retry
                raise httpx.ReadError(f"Server error {resp.status_code}")

            if resp.status_code >= 400:
                # Client error - don't retry, return failure
                logger.error(f"ElevenLabs outbound-call error {resp.status_code}: {resp.text[:1200]}")
                return False, None, None

            data = resp.json()
            success = data.get("success", False)
            conversation_id = data.get("conversation_id")
            call_sid = data.get("callSid")

            logger.info(f"ElevenLabs outbound call: success={success}, conversation_id={conversation_id}, callSid={call_sid}")
            return success, conversation_id, call_sid

        try:
            return await _make_call()
        except RetryError as e:
            logger.error(f"ElevenLabs outbound-call failed after retries: {e}")
            return False, None, None
        except Exception as e:
            logger.error(f"ElevenLabs outbound-call exception: {e}")
            return False, None, None

    def get_monitor_websocket_url(self, conversation_id: str) -> str:
        """Get WebSocket URL for real-time conversation monitoring."""
        return f"wss://api.elevenlabs.io/v1/convai/conversations/{conversation_id}/monitor"

    def get_monitor_headers(self) -> Dict[str, str]:
        """Get headers for monitor WebSocket connection."""
        return {"xi-api-key": self.api_key}

    async def register_call_twiml(
        self,
        *,
        from_number: str,
        to_number: str,
        direction: str = "outbound",
        conversation_initiation_client_data: Optional[Dict[str, Any]] = None,
        agent_id: Optional[str] = None,
    ) -> str:
        """
        Calls ElevenLabs register-call endpoint. Returns TwiML (XML string).
        Includes retry logic with exponential backoff for transient failures.
        """
        agent = (agent_id or self.agent_id).strip()
        if not self.api_key:
            raise RuntimeError("ELEVENLABS_API_KEY missing")
        if not agent:
            raise RuntimeError("ELEVENLABS_AGENT_ID missing")
        if not from_number or not to_number:
            raise ValueError("from_number and to_number are required")

        url = f"{self.base_url}/v1/convai/twilio/register-call"
        payload: Dict[str, Any] = {
            "agent_id": agent,
            "from_number": from_number,
            "to_number": to_number,
            "direction": direction,
        }
        if conversation_initiation_client_data:
            payload["conversation_initiation_client_data"] = conversation_initiation_client_data

        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
        }

        @async_retry(
            max_attempts=3,
            initial_delay=2.0,
            max_delay=30.0,
            backoff_factor=2.0,
            retryable_exceptions=(
                httpx.TimeoutException,
                httpx.ConnectError,
                httpx.ReadError,
                RateLimitError,
            ),
            operation_name="elevenlabs_register_call",
        )
        async def _register_call() -> str:
            resp = await self._http.post(url, headers=headers, json=payload)

            # Check for rate limiting
            check_rate_limit_response(resp)

            if resp.status_code >= 500:
                # Server error - retry
                raise httpx.ReadError(f"Server error {resp.status_code}")

            if resp.status_code >= 400:
                logger.error(f"ElevenLabs register-call error {resp.status_code}: {resp.text[:1200]}")
                resp.raise_for_status()

            return resp.text  # TwiML XML

        return await _register_call()

    def verify_webhook_signature(
        self,
        *,
        raw_body: bytes,
        signature_header: Optional[str],
        tolerance_seconds: int = 30 * 60,
    ) -> bool:
        """
        Verifies ElevenLabs webhook signature.
        Header example: "t=timestamp,v0=hash"
        hash = HMAC_SHA256(secret, f"{timestamp}.{body}")
        """
        if not self.webhook_secret:
            # For dev you might temporarily bypass, but production should verify.
            logger.warning("ELEVENLABS_WEBHOOK_SECRET missing; webhook verification will fail.")
            return False

        if not signature_header:
            return False

        try:
            parts = [p.strip() for p in signature_header.split(",")]
            t_part = next((p for p in parts if p.startswith("t=")), "")
            v0_part = next((p for p in parts if p.startswith("v0=")), "")
            if not t_part or not v0_part:
                return False

            ts = int(t_part[2:])
            now = int(time.time())
            if ts < (now - tolerance_seconds):
                return False

            msg = f"{ts}.{raw_body.decode('utf-8')}".encode("utf-8")
            mac = hmac.new(self.webhook_secret.encode("utf-8"), msg=msg, digestmod=sha256)
            expected = "v0=" + mac.hexdigest()

            return hmac.compare_digest(v0_part, expected)
        except Exception:
            return False

    async def aclose(self) -> None:
        try:
            await self._http.aclose()
        except Exception:
            pass
