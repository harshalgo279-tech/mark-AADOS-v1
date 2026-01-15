# backend/app/services/openai_service.py
from __future__ import annotations

import asyncio
from typing import Optional

from app.config import settings
from app.utils.logger import logger

try:
    from openai import OpenAI
except Exception:
    OpenAI = None


class OpenAIService:
    """
    Text-only OpenAI wrapper.
    Voice (STT/TTS) removed so you can migrate voice to ElevenLabs.
    """

    def __init__(self):
        self.client = None
        if OpenAI is not None and getattr(settings, "OPENAI_API_KEY", None):
            self.client = OpenAI(api_key=settings.OPENAI_API_KEY)

        # Chat defaults
        self.model = (getattr(settings, "OPENAI_MODEL", None) or "gpt-4o-mini").strip()

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
