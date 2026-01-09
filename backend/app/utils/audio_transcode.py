# backend/app/utils/audio_transcode.py
from __future__ import annotations

import audioop


def ulaw8k_to_pcm16_24k(ulaw_bytes: bytes) -> bytes:
    """
    Twilio Media Streams audio is typically 8kHz μ-law (PCMU).
    Convert to PCM16 @ 24kHz for OpenAI realtime input.
    """
    if not ulaw_bytes:
        return b""

    pcm16_8k = audioop.ulaw2lin(ulaw_bytes, 2)  # 16-bit
    pcm16_24k, _ = audioop.ratecv(pcm16_8k, 2, 1, 8000, 24000, None)
    return pcm16_24k
