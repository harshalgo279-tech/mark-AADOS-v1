# backend/app/services/twilio_service.py
from __future__ import annotations

from typing import Optional
from urllib.parse import urljoin

import httpx
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException

from app.config import settings
from app.utils.logger import logger


def _normalize_base_url(base: str) -> str:
    base = (base or "").strip()
    if not base:
        return ""
    # ensure trailing slash so urljoin behaves predictably
    if not base.endswith("/"):
        base += "/"
    return base


def _normalize_path(path: str) -> str:
    path = (path or "").strip()
    if not path:
        return ""
    if not path.startswith("/"):
        path = "/" + path
    return path


class TwilioService:
    """
    Twilio call orchestration.

    Latency improvements here mostly help:
    - Faster call setup
    - Cleaner callbacks
    - More reliable recording download
    """

    def __init__(self):
        self.client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        self.from_number = getattr(settings, "TWILIO_PHONE_NUMBER", None)
        self.base_webhook = _normalize_base_url(getattr(settings, "TWILIO_WEBHOOK_URL", ""))

        # optional: reuse a single httpx client for downloads (pooling)
        self._http = httpx.AsyncClient(timeout=60)

    async def make_call(
        self,
        to_number: str,
        callback_url: Optional[str] = None,
        callback_path: Optional[str] = None,
        webhook_path: Optional[str] = None,
    ):
        """
        Create an outbound call.

        callback_* args are relative paths like:
        - /api/calls/{id}/webhook
        """
        try:
            if not to_number:
                raise ValueError("to_number is required")
            if not self.from_number:
                raise ValueError("TWILIO_PHONE_NUMBER is missing in settings/.env")
            if not self.base_webhook:
                raise ValueError("TWILIO_WEBHOOK_URL is missing in settings/.env (must be public HTTPS URL)")

            path = callback_url or callback_path or webhook_path
            if not path:
                raise ValueError("callback_url/callback_path/webhook_path is required")

            path = _normalize_path(path)

            # Twilio fetches TwiML from url=...
            twiml_url = urljoin(self.base_webhook, path.lstrip("/"))

            # Status and recording callbacks
            status_url = urljoin(self.base_webhook, (path.lstrip("/") + "/status"))
            recording_url = urljoin(self.base_webhook, (path.lstrip("/") + "/recording"))

            logger.info(f"Twilio make_call -> to={to_number}, twiml_url={twiml_url}")

            # ✅ Latency knobs:
            # - timeout: how long Twilio waits for pickup (not your webhook latency)
            # - record: can add overhead; keep True if you need it
            # - status_callback_event: reduce noise if you don't need all
            # - recording_status_callback_event: only when completed
            call = self.client.calls.create(
                to=to_number,
                from_=self.from_number,
                url=twiml_url,
                method="POST",
                status_callback=status_url,
                status_callback_method="POST",
                status_callback_event=["initiated", "answered", "completed"],  # reduced events
                record=True,
                recording_status_callback=recording_url,
                recording_status_callback_event=["completed"],  # only once
                timeout=int(getattr(settings, "CALL_TIMEOUT", 25) or 25),

                # OPTIONAL (commented): can help avoid wasting time on voicemail
                # machine_detection="Enable",
                # machine_detection_timeout=6,
            )

            logger.info(f"Twilio call created: sid={call.sid}, status={call.status}")
            return call

        except TwilioRestException as e:
            logger.error(f"TwilioRestException: {e.msg}")
            raise
        except Exception as e:
            logger.error(f"Twilio make_call error: {str(e)}")
            raise

    async def download_recording(self, recording_url: str) -> bytes:
        """
        Download the recording from Twilio (authenticated).
        Use a pooled client for better performance.
        """
        try:
            if not recording_url:
                raise ValueError("recording_url is required")

            auth = (settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
            resp = await self._http.get(recording_url, auth=auth)
            resp.raise_for_status()
            return resp.content

        except Exception as e:
            logger.error(f"Error downloading recording: {str(e)}")
            raise

    async def end_call(self, call_sid: str) -> bool:
        """
        Terminate an active call by its SID.

        Used by the watchdog timer to end calls that exceed maximum duration.

        Args:
            call_sid: The Twilio Call SID to terminate

        Returns:
            True if the call was successfully terminated, False otherwise
        """
        try:
            if not call_sid:
                logger.warning("Cannot end call: call_sid is empty")
                return False

            logger.info(f"Attempting to end call: {call_sid}")

            # Update the call status to 'completed' which terminates it
            call = self.client.calls(call_sid).update(status="completed")

            logger.info(f"Call {call_sid} terminated. Final status: {call.status}")
            return True

        except TwilioRestException as e:
            # Call may already be completed or not found
            if "not found" in str(e.msg).lower() or e.code == 20404:
                logger.info(f"Call {call_sid} not found (may already be completed)")
                return True  # Consider it success if call doesn't exist
            logger.error(f"TwilioRestException ending call {call_sid}: {e.msg}")
            return False
        except Exception as e:
            logger.error(f"Error ending call {call_sid}: {str(e)}")
            return False

    async def aclose(self) -> None:
        try:
            await self._http.aclose()
        except Exception:
            pass
