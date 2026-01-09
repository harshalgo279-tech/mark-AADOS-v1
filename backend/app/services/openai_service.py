# backend/app/services/openai_service.py
"""
OpenAI Service (LEGACY path) with latency optimizations:
- LLM streaming for faster time-to-first-token
- Async file I/O for TTS cache
- Memory LRU cache for hot TTS audio
- Sentence extraction for parallel TTS generation

Notes:
- Twilio still handles telephony.
- This file provides STT + TTS using OpenAI for the <Gather>/<Play> pipeline.
- Realtime speech-to-speech uses OpenAIRealtimeService (separate file).
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import re
import time
from typing import Any, Callable, Dict, Optional, Tuple

import httpx

from app.config import settings
from app.utils.logger import logger

try:
    from openai import OpenAI, AsyncOpenAI
except Exception:
    OpenAI = None
    AsyncOpenAI = None

try:
    import aiofiles  # type: ignore
    AIOFILES_AVAILABLE = True
except ImportError:
    AIOFILES_AVAILABLE = False
    logger.warning("[OPTIMIZATION] aiofiles not installed - using sync file I/O")


SUPPORTED_TTS_VOICES = {
    "alloy", "ash", "ballad", "coral", "echo", "fable",
    "onyx", "nova", "sage", "shimmer",
}

SUPPORTED_TTS_FORMATS = {"mp3", "wav", "opus", "flac", "pcm"}


class TTSMemoryCache:
    def __init__(self, max_size: int = 50):
        self.max_size = max_size
        self._cache: Dict[str, bytes] = {}
        self._access_order: list[str] = []

    def get(self, key: str) -> Optional[bytes]:
        if key in self._cache:
            self._access_order.remove(key)
            self._access_order.append(key)
            return self._cache[key]
        return None

    def set(self, key: str, audio_bytes: bytes) -> None:
        if key in self._cache:
            self._access_order.remove(key)
        elif len(self._cache) >= self.max_size:
            oldest = self._access_order.pop(0)
            del self._cache[oldest]

        self._cache[key] = audio_bytes
        self._access_order.append(key)

    def clear(self) -> None:
        self._cache.clear()
        self._access_order.clear()


class OpenAIService:
    _http_client: Optional[httpx.AsyncClient] = None
    _async_client: Optional[Any] = None
    _tts_memory_cache: Optional[TTSMemoryCache] = None

    def __init__(self):
        self.client = None
        if OpenAI is not None and getattr(settings, "OPENAI_API_KEY", None):
            self.client = OpenAI(api_key=settings.OPENAI_API_KEY)

        self.model = (getattr(settings, "OPENAI_MODEL", None) or "gpt-4o-mini").strip()
        self.stt_model = (getattr(settings, "OPENAI_STT_MODEL", None) or "whisper-1").strip()
        self.tts_model = (getattr(settings, "OPENAI_TTS_MODEL", None) or "gpt-4o-mini-tts").strip()

        configured_voice = (getattr(settings, "OPENAI_TTS_VOICE", None) or "alloy").strip().lower()
        if configured_voice not in SUPPORTED_TTS_VOICES:
            logger.warning(
                f"[TTS] Unsupported voice '{configured_voice}'. Falling back to 'alloy'. "
                f"Supported: {sorted(SUPPORTED_TTS_VOICES)}"
            )
            configured_voice = "alloy"
        self.tts_voice = configured_voice

        try:
            self.tts_speed = float(getattr(settings, "OPENAI_TTS_SPEED", 1.0) or 1.0)
        except Exception:
            self.tts_speed = 1.0

        self.tts_cache_dir = (getattr(settings, "TTS_CACHE_DIR", None) or "storage/tts").strip()
        self._sentence_pattern = re.compile(r"(?<=[.!?])\s+")

    @classmethod
    def get_http_client(cls) -> httpx.AsyncClient:
        if cls._http_client is None:
            cls._http_client = httpx.AsyncClient(timeout=30.0)
        return cls._http_client

    @classmethod
    def get_async_client(cls) -> Optional[Any]:
        if cls._async_client is None and AsyncOpenAI is not None:
            api_key = getattr(settings, "OPENAI_API_KEY", None)
            if api_key:
                cls._async_client = AsyncOpenAI(api_key=api_key)
        return cls._async_client

    @classmethod
    def get_tts_memory_cache(cls) -> TTSMemoryCache:
        if cls._tts_memory_cache is None:
            cls._tts_memory_cache = TTSMemoryCache(max_size=50)
        return cls._tts_memory_cache

    @classmethod
    async def close_http_client(cls) -> None:
        if cls._http_client is not None:
            await cls._http_client.aclose()
            cls._http_client = None
        if cls._async_client is not None:
            await cls._async_client.close()
            cls._async_client = None

    def extract_first_sentence(self, text: str) -> Tuple[str, str]:
        if not text:
            return "", ""
        parts = self._sentence_pattern.split(text, maxsplit=1)
        if len(parts) == 1:
            return text.strip(), ""
        return parts[0].strip(), parts[1].strip() if len(parts) > 1 else ""

    async def generate_completion_streaming(
        self,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 300,
        timeout_s: float = 12.0,
        on_first_sentence: Optional[Callable[[str], None]] = None,
    ) -> str:
        async_client = self.get_async_client()
        if not async_client:
            return await self.generate_completion(prompt, temperature, max_tokens, timeout_s)

        llm_start = time.time()
        collected_text = ""
        first_sentence_sent = False
        ttft_logged = False

        try:
            stream = await asyncio.wait_for(
                async_client.chat.completions.create(
                    model=self.model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stream=True,
                    messages=[
                        {"role": "system", "content": "You are a helpful sales development assistant. Return only what is requested."},
                        {"role": "user", "content": prompt},
                    ],
                ),
                timeout=timeout_s,
            )

            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    token = chunk.choices[0].delta.content
                    collected_text += token

                    if not ttft_logged:
                        ttft = (time.time() - llm_start) * 1000
                        logger.info(f"[LATENCY] LLM TTFT: {ttft:.2f}ms (model={self.model})")
                        ttft_logged = True

                    if not first_sentence_sent and on_first_sentence:
                        if any(p in collected_text for p in [".", "!", "?"]):
                            first_sentence, _ = self.extract_first_sentence(collected_text)
                            if first_sentence:
                                first_sentence_sent = True
                                asyncio.create_task(asyncio.to_thread(on_first_sentence, first_sentence))

            llm_elapsed = (time.time() - llm_start) * 1000
            logger.info(f"[LATENCY] LLM streaming total: {llm_elapsed:.2f}ms (model={self.model})")
            return collected_text.strip()

        except asyncio.TimeoutError:
            llm_elapsed = (time.time() - llm_start) * 1000
            logger.warning(f"[LATENCY] LLM streaming timed out after {llm_elapsed:.2f}ms")
            return collected_text.strip() if collected_text else ""
        except Exception as e:
            llm_elapsed = (time.time() - llm_start) * 1000
            logger.error(f"[LATENCY] LLM streaming error after {llm_elapsed:.2f}ms: {e}")
            return await self.generate_completion(prompt, temperature, max_tokens, timeout_s)

    async def generate_completion(
        self,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 300,
        timeout_s: float = 12.0,
    ) -> str:
        async_client = self.get_async_client()
        if async_client:
            return await self.generate_completion_streaming(prompt, temperature, max_tokens, timeout_s)

        if not self.client:
            return "OK"

        llm_start = time.time()

        def _do():
            return self.client.chat.completions.create(
                model=self.model,
                temperature=temperature,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": "You are a helpful sales development assistant. Return only what is requested."},
                    {"role": "user", "content": prompt},
                ],
            )

        try:
            resp = await asyncio.wait_for(asyncio.to_thread(_do), timeout=timeout_s)
            llm_elapsed = (time.time() - llm_start) * 1000
            logger.info(f"[LATENCY] LLM completion: {llm_elapsed:.2f}ms (model={self.model})")
            return (resp.choices[0].message.content or "").strip()
        except asyncio.TimeoutError:
            llm_elapsed = (time.time() - llm_start) * 1000
            logger.warning(f"[LATENCY] LLM completion timed out after {llm_elapsed:.2f}ms")
            return ""
        except Exception as e:
            llm_elapsed = (time.time() - llm_start) * 1000
            logger.error(f"[LATENCY] LLM completion error after {llm_elapsed:.2f}ms: {e}")
            raise

    async def transcribe_audio(self, audio_bytes: bytes, filename: str = "recording.mp3") -> Optional[str]:
        if not self.client:
            return None

        try:
            import io
            f = io.BytesIO(audio_bytes)
            f.name = filename
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

    def is_tts_enabled(self) -> bool:
        return bool(getattr(settings, "OPENAI_API_KEY", None)) and bool(self.tts_model)

    def _tts_cache_key(self, text: str, model: str, voice: str, speed: float, fmt: str) -> str:
        raw = f"{model}|{voice}|{speed}|{fmt}|{text}".encode("utf-8")
        return hashlib.sha1(raw).hexdigest()

    async def tts_to_bytes(
        self,
        text: str,
        *,
        model: Optional[str] = None,
        voice: Optional[str] = None,
        speed: Optional[float] = None,
        response_format: str = "mp3",
        timeout_s: float = 20.0,
    ) -> bytes:
        if not self.is_tts_enabled():
            raise RuntimeError("TTS not enabled (missing OPENAI_API_KEY or OPENAI_TTS_MODEL)")

        model = (model or self.tts_model).strip()
        voice_val = (voice or self.tts_voice).strip().lower()
        if voice_val not in SUPPORTED_TTS_VOICES:
            logger.warning(f"[TTS] Unsupported voice '{voice_val}', falling back to 'alloy'")
            voice_val = "alloy"

        fmt = (response_format or "mp3").strip().lower()
        if fmt not in SUPPORTED_TTS_FORMATS:
            logger.warning(f"[TTS] Unknown response_format '{fmt}', using 'mp3'")
            fmt = "mp3"

        speed_val = self.tts_speed if speed is None else float(speed)
        speed_val = max(0.25, min(4.0, speed_val))

        text = (text or "").strip()
        if not text:
            raise ValueError("TTS text is empty")

        key = self._tts_cache_key(text, model, voice_val, speed_val, fmt)
        memory_cache = self.get_tts_memory_cache()
        cached = memory_cache.get(key)
        if cached:
            logger.info(f"[LATENCY] TTS memory cache hit: {key[:16]}...")
            return cached

        url = "https://api.openai.com/v1/audio/speech"
        headers = {
            "Authorization": f"Bearer {getattr(settings, 'OPENAI_API_KEY')}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "input": text[:4096],
            "voice": voice_val,
            "speed": speed_val,
            "response_format": fmt,
        }

        tts_api_start = time.time()
        client = self.get_http_client()
        resp = await client.post(url, headers=headers, json=payload, timeout=timeout_s)
        tts_api_elapsed = (time.time() - tts_api_start) * 1000

        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            logger.error(f"OpenAI TTS HTTP error {resp.status_code}: {resp.text[:500]}")
            raise e

        audio_bytes = resp.content
        memory_cache.set(key, audio_bytes)
        logger.info(f"[LATENCY] OpenAI TTS API call: {tts_api_elapsed:.2f}ms (voice={voice_val}, fmt={fmt})")
        return audio_bytes

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
        os.makedirs(self.tts_cache_dir, exist_ok=True)

        model = (model or self.tts_model).strip()
        voice_val = (voice or self.tts_voice).strip().lower()
        if voice_val not in SUPPORTED_TTS_VOICES:
            logger.warning(f"[TTS] Unsupported voice '{voice_val}', falling back to 'alloy'")
            voice_val = "alloy"

        fmt = (response_format or "mp3").strip().lower()
        if fmt not in SUPPORTED_TTS_FORMATS:
            logger.warning(f"[TTS] Unknown response_format '{fmt}', using 'mp3'")
            fmt = "mp3"

        speed_val = self.tts_speed if speed is None else float(speed)
        speed_val = max(0.25, min(4.0, speed_val))

        text = (text or "").strip()
        if not text:
            raise ValueError("TTS text is empty")

        key = self._tts_cache_key(text, model, voice_val, speed_val, fmt)
        filename = f"tts_{key}.{fmt}"
        filepath = os.path.join(self.tts_cache_dir, filename)

        memory_cache = self.get_tts_memory_cache()
        cached_bytes = memory_cache.get(key)
        if cached_bytes:
            if not os.path.exists(filepath):
                await self._write_file_async(filepath, cached_bytes)
            return os.path.abspath(filepath)

        if await self._file_exists_async(filepath):
            audio_bytes = await self._read_file_async(filepath)
            if audio_bytes:
                memory_cache.set(key, audio_bytes)
            return os.path.abspath(filepath)

        audio_bytes = await self.tts_to_bytes(
            text,
            model=model,
            voice=voice_val,
            speed=speed_val,
            response_format=fmt,
            timeout_s=timeout_s,
        )
        await self._write_file_async(filepath, audio_bytes)
        return os.path.abspath(filepath)

    async def _file_exists_async(self, filepath: str) -> bool:
        return await asyncio.to_thread(lambda: os.path.exists(filepath) and os.path.getsize(filepath) > 0)

    async def _read_file_async(self, filepath: str) -> Optional[bytes]:
        try:
            if AIOFILES_AVAILABLE:
                async with aiofiles.open(filepath, "rb") as f:
                    return await f.read()
            return await asyncio.to_thread(self._read_file_sync, filepath)
        except Exception as e:
            logger.warning(f"Failed to read file {filepath}: {e}")
            return None

    def _read_file_sync(self, filepath: str) -> bytes:
        with open(filepath, "rb") as f:
            return f.read()

    async def _write_file_async(self, filepath: str, data: bytes) -> None:
        try:
            if AIOFILES_AVAILABLE:
                async with aiofiles.open(filepath, "wb") as f:
                    await f.write(data)
            else:
                await asyncio.to_thread(self._write_file_sync, filepath, data)
        except Exception as e:
            logger.error(f"Failed to write file {filepath}: {e}")
            raise

    def _write_file_sync(self, filepath: str, data: bytes) -> None:
        with open(filepath, "wb") as f:
            f.write(data)
