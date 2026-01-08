# backend/app/utils/model_warmup.py
"""
Model warm-up utility to reduce cold-start latency.
Pre-loads LLM and TTS models at startup.
"""

import asyncio
from typing import Optional
from app.utils.logger import logger


class ModelWarmupHandler:
    """
    Pre-warm models at startup to reduce first-request latency.
    Typical cold start: 2-3s
    Warm start: 800-1500ms
    """

    @staticmethod
    async def warmup_llm(openai_service) -> bool:
        """
        Warm up OpenAI LLM with a simple request.

        Args:
            openai_service: OpenAIService instance

        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info("[WARMUP] Starting LLM warm-up...")
            prompt = "Respond with 'Ready' in one word only."

            response = await openai_service.generate_completion(
                prompt=prompt,
                temperature=0.5,
                max_tokens=10,
                timeout_s=30.0,  # Generous timeout for cold start
            )

            if response:
                logger.info(f"[WARMUP] LLM ready: {response}")
                return True
            else:
                logger.warning("[WARMUP] LLM warm-up returned empty response")
                return False

        except Exception as e:
            logger.error(f"[WARMUP] LLM warm-up failed: {e}")
            return False

    @staticmethod
    async def warmup_tts(voice_agent, openai_service) -> bool:
        """
        Warm up TTS by pre-generating common phrases.

        Args:
            voice_agent: VoiceAgent instance
            openai_service: OpenAIService instance

        Returns:
            True if all phrases cached, False if any failed
        """
        try:
            logger.info("[WARMUP] Starting TTS warm-up...")

            # Use existing pre-heat method if available
            if hasattr(voice_agent, "preheat_tts_cache"):
                await voice_agent.preheat_tts_cache()
                logger.info("[WARMUP] TTS cache pre-heated via voice agent")
                return True
            else:
                logger.warning("[WARMUP] Voice agent TTS pre-heat method not found")
                return False

        except Exception as e:
            logger.error(f"[WARMUP] TTS warm-up failed: {e}")
            return False

    @staticmethod
    async def warmup_http_pool() -> bool:
        """
        Warm up HTTP connection pool.
        Ensures pooled connections are ready for TTS API calls.

        Returns:
            True if successful
        """
        try:
            logger.info("[WARMUP] Warming up HTTP connection pool...")
            # Get shared client (creates if doesn't exist)
            from app.services.openai_service import OpenAIService

            client = OpenAIService.get_http_client()
            logger.info("[WARMUP] HTTP connection pool ready")
            return True

        except Exception as e:
            logger.error(f"[WARMUP] HTTP pool warm-up failed: {e}")
            return False

    @staticmethod
    async def run_full_warmup(voice_agent, openai_service) -> dict:
        """
        Run complete warm-up sequence.

        Args:
            voice_agent: VoiceAgent instance
            openai_service: OpenAIService instance

        Returns:
            Dict with warm-up results
        """
        logger.info("[WARMUP] ========== STARTING FULL MODEL WARM-UP ==========")

        # Run all warm-ups in parallel
        results = await asyncio.gather(
            ModelWarmupHandler.warmup_llm(openai_service),
            ModelWarmupHandler.warmup_tts(voice_agent, openai_service),
            ModelWarmupHandler.warmup_http_pool(),
            return_exceptions=True,
        )

        llm_ok = results[0] if isinstance(results[0], bool) else False
        tts_ok = results[1] if isinstance(results[1], bool) else False
        http_ok = results[2] if isinstance(results[2], bool) else False

        warmup_report = {
            "llm_ready": llm_ok,
            "tts_ready": tts_ok,
            "http_pool_ready": http_ok,
            "all_ready": all([llm_ok, tts_ok, http_ok]),
        }

        if warmup_report["all_ready"]:
            logger.info(
                "[WARMUP] ========== WARM-UP COMPLETE: ALL SYSTEMS READY =========="
            )
        else:
            logger.warning(
                f"[WARMUP] ========== WARM-UP PARTIAL: {warmup_report} =========="
            )

        return warmup_report


async def warmup_models_on_startup(voice_agent, openai_service) -> dict:
    """
    Convenience function to warmup models on application startup.

    Args:
        voice_agent: VoiceAgent instance
        openai_service: OpenAIService instance

    Returns:
        Warm-up results
    """
    handler = ModelWarmupHandler()
    return await handler.run_full_warmup(voice_agent, openai_service)
