# backend/app/utils/latency_tracker.py
"""
Latency tracking utility for measuring end-to-end response times.
Tracks timing at each pipeline stage: prompt building, LLM inference, TTS generation.
"""

import time
from typing import Dict, Optional
from app.utils.logger import logger


class LatencyTracker:
    """
    Track latency across multiple stages of the voice pipeline.

    Usage:
        tracker = LatencyTracker(call_id=123)
        tracker.mark("prompt_start")
        # ... do work ...
        tracker.mark("prompt_end")
        tracker.mark("llm_start")
        # ... call LLM ...
        tracker.mark("llm_end")
        tracker.mark("tts_start")
        # ... generate TTS ...
        tracker.mark("tts_end")
        tracker.log_metrics()
    """

    def __init__(self, call_id: int):
        self.call_id = call_id
        self.timestamps: Dict[str, float] = {}
        self.start_time = time.time()

    def mark(self, stage: str) -> None:
        """Record a timestamp for a stage."""
        self.timestamps[stage] = time.time()

    def elapsed(self, start_stage: str, end_stage: str) -> Optional[float]:
        """Get elapsed time between two stages in milliseconds."""
        if start_stage not in self.timestamps or end_stage not in self.timestamps:
            return None
        return (self.timestamps[end_stage] - self.timestamps[start_stage]) * 1000

    def total_elapsed(self) -> float:
        """Get total elapsed time from tracker creation in milliseconds."""
        return (time.time() - self.start_time) * 1000

    def log_metrics(self) -> None:
        """Log all tracked metrics."""
        total = self.total_elapsed()

        prompt_time = self.elapsed("prompt_start", "prompt_end")
        llm_time = self.elapsed("llm_start", "llm_end")
        tts_time = self.elapsed("tts_start", "tts_end")

        metrics = {
            "call_id": self.call_id,
            "total_ms": round(total, 2),
            "prompt_ms": round(prompt_time, 2) if prompt_time else None,
            "llm_ms": round(llm_time, 2) if llm_time else None,
            "tts_ms": round(tts_time, 2) if tts_time else None,
        }

        logger.info(f"[LATENCY] {metrics}")
        return metrics

    def get_summary(self) -> Dict:
        """Return latency summary as dict."""
        total = self.total_elapsed()
        prompt_time = self.elapsed("prompt_start", "prompt_end")
        llm_time = self.elapsed("llm_start", "llm_end")
        tts_time = self.elapsed("tts_start", "tts_end")

        return {
            "call_id": self.call_id,
            "total_ms": round(total, 2),
            "prompt_ms": round(prompt_time, 2) if prompt_time else None,
            "llm_ms": round(llm_time, 2) if llm_time else None,
            "tts_ms": round(tts_time, 2) if tts_time else None,
        }
