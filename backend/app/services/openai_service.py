# backend/app/services/openai_service.py
from __future__ import annotations

import asyncio
import hashlib
import os
from typing import Optional

import httpx

from app.config import settings
from app.utils.logger import logger

try:
    from openai import OpenAI
except Exception:
    OpenAI = None


class OpenAIService:
    def __init__(self):
        self.client = None
        if OpenAI is not None and getattr(settings, "OPENAI_API_KEY", None):
            self.client = OpenAI(api_key=settings.OPENAI_API_KEY)

        # Chat defaults
        self.model = (getattr(settings, "OPENAI_MODEL", None) or "gpt-4o-mini").strip()
        self.stt_model = (getattr(settings, "OPENAI_STT_MODEL", None) or "whisper-1").strip()

        # TTS defaults
        self.tts_model = (getattr(settings, "OPENAI_TTS_MODEL", None) or "gpt-4o-mini-tts").strip()

        # IMPORTANT: default to cedar if not provided (your desired behavior)
        self.tts_voice = (getattr(settings, "OPENAI_TTS_VOICE", None) or "cedar").strip().lower()

        try:
            self.tts_speed = float(getattr(settings, "OPENAI_TTS_SPEED", 1.0) or 1.0)
        except Exception:
            self.tts_speed = 1.0

        self.tts_cache_dir = (getattr(settings, "TTS_CACHE_DIR", None) or "storage/tts").strip()

    async def generate_completion(
        self,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 300,
        timeout_s: float = 12.0,
    ) -> str:
        """
        Lower-latency friendly wrapper.
        Returns "" on timeout so caller can fallback.
        """
        if not self.client:
            return "OK"

        def _do():
            return self.client.chat.completions.create(
                model=self.model,
                temperature=temperature,
                max_tokens=max_tokens,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a helpful sales development assistant. Return only what is requested.",
                    },
                    {"role": "user", "content": prompt},
                ],
            )

        try:
            resp = await asyncio.wait_for(asyncio.to_thread(_do), timeout=timeout_s)
            return (resp.choices[0].message.content or "").strip()
        except asyncio.TimeoutError:
            logger.warning("OpenAI completion timed out")
            return ""
        except Exception as e:
            logger.error(f"OpenAI completion error: {e}")
            raise

    async def transcribe_audio(self, audio_bytes: bytes) -> Optional[str]:
        if not self.client:
            return None

        try:
            import io

            f = io.BytesIO(audio_bytes)
            f.name = "recording.mp3"

            resp = await asyncio.to_thread(
                self.client.audio.transcriptions.create,
                model=self.stt_model,
                file=f,
            )

            text = getattr(resp, "text", None)
            return text.strip() if text else None

        except Exception as e:
            logger.error(f"OpenAI transcription error: {e}")
            raise

    # -------------------------
    # OpenAI TTS helpers
    # -------------------------

    def is_tts_enabled(self) -> bool:
        return bool(getattr(settings, "OPENAI_API_KEY", None)) and bool(self.tts_model)

    def _tts_cache_key(self, text: str, model: str, voice: str, speed: float, fmt: str) -> str:
        raw = f"{model}|{voice}|{speed}|{fmt}|{text}".encode("utf-8")
        return hashlib.sha1(raw).hexdigest()

    async def tts_to_file(
        self,
        text: str,
        *,
        model: Optional[str] = None,
        voice: Optional[str] = None,
        speed: Optional[float] = None,
        response_format: str = "mp3",
        timeout_s: float = 20.0,
    ) -> str:
        """
        Generates TTS audio via OpenAI Audio API and caches to disk.
        Returns absolute filepath.

        Uses REST call to /v1/audio/speech.
        """
        if not self.is_tts_enabled():
            raise RuntimeError("TTS not enabled (missing OPENAI_API_KEY or OPENAI_TTS_MODEL)")

        model = (model or self.tts_model).strip()
        voice = (voice or self.tts_voice).strip().lower()

        speed_val = self.tts_speed if speed is None else float(speed)
        speed_val = max(0.25, min(4.0, speed_val))

        text = (text or "").strip()
        if not text:
            raise ValueError("TTS text is empty")

        os.makedirs(self.tts_cache_dir, exist_ok=True)

        key = self._tts_cache_key(text, model, voice, speed_val, response_format)
        filename = f"tts_{key}.{response_format}"
        filepath = os.path.join(self.tts_cache_dir, filename)

        if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
            return os.path.abspath(filepath)

        url = "https://api.openai.com/v1/audio/speech"
        headers = {
            "Authorization": f"Bearer {getattr(settings, 'OPENAI_API_KEY')}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "input": text[:4096],
            "voice": voice,
            "speed": speed_val,
            "response_format": response_format,
        }

        try:
            async with httpx.AsyncClient(timeout=timeout_s) as client:
                resp = await client.post(url, headers=headers, json=payload)
                try:
                    resp.raise_for_status()
                except httpx.HTTPStatusError as e:
                    # Log response body so you can see "invalid voice" etc.
                    logger.error(f"OpenAI TTS HTTP error {resp.status_code}: {resp.text[:500]}")
                    raise e
                audio_bytes = resp.content

            with open(filepath, "wb") as f:
                f.write(audio_bytes)

            return os.path.abspath(filepath)

        except Exception as e:
            # clean partial file
            try:
                if os.path.exists(filepath):
                    os.remove(filepath)
            except Exception:
                pass
            logger.error(f"OpenAI TTS error: {e}")
            raise
