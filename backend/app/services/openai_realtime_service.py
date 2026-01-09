from __future__ import annotations
import base64, json, asyncio
from typing import AsyncGenerator, Optional
import websockets
from app.config import settings
from app.utils.logger import logger

OPENAI_WS = "wss://api.openai.com/v1/realtime?model=gpt-realtime"

class OpenAIRealtimeService:
    def __init__(self):
        self.api_key = settings.OPENAI_API_KEY
        self.ws: Optional[websockets.WebSocketClientProtocol] = None

    async def connect(self):
        """Establish WebSocket connection to OpenAI Realtime API"""
        try:
            self.ws = await websockets.connect(
                OPENAI_WS,
                extra_headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "OpenAI-Beta": "realtime=v1",
                },
                max_size=2**24,
            )

            await self.ws.send(json.dumps({
                "type": "session.update",
                "session": {
                    "modalities": ["audio", "text"],
                    "input_audio_format": "pcm16",
                    "output_audio_format": "pcm16",
                    "voice": "ash",
                    "input_audio_transcription": {
                        "model": "gpt-4o-transcribe"
                    },
                    "turn_detection": {"type": "semantic_vad"},
                    "instructions": "You are AADOS, a natural phone sales agent. Speak clearly, short sentences."
                }
            }))
            logger.info("[OpenAI Realtime] Connected successfully")
        except Exception as e:
            logger.error(f"[OpenAI Realtime] Connection failed: {e}")
            raise

    async def send_pcm16(self, pcm16: bytes):
        """Send PCM16 audio to OpenAI (legacy method name for compatibility)"""
        await self.send_audio_pcm16(pcm16)

    async def send_audio_pcm16(self, pcm16: bytes):
        """Send PCM16 audio buffer to OpenAI Realtime API"""
        if not self.ws:
            raise RuntimeError("WebSocket not connected. Call connect() first.")

        try:
            await self.ws.send(json.dumps({
                "type": "input_audio_buffer.append",
                "audio": base64.b64encode(pcm16).decode()
            }))
        except Exception as e:
            logger.error(f"[OpenAI Realtime] Failed to send audio: {e}")
            raise

    async def commit_audio(self):
        """Commit the audio buffer (optional, mainly for manual control)"""
        if not self.ws:
            raise RuntimeError("WebSocket not connected")

        try:
            await self.ws.send(json.dumps({"type": "input_audio_buffer.commit"}))
        except Exception as e:
            logger.error(f"[OpenAI Realtime] Failed to commit audio: {e}")
            raise

    async def create_response(self, instructions: str):
        """
        Request the model to generate a response with specific instructions.
        This is used to provide context-specific prompts for each turn.
        """
        if not self.ws:
            raise RuntimeError("WebSocket not connected")

        try:
            await self.ws.send(json.dumps({
                "type": "response.create",
                "response": {
                    "modalities": ["audio", "text"],
                    "instructions": instructions
                }
            }))
            logger.info(f"[OpenAI Realtime] Created response with instructions: {instructions[:100]}...")
        except Exception as e:
            logger.error(f"[OpenAI Realtime] Failed to create response: {e}")
            raise

    async def events(self) -> AsyncGenerator[dict, None]:
        """Async generator that yields events from the OpenAI Realtime API"""
        if not self.ws:
            raise RuntimeError("WebSocket not connected")

        try:
            async for msg in self.ws:
                yield json.loads(msg)
        except websockets.exceptions.ConnectionClosed:
            logger.info("[OpenAI Realtime] Connection closed")
        except Exception as e:
            logger.error(f"[OpenAI Realtime] Error in event stream: {e}")
            raise

    async def close(self):
        """Close the WebSocket connection gracefully"""
        if self.ws:
            try:
                await self.ws.close()
                logger.info("[OpenAI Realtime] Connection closed successfully")
            except Exception as e:
                logger.warning(f"[OpenAI Realtime] Error during close: {e}")
            finally:
                self.ws = None
