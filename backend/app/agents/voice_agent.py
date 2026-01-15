# backend/app/agents/voice_agent.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.models.call import Call
from app.models.lead import Lead
from app.services.twilio_service import TwilioService
from app.services.elevenlabs_service import ElevenLabsService
from app.services.realtime_monitor import start_realtime_monitor, stop_realtime_monitor
from app.api.websocket import broadcast_activity
from app.utils.logger import logger

# Import DataPacket model for fetching use cases
try:
    from app.models.data_packet import DataPacket
except Exception:
    DataPacket = None  # type: ignore


class VoiceAgent:
    """
    ElevenLabs voice agent architecture:

    - Twilio handles the phone call (PSTN + callbacks).
    - Twilio requests TwiML from our webhook (/api/calls/{call_id}/webhook).
    - Our webhook calls ElevenLabs register-call and returns the TwiML (XML) back to Twilio.
    - ElevenLabs handles the full live voice loop (STT + agent reasoning + TTS).
    - After the call, ElevenLabs sends a post-call webhook with transcript/analysis which we store.

    This class now only:
      1) starts outbound calls via Twilio
      2) builds TwiML for Twilio webhook by calling ElevenLabs register-call
    """

    def __init__(self, db: Session):
        self.db = db
        self.twilio = TwilioService()
        self.eleven = ElevenLabsService()
        self._agent_config = None  # Lazy loaded to avoid circular import

    @property
    def agent_config(self):
        """Lazy load agent config to avoid circular imports."""
        if self._agent_config is None:
            from app.services.elevenlabs_agent_config import ElevenLabsAgentConfig
            self._agent_config = ElevenLabsAgentConfig()
        return self._agent_config

    # -----------------------------
    # Outbound call initiation
    # -----------------------------
    async def initiate_outbound_call(self, lead: Lead, call: Call) -> str:
        """
        Creates an outbound call. Uses ElevenLabs outbound-call API if phone_number_id
        is configured (enables real-time transcript streaming), otherwise falls back
        to Twilio with ElevenLabs register-call.

        Now includes: Pre-call agent configuration with sales control plane prompt
        """
        if not lead.phone and not call.phone_number:
            raise ValueError("Lead has no phone number")

        if not call.phone_number:
            call.phone_number = lead.phone

        if not call.started_at:
            call.started_at = datetime.utcnow()

        # Mark as queued until status callbacks update it
        call.status = call.status or "queued"
        self.db.commit()
        self.db.refresh(call)

        # ✅ Configure agent with sales control plane before call
        await self._configure_agent_for_lead(lead)

        # Build dynamic variables for ElevenLabs agent
        dyn = self._build_dynamic_variables(lead, call)
        conversation_initiation_client_data = {"dynamic_variables": dyn}

        # Check if we can use ElevenLabs outbound-call API (enables real-time streaming)
        if self.eleven.can_use_outbound_api():
            logger.info(f"Using ElevenLabs outbound-call API for call_id={call.id}")

            success, conversation_id, call_sid = await self.eleven.make_outbound_call(
                to_number=call.phone_number,
                conversation_initiation_client_data=conversation_initiation_client_data,
            )

            if success and conversation_id:
                call.twilio_call_sid = call_sid
                call.elevenlabs_conversation_id = conversation_id
                call.status = "in-progress"
                self.db.commit()

                logger.info(f"ElevenLabs outbound call started call_id={call.id}, conversation_id={conversation_id}")

                # Start real-time transcript monitoring
                await self._start_realtime_monitor(call.id, lead.id, conversation_id)

                return call_sid or conversation_id
            else:
                logger.warning(f"ElevenLabs outbound-call failed for call_id={call.id}, falling back to Twilio")

        # Fallback: Twilio makes the call, fetches TwiML from our webhook
        logger.info(f"Using Twilio with ElevenLabs register-call for call_id={call.id}")
        twilio_call = await self.twilio.make_call(
            to_number=call.phone_number,
            callback_url=f"/api/calls/{call.id}/webhook",
        )

        call.twilio_call_sid = getattr(twilio_call, "sid", None)
        call.status = getattr(twilio_call, "status", None) or "queued"
        self.db.commit()

        logger.info(f"Twilio outbound call started call_id={call.id} sid={call.twilio_call_sid}")
        return call.twilio_call_sid

    async def _start_realtime_monitor(self, call_id: int, lead_id: int, conversation_id: str) -> None:
        """Start real-time transcript monitoring and forward events to frontend."""
        async def on_transcript(event: Dict[str, Any]) -> None:
            # Forward real-time transcript events to frontend via WebSocket
            await broadcast_activity(event)

        try:
            await start_realtime_monitor(
                conversation_id=conversation_id,
                call_id=call_id,
                lead_id=lead_id,
                on_transcript=on_transcript,
            )
            logger.info(f"Real-time monitor started for call_id={call_id}, conversation_id={conversation_id}")
        except Exception as e:
            logger.error(f"Failed to start real-time monitor for call_id={call_id}: {e}")

    async def _configure_agent_for_lead(self, lead: Lead) -> None:
        """
        Configure the ElevenLabs agent with sales control plane prompt
        and optimized voice settings before initiating a call.
        """
        try:
            # Fetch data packet for use cases if available
            data_packet_dict = None
            if DataPacket is not None:
                packet = self.db.query(DataPacket).filter(DataPacket.lead_id == lead.id).first()
                if packet:
                    data_packet_dict = {
                        "company_analysis": packet.company_analysis,
                        "use_case_1_title": packet.use_case_1_title,
                        "use_case_1_description": packet.use_case_1_description,
                        "use_case_1_impact": packet.use_case_1_impact,
                        "use_case_2_title": packet.use_case_2_title,
                        "use_case_2_description": packet.use_case_2_description,
                        "use_case_2_impact": packet.use_case_2_impact,
                        "use_case_3_title": packet.use_case_3_title,
                        "use_case_3_description": packet.use_case_3_description,
                        "use_case_3_impact": packet.use_case_3_impact,
                    }

            # Configure agent with comprehensive sales prompt and voice settings
            success = await self.agent_config.configure_for_call(
                lead_name=(lead.name or "").strip(),
                lead_company=(lead.company or "").strip(),
                lead_title=(lead.title or "").strip(),
                lead_industry=(getattr(lead, "company_industry", "") or "").strip(),
                data_packet=data_packet_dict,
            )

            if success:
                logger.info(f"Agent configured with sales control plane for lead_id={lead.id}")
                await broadcast_activity({
                    "type": "agent_configured",
                    "lead_id": lead.id,
                    "message": "Sales agent configured with optimized prompt and voice settings",
                })
            else:
                logger.warning(f"Agent configuration partially failed for lead_id={lead.id}")

        except Exception as e:
            logger.error(f"Failed to configure agent for lead_id={lead.id}: {e}")
            # Continue with call even if configuration fails - agent will use default prompt

    # -----------------------------
    # TwiML builder (ElevenLabs register-call)
    # -----------------------------
    def _build_dynamic_variables(self, lead: Lead, call: Call) -> Dict[str, Any]:
        """
        These are passed to ElevenLabs agent and can be used in prompt/logic.
        We ALWAYS include call_id so webhook correlation is easy.
        """
        return {
            "call_id": str(call.id),
            "lead_id": str(call.lead_id),
            "lead_name": (lead.name or "").strip(),
            "lead_title": (lead.title or "").strip(),
            "lead_company": (lead.company or "").strip(),
            "lead_industry": (getattr(lead, "company_industry", "") or "").strip(),
            "lead_email": (getattr(lead, "email", "") or "").strip(),
            "lead_phone": (lead.phone or call.phone_number or "").strip(),
        }

    async def build_twiml_for_twilio_webhook(
        self,
        *,
        call_id: int,
        from_number: str,
        to_number: str,
        direction: str = "outbound",
    ) -> str:
        """
        Called by calls.py /twilio_webhook.
        Returns TwiML XML string to Twilio, generated by ElevenLabs register-call.
        """
        call = self.db.query(Call).filter(Call.id == call_id).first()
        if not call:
            raise ValueError(f"Call not found call_id={call_id}")

        lead = self.db.query(Lead).filter(Lead.id == call.lead_id).first()
        if not lead:
            raise ValueError(f"Lead not found lead_id={call.lead_id}")

        dyn = self._build_dynamic_variables(lead, call)

        # Optional: include anything else you want the agent to know:
        # - call status, campaign info, custom attributes, etc.
        conversation_initiation_client_data = {"dynamic_variables": dyn}

        twiml = await self.eleven.register_call_twiml(
            from_number=from_number,
            to_number=to_number,
            direction=direction,
            conversation_initiation_client_data=conversation_initiation_client_data,
        )
        return twiml

    # -----------------------------
    # Backward-compat (optional stubs)
    # -----------------------------
    # Your old calls.py referenced these methods. Once you patch calls.py below,
    # they won’t be used, but stubs avoid accidental import errors elsewhere.

    def _build_opener(self, lead: Optional[Lead]) -> str:
        name = (getattr(lead, "name", "") or "").strip() or "there"
        return f"Hi {name} — this is AADOS calling from Algonox."

    async def tts_audio_url(self, call_id: int, text: str) -> Optional[str]:
        return None

    def build_initial_twiml(self, call_id: int, opener_text: str, opener_audio_url: Optional[str]) -> str:
        return "<Response></Response>"

    def build_turn_twiml(self, call_id: int, agent_text: str, agent_audio_url: Optional[str]) -> str:
        return "<Response></Response>"

    async def generate_reply(self, call: Call, user_input: str) -> str:
        # In ElevenLabs architecture, replies are generated inside ElevenLabs.
        return ""
