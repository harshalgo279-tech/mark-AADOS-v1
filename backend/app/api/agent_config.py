# backend/app/api/agent_config.py
"""
API endpoints for configuring and testing the sales agent
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from app.services.elevenlabs_agent_config import ElevenLabsAgentConfig, VOICE_PRESETS
from app.agents.sales_control_plane import generate_elevenlabs_agent_prompt
from app.utils.logger import logger

router = APIRouter(prefix="/api/agent-config", tags=["agent-config"])


class UpdatePromptRequest(BaseModel):
    lead_name: Optional[str] = ""
    lead_company: Optional[str] = ""
    lead_title: Optional[str] = ""
    lead_industry: Optional[str] = ""
    company_analysis: Optional[str] = ""
    use_cases: Optional[List[Dict[str, str]]] = None


class UpdateVoiceRequest(BaseModel):
    preset: Optional[str] = "professional_clear"
    stability: Optional[float] = None
    similarity_boost: Optional[float] = None
    style: Optional[float] = None
    use_speaker_boost: Optional[bool] = True


@router.get("/current")
async def get_current_config():
    """Get current agent configuration from ElevenLabs."""
    try:
        config_service = ElevenLabsAgentConfig()
        config = await config_service.get_agent_config()
        await config_service.aclose()
        return {"success": True, "config": config}
    except Exception as e:
        logger.error(f"Failed to get agent config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/update-prompt")
async def update_agent_prompt(request: UpdatePromptRequest):
    """Update the agent prompt with sales control plane."""
    try:
        config_service = ElevenLabsAgentConfig()

        prompt = generate_elevenlabs_agent_prompt(
            lead_name=request.lead_name or "",
            lead_company=request.lead_company or "",
            lead_title=request.lead_title or "",
            lead_industry=request.lead_industry or "",
            use_cases=request.use_cases or [],
            company_analysis=request.company_analysis or "",
        )

        first_message = f"Hi{' ' + request.lead_name if request.lead_name else ''}, this is AADOS calling from Algonox. Did I catch you at a bad time?"

        success = await config_service.update_agent_prompt(
            prompt=prompt,
            first_message=first_message,
        )

        await config_service.aclose()

        return {
            "success": success,
            "message": "Agent prompt updated with sales control plane" if success else "Failed to update prompt",
            "prompt_length": len(prompt),
        }
    except Exception as e:
        logger.error(f"Failed to update prompt: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/update-voice")
async def update_voice_settings(request: UpdateVoiceRequest):
    """Update voice settings for better clarity and volume."""
    try:
        config_service = ElevenLabsAgentConfig()

        # Use preset or custom values
        if request.preset and request.preset in VOICE_PRESETS:
            preset = VOICE_PRESETS[request.preset]
            stability = request.stability or preset["stability"]
            similarity_boost = request.similarity_boost or preset["similarity_boost"]
            style = request.style or preset["style"]
            use_speaker_boost = request.use_speaker_boost if request.use_speaker_boost is not None else preset["use_speaker_boost"]
        else:
            stability = request.stability or 0.75
            similarity_boost = request.similarity_boost or 0.80
            style = request.style or 0.35
            use_speaker_boost = request.use_speaker_boost if request.use_speaker_boost is not None else True

        success = await config_service.update_voice_settings(
            stability=stability,
            similarity_boost=similarity_boost,
            style=style,
            use_speaker_boost=use_speaker_boost,
        )

        await config_service.aclose()

        return {
            "success": success,
            "message": "Voice settings updated" if success else "Failed to update voice",
            "settings": {
                "stability": stability,
                "similarity_boost": similarity_boost,
                "style": style,
                "use_speaker_boost": use_speaker_boost,
            }
        }
    except Exception as e:
        logger.error(f"Failed to update voice: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/voice-presets")
async def list_voice_presets():
    """List available voice presets."""
    return {"presets": VOICE_PRESETS}


@router.post("/full-update")
async def full_agent_update(request: UpdatePromptRequest):
    """Update both prompt and voice settings."""
    try:
        config_service = ElevenLabsAgentConfig()

        results = await config_service.update_full_agent_config(
            lead_name=request.lead_name or "",
            lead_company=request.lead_company or "",
            lead_title=request.lead_title or "",
            lead_industry=request.lead_industry or "",
            use_cases=request.use_cases or [],
            company_analysis=request.company_analysis or "",
        )

        await config_service.aclose()

        return {
            "success": results["prompt_updated"] and results["voice_updated"],
            "prompt_updated": results["prompt_updated"],
            "voice_updated": results["voice_updated"],
            "message": "Agent fully updated with sales control plane and optimized voice",
        }
    except Exception as e:
        logger.error(f"Failed to fully update agent: {e}")
        raise HTTPException(status_code=500, detail=str(e))
