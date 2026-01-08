# backend/app/services/openai_service.py
"""
OpenAI Service with latency optimizations:
- LLM streaming for faster time-to-first-token
- Async file I/O for TTS cache
- Memory LRU cache for hot TTS audio
- Sentence extraction for parallel TTS generation
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import re
import time
from functools import lru_cache
from typing import AsyncGenerator, Callable, Dict, Optional, Tuple, Any

import httpx

from app.config import settings
from app.utils.logger import logger

try:
    from openai import OpenAI, AsyncOpenAI
except Exception:
    OpenAI = None
    AsyncOpenAI = None

# Try to import aiofiles for async file I/O
try:
    import aiofiles  # type: ignore[import]
    AIOFILES_AVAILABLE = True
except ImportError:
    AIOFILES_AVAILABLE = False
    logger.warning("[OPTIMIZATION] aiofiles not installed - using sync file I/O")


class TTSMemoryCache:
    """
    LRU memory cache for recently used TTS audio files.
    Reduces disk I/O latency for hot audio files.
    """
    def __init__(self, max_size: int = 50):
        self.max_size = max_size
        self._cache: Dict[str, bytes] = {}
        self._access_order: list = []

    def get(self, key: str) -> Optional[bytes]:
        """Get audio bytes from cache."""
        if key in self._cache:
            # Move to end (most recently used)
            self._access_order.remove(key)
            self._access_order.append(key)
            return self._cache[key]
        return None

    def set(self, key: str, audio_bytes: bytes) -> None:
        """Add audio bytes to cache with LRU eviction."""
        if key in self._cache:
            self._access_order.remove(key)
        elif len(self._cache) >= self.max_size:
            # Evict least recently used
            oldest = self._access_order.pop(0)
            del self._cache[oldest]

        self._cache[key] = audio_bytes
        self._access_order.append(key)

    def clear(self) -> None:
        """Clear the cache."""
        self._cache.clear()
        self._access_order.clear()


class OpenAIService:
    # Class-level shared HTTP client for connection pooling
    _http_client: Optional[httpx.AsyncClient] = None
    # Class-level async OpenAI client for streaming
    _async_client: Optional[Any] = None
    # Class-level TTS memory cache
    _tts_memory_cache: Optional[TTSMemoryCache] = None

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

        # Pre-compiled regex for sentence extraction (latency optimization)
        self._sentence_pattern = re.compile(r'(?<=[.!?])\s+')

    @classmethod
    def get_http_client(cls) -> httpx.AsyncClient:
        """Get or create a shared HTTP client for connection pooling."""
        if cls._http_client is None:
            cls._http_client = httpx.AsyncClient(timeout=30.0)
        return cls._http_client

    @classmethod
    def get_async_client(cls) -> Optional[Any]:
        """Get or create async OpenAI client for streaming."""
        if cls._async_client is None and AsyncOpenAI is not None:
            api_key = getattr(settings, "OPENAI_API_KEY", None)
            if api_key:
                cls._async_client = AsyncOpenAI(api_key=api_key)
        return cls._async_client

    @classmethod
    def get_tts_memory_cache(cls) -> TTSMemoryCache:
        """Get or create TTS memory cache."""
        if cls._tts_memory_cache is None:
            cls._tts_memory_cache = TTSMemoryCache(max_size=50)
        return cls._tts_memory_cache

    @classmethod
    async def close_http_client(cls) -> None:
        """Close the shared HTTP client."""
        if cls._http_client is not None:
            await cls._http_client.aclose()
            cls._http_client = None
        if cls._async_client is not None:
            await cls._async_client.close()
            cls._async_client = None

    def extract_first_sentence(self, text: str) -> Tuple[str, str]:
        """
        Extract first sentence from text for early TTS generation.
        Returns (first_sentence, remaining_text).
        """
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
        """
        Streaming LLM completion with optional callback on first sentence.
        Enables parallel TTS generation while LLM continues streaming.

        Args:
            prompt: The prompt to complete
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            timeout_s: Timeout in seconds
            on_first_sentence: Callback when first sentence is complete

        Returns:
            Complete response text
        """
        async_client = self.get_async_client()
        if not async_client:
            # Fallback to non-streaming
            return await self.generate_completion(prompt, temperature, max_tokens, timeout_s)

        llm_start = time.time()
        collected_text = ""
        first_sentence_sent = False
        ttft_logged = False  # Time to first token

        try:
            stream = await asyncio.wait_for(
                async_client.chat.completions.create(
                    model=self.model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stream=True,
                    messages=[
                        {
                            "role": "system",
                            "content": "You are a helpful sales development assistant. Return only what is requested.",
                        },
                        {"role": "user", "content": prompt},
                    ],
                ),
                timeout=timeout_s
            )

            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    token = chunk.choices[0].delta.content
                    collected_text += token

                    # Log time to first token
                    if not ttft_logged:
                        ttft = (time.time() - llm_start) * 1000
                        logger.info(f"[LATENCY] LLM TTFT (time-to-first-token): {ttft:.2f}ms")
                        ttft_logged = True

                    # Check for first sentence completion
                    if not first_sentence_sent and on_first_sentence:
                        # Look for sentence-ending punctuation
                        if any(p in collected_text for p in ['.', '!', '?']):
                            first_sentence, _ = self.extract_first_sentence(collected_text)
                            if first_sentence:
                                first_sentence_sent = True
                                # Fire callback asynchronously
                                asyncio.create_task(
                                    asyncio.to_thread(on_first_sentence, first_sentence)
                                )

            llm_elapsed = (time.time() - llm_start) * 1000
            logger.info(f"[LATENCY] OpenAI streaming completion: {llm_elapsed:.2f}ms (model={self.model})")
            return collected_text.strip()

        except asyncio.TimeoutError:
            llm_elapsed = (time.time() - llm_start) * 1000
            logger.warning(f"[LATENCY] OpenAI streaming timed out after {llm_elapsed:.2f}ms")
            return collected_text.strip() if collected_text else ""
        except Exception as e:
            llm_elapsed = (time.time() - llm_start) * 1000
            logger.error(f"[LATENCY] OpenAI streaming error after {llm_elapsed:.2f}ms: {e}")
            # Fallback to non-streaming on error
            return await self.generate_completion(prompt, temperature, max_tokens, timeout_s)

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
        Now uses streaming by default for faster TTFT.
        """
        # Try streaming first for better latency
        async_client = self.get_async_client()
        if async_client:
            return await self.generate_completion_streaming(
                prompt, temperature, max_tokens, timeout_s
            )

        # Fallback to sync client
        if not self.client:
            return "OK"

        llm_start = time.time()

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
            llm_elapsed = (time.time() - llm_start) * 1000
            logger.info(f"[LATENCY] OpenAI completion: {llm_elapsed:.2f}ms (model={self.model})")
            return (resp.choices[0].message.content or "").strip()
        except asyncio.TimeoutError:
            llm_elapsed = (time.time() - llm_start) * 1000
            logger.warning(f"[LATENCY] OpenAI completion timed out after {llm_elapsed:.2f}ms")
            return ""
        except Exception as e:
            llm_elapsed = (time.time() - llm_start) * 1000
            logger.error(f"[LATENCY] OpenAI completion error after {llm_elapsed:.2f}ms: {e}")
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

        Optimizations:
        - Memory LRU cache for hot audio files
        - Async file I/O with aiofiles (if available)
        - Connection pooling via shared HTTP client
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

        # Check memory cache first (fastest)
        memory_cache = self.get_tts_memory_cache()
        cached_bytes = memory_cache.get(key)
        if cached_bytes:
            # Ensure file exists on disk too
            if not os.path.exists(filepath):
                await self._write_file_async(filepath, cached_bytes)
            logger.info(f"[LATENCY] TTS memory cache hit: {key[:16]}...")
            return os.path.abspath(filepath)

        # Check disk cache (async check)
        if await self._file_exists_async(filepath):
            # Load into memory cache for next time
            audio_bytes = await self._read_file_async(filepath)
            if audio_bytes:
                memory_cache.set(key, audio_bytes)
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

        tts_api_start = time.time()

        try:
            # Use shared HTTP client for connection pooling (latency optimization)
            client = self.get_http_client()
            resp = await client.post(url, headers=headers, json=payload, timeout=timeout_s)
            tts_api_elapsed = (time.time() - tts_api_start) * 1000
            try:
                resp.raise_for_status()
            except httpx.HTTPStatusError as e:
                # Log response body so you can see "invalid voice" etc.
                logger.error(f"OpenAI TTS HTTP error {resp.status_code}: {resp.text[:500]}")
                raise e
            audio_bytes = resp.content

            # Write to disk (async if available)
            await self._write_file_async(filepath, audio_bytes)

            # Add to memory cache
            memory_cache.set(key, audio_bytes)

            logger.info(f"[LATENCY] OpenAI TTS API call: {tts_api_elapsed:.2f}ms (voice={voice})")
            return os.path.abspath(filepath)

        except Exception as e:
            tts_api_elapsed = (time.time() - tts_api_start) * 1000
            # clean partial file
            try:
                if os.path.exists(filepath):
                    os.remove(filepath)
            except Exception:
                pass
            logger.error(f"[LATENCY] OpenAI TTS error after {tts_api_elapsed:.2f}ms: {e}")
            raise

    async def _file_exists_async(self, filepath: str) -> bool:
        """Check if file exists (async-friendly)."""
        return await asyncio.to_thread(
            lambda: os.path.exists(filepath) and os.path.getsize(filepath) > 0
        )

    async def _read_file_async(self, filepath: str) -> Optional[bytes]:
        """Read file bytes asynchronously."""
        try:
            if AIOFILES_AVAILABLE:
                async with aiofiles.open(filepath, 'rb') as f:
                    return await f.read()
            else:
                return await asyncio.to_thread(self._read_file_sync, filepath)
        except Exception as e:
            logger.warning(f"Failed to read file {filepath}: {e}")
            return None

    def _read_file_sync(self, filepath: str) -> bytes:
        """Sync file read for fallback."""
        with open(filepath, 'rb') as f:
            return f.read()

    async def _write_file_async(self, filepath: str, data: bytes) -> None:
        """Write file bytes asynchronously."""
        try:
            if AIOFILES_AVAILABLE:
                async with aiofiles.open(filepath, 'wb') as f:
                    await f.write(data)
            else:
                await asyncio.to_thread(self._write_file_sync, filepath, data)
        except Exception as e:
            logger.error(f"Failed to write file {filepath}: {e}")
            raise

    def _write_file_sync(self, filepath: str, data: bytes) -> None:
        """Sync file write for fallback."""
        with open(filepath, 'wb') as f:
            f.write(data)
