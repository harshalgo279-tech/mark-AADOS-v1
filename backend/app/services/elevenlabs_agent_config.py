# backend/app/services/elevenlabs_agent_config.py
"""
ElevenLabs Agent Configuration Service
Updates agent prompts, voice settings, and conversation config
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional, List
import httpx

from app.config import settings
from app.utils.logger import logger
from app.agents.sales_control_plane import (
    generate_elevenlabs_agent_prompt,
    generate_enhanced_prompt,
    generate_voice_settings,
    generate_conversation_config,
    get_or_create_tracker,
    ConversationTracker,
)


class ElevenLabsAgentConfig:
    """
    Service to configure and update ElevenLabs conversational AI agents.
    """

    def __init__(self):
        self.api_key = (getattr(settings, "ELEVENLABS_API_KEY", "") or "").strip()
        self.agent_id = (getattr(settings, "ELEVENLABS_AGENT_ID", "") or "").strip()
        self.voice_id = (getattr(settings, "ELEVENLABS_VOICE_ID", "") or "").strip()
        self.base_url = "https://api.elevenlabs.io"
        self._http = httpx.AsyncClient(timeout=30)

        if not self.api_key:
            logger.warning("ELEVENLABS_API_KEY is missing")
        if not self.agent_id:
            logger.warning("ELEVENLABS_AGENT_ID is missing")

    def _headers(self) -> Dict[str, str]:
        return {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
        }

    async def get_agent_config(self, agent_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get current agent configuration from ElevenLabs.
        """
        agent = (agent_id or self.agent_id).strip()
        if not agent:
            raise RuntimeError("ELEVENLABS_AGENT_ID missing")

        url = f"{self.base_url}/v1/convai/agents/{agent}"

        try:
            resp = await self._http.get(url, headers=self._headers())
            if resp.status_code >= 400:
                logger.error(f"ElevenLabs get_agent error {resp.status_code}: {resp.text[:500]}")
                return {}

            return resp.json()
        except Exception as e:
            logger.error(f"ElevenLabs get_agent exception: {e}")
            return {}

    async def update_agent_prompt(
        self,
        prompt: str,
        agent_id: Optional[str] = None,
        first_message: Optional[str] = None,
    ) -> bool:
        """
        Update the agent's system prompt with automatic call ending configuration.
        """
        agent = (agent_id or self.agent_id).strip()
        if not agent:
            raise RuntimeError("ELEVENLABS_AGENT_ID missing")

        url = f"{self.base_url}/v1/convai/agents/{agent}"

        # Include call ending configuration with the prompt
        payload: Dict[str, Any] = {
            "conversation_config": {
                "agent": {
                    "prompt": {
                        "prompt": prompt,
                    },
                    # Tools for the agent including end_call
                    "tools": [
                        {
                            "type": "end_call",
                            "name": "end_call",
                            "description": "End the phone call. Use this immediately after delivering your final closing statement. Do not wait for the prospect to hang up.",
                        }
                    ],
                },
                # Conversation settings for automatic call ending
                "conversation": {
                    "max_duration_seconds": 600,
                    # Phrases that trigger automatic call ending when spoken by the agent
                    "client_events": {
                        "end_call_phrases": [
                            "goodbye",
                            "bye",
                            "take care",
                            "talk soon",
                            "talk to you soon",
                            "looking forward to it",
                            "have a good day",
                            "have a great day",
                            "thanks for your time",
                            "thank you for your time",
                            "i appreciate your time",
                            "i'll remove you from our list",
                        ],
                    },
                },
            }
        }

        if first_message:
            payload["conversation_config"]["agent"]["first_message"] = first_message

        try:
            resp = await self._http.patch(url, headers=self._headers(), json=payload)
            if resp.status_code >= 400:
                logger.error(f"ElevenLabs update_prompt error {resp.status_code}: {resp.text[:500]}")
                return False

            logger.info(f"ElevenLabs agent prompt updated with end_call config for agent_id={agent}")
            return True
        except Exception as e:
            logger.error(f"ElevenLabs update_prompt exception: {e}")
            return False

    async def update_voice_settings(
        self,
        voice_id: Optional[str] = None,
        stability: float = 0.75,
        similarity_boost: float = 0.80,
        style: float = 0.35,
        use_speaker_boost: bool = True,
        agent_id: Optional[str] = None,
    ) -> bool:
        """
        Update the agent's voice settings for better clarity and volume.
        """
        agent = (agent_id or self.agent_id).strip()
        voice = (voice_id or self.voice_id).strip()

        if not agent:
            raise RuntimeError("ELEVENLABS_AGENT_ID missing")

        url = f"{self.base_url}/v1/convai/agents/{agent}"

        payload: Dict[str, Any] = {
            "conversation_config": {
                "tts": {
                    "model_id": "eleven_turbo_v2_5",  # Latest turbo model
                    "voice_settings": {
                        "stability": stability,
                        "similarity_boost": similarity_boost,
                        "style": style,
                        "use_speaker_boost": use_speaker_boost,
                    },
                    "optimize_streaming_latency": 3,
                }
            }
        }

        if voice:
            payload["conversation_config"]["tts"]["voice_id"] = voice

        try:
            resp = await self._http.patch(url, headers=self._headers(), json=payload)
            if resp.status_code >= 400:
                logger.error(f"ElevenLabs update_voice error {resp.status_code}: {resp.text[:500]}")
                return False

            logger.info(f"ElevenLabs voice settings updated for agent_id={agent}")
            return True
        except Exception as e:
            logger.error(f"ElevenLabs update_voice exception: {e}")
            return False

    async def update_full_agent_config(
        self,
        lead_name: str = "",
        lead_company: str = "",
        lead_title: str = "",
        lead_industry: str = "",
        use_cases: List[Dict[str, str]] = None,
        company_analysis: str = "",
        agent_id: Optional[str] = None,
        conversation_id: Optional[str] = None,  # NEW: For context injection
    ) -> Dict[str, bool]:
        """
        Update the agent with full sales control plane configuration.
        Returns dict with success status for each update.

        If conversation_id is provided, injects real-time conversation context
        to prevent repetition and enable adaptive responses.
        """
        agent = (agent_id or self.agent_id).strip()
        use_cases = use_cases or []

        results = {
            "prompt_updated": False,
            "voice_updated": False,
        }

        # Get conversation context if available
        conversation_context = ""
        if conversation_id:
            tracker = get_or_create_tracker(conversation_id)
            conversation_context = tracker.get_context_summary()
            logger.info(f"Injecting conversation context for conversation_id={conversation_id}")

        # Generate the comprehensive prompt (with context if available)
        if conversation_context:
            prompt = generate_enhanced_prompt(
                lead_name=lead_name,
                lead_company=lead_company,
                lead_title=lead_title,
                lead_industry=lead_industry,
                use_cases=use_cases,
                company_analysis=company_analysis,
                conversation_context=conversation_context,
            )
        else:
            prompt = generate_elevenlabs_agent_prompt(
                lead_name=lead_name,
                lead_company=lead_company,
                lead_title=lead_title,
                lead_industry=lead_industry,
                use_cases=use_cases,
                company_analysis=company_analysis,
            )

        # Generate first message based on lead
        first_message = f"Hi{' ' + lead_name if lead_name else ''}, this is AADOS calling from Algonox. Did I catch you at a bad time?"

        # Update prompt
        results["prompt_updated"] = await self.update_agent_prompt(
            prompt=prompt,
            first_message=first_message,
            agent_id=agent,
        )

        # Update voice settings for clarity
        results["voice_updated"] = await self.update_voice_settings(
            stability=0.75,
            similarity_boost=0.80,
            style=0.35,
            use_speaker_boost=True,
            agent_id=agent,
        )

        return results

    async def configure_for_call(
        self,
        lead_name: str,
        lead_company: str,
        lead_title: str = "",
        lead_industry: str = "",
        data_packet: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Configure the agent for a specific call with lead context.
        Call this before initiating a call to personalize the agent.
        """
        use_cases = []
        company_analysis = ""

        if data_packet:
            company_analysis = data_packet.get("company_analysis", "")

            for i in range(1, 4):
                title = data_packet.get(f"use_case_{i}_title", "")
                desc = data_packet.get(f"use_case_{i}_description", "")
                impact = data_packet.get(f"use_case_{i}_impact", "")
                if title:
                    use_cases.append({
                        "title": title,
                        "description": desc,
                        "impact": impact,
                    })

        results = await self.update_full_agent_config(
            lead_name=lead_name,
            lead_company=lead_company,
            lead_title=lead_title,
            lead_industry=lead_industry,
            use_cases=use_cases,
            company_analysis=company_analysis,
        )

        return results.get("prompt_updated", False) and results.get("voice_updated", False)

    async def list_voices(self) -> List[Dict[str, Any]]:
        """
        List available voices for selection.
        """
        url = f"{self.base_url}/v1/voices"

        try:
            resp = await self._http.get(url, headers=self._headers())
            if resp.status_code >= 400:
                logger.error(f"ElevenLabs list_voices error {resp.status_code}: {resp.text[:500]}")
                return []

            data = resp.json()
            return data.get("voices", [])
        except Exception as e:
            logger.error(f"ElevenLabs list_voices exception: {e}")
            return []

    async def get_voice_settings(self, voice_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get current voice settings.
        """
        voice = (voice_id or self.voice_id).strip()
        if not voice:
            return {}

        url = f"{self.base_url}/v1/voices/{voice}/settings"

        try:
            resp = await self._http.get(url, headers=self._headers())
            if resp.status_code >= 400:
                logger.error(f"ElevenLabs get_voice_settings error {resp.status_code}: {resp.text[:500]}")
                return {}

            return resp.json()
        except Exception as e:
            logger.error(f"ElevenLabs get_voice_settings exception: {e}")
            return {}

    async def aclose(self) -> None:
        try:
            await self._http.aclose()
        except Exception:
            pass


# Recommended voice configurations for different scenarios
VOICE_PRESETS = {
    "professional_clear": {
        "description": "Professional, clear voice optimized for business calls",
        "stability": 0.75,
        "similarity_boost": 0.80,
        "style": 0.35,
        "use_speaker_boost": True,
    },
    "warm_conversational": {
        "description": "Warm, friendly voice for relationship building",
        "stability": 0.65,
        "similarity_boost": 0.75,
        "style": 0.50,
        "use_speaker_boost": True,
    },
    "energetic_persuasive": {
        "description": "Energetic voice for engaged prospects",
        "stability": 0.55,
        "similarity_boost": 0.70,
        "style": 0.65,
        "use_speaker_boost": True,
    },
    "calm_consultative": {
        "description": "Calm, measured voice for complex discussions",
        "stability": 0.85,
        "similarity_boost": 0.85,
        "style": 0.25,
        "use_speaker_boost": True,
    },
}
