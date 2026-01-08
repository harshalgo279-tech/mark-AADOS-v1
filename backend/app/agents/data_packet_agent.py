# backend/app/agents/data_packet_agent.py
import asyncio
# backend/app/agents/data_packet_agent.py
import asyncio
import json
import logging
import re
from typing import Any, Dict

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.models.data_packet import DataPacket
from app.models.lead import Lead

logger = logging.getLogger(__name__)

try:
    # openai>=1.x
    from openai import OpenAI
except Exception:
    OpenAI = None  # type: ignore


def _safe_str(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    return str(v)


def _safe_json_dumps(v: Any) -> str:
    try:
        return json.dumps(v if v is not None else [], ensure_ascii=False)
    except Exception:
        return "[]"


def _extract_json_object(text: str) -> Dict[str, Any] | None:
    """
    Many LLMs occasionally wrap JSON in prose. Try to extract first {...} block.
    """
    if not text:
        return None
    text = text.strip()

    # If it's already valid JSON:
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass

    # Try to find a JSON object inside text
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None

    candidate = m.group(0)
    try:
        obj = json.loads(candidate)
        if isinstance(obj, dict):
            return obj
    except Exception:
        return None

    return None


class DataPacketAgent:
    """
    Generates and stores DataPacket rows for a lead.
    IMPORTANT: Store only strings/JSON-strings to avoid MySQL driver errors.
    """

    def __init__(self, db: Session):
        self.db = db

        self._client = None
        if getattr(settings, "OPENAI_API_KEY", None) and OpenAI is not None:
            self._client = OpenAI(api_key=settings.OPENAI_API_KEY)

        # Optional model override via OPENAI_MODEL
        self._model = getattr(settings, "OPENAI_MODEL", None) or "gpt-4o-mini"

    async def create_data_packet(self, lead: Lead) -> DataPacket:
        """
        Idempotent + concurrency-safe:
        - If exists: return it
        - If insert hits duplicate lead_id: rollback + return existing
        """
        existing = (
            self.db.query(DataPacket)
            .filter(DataPacket.lead_id == lead.id)
            .first()
        )
        if existing:
            return existing

        content = await self._generate_packet_content(lead)

        packet = DataPacket(
            lead_id=lead.id,
            company_analysis=_safe_str(content.get("company_analysis")),
            pain_points=_safe_json_dumps(content.get("pain_points", [])),
            use_case_1_title=_safe_str(content.get("use_case_1_title")),
            use_case_1_description=_safe_str(content.get("use_case_1_description")),
            use_case_1_impact=_safe_str(content.get("use_case_1_impact")),
            use_case_2_title=_safe_str(content.get("use_case_2_title")),
            use_case_2_description=_safe_str(content.get("use_case_2_description")),
            use_case_2_impact=_safe_str(content.get("use_case_2_impact")),
            use_case_3_title=_safe_str(content.get("use_case_3_title")),
            use_case_3_description=_safe_str(content.get("use_case_3_description")),
            use_case_3_impact=_safe_str(content.get("use_case_3_impact")),
            solution_1_title=_safe_str(content.get("solution_1_title")),
            solution_1_description=_safe_str(content.get("solution_1_description")),
            solution_1_roi=_safe_str(content.get("solution_1_roi")),
            solution_2_title=_safe_str(content.get("solution_2_title")),
            solution_2_description=_safe_str(content.get("solution_2_description")),
            solution_2_roi=_safe_str(content.get("solution_2_roi")),
            solution_3_title=_safe_str(content.get("solution_3_title")),
            solution_3_description=_safe_str(content.get("solution_3_description")),
            solution_3_roi=_safe_str(content.get("solution_3_roi")),
            confidence_score=float(content.get("confidence_score") or 0.7),
        )

        self.db.add(packet)

        try:
            self.db.commit()
            self.db.refresh(packet)
            return packet

        except IntegrityError:
            # Duplicate lead_id (someone else created it first) -> rollback and return existing
            self.db.rollback()
            existing = (
                self.db.query(DataPacket)
                .filter(DataPacket.lead_id == lead.id)
                .first()
            )
            if existing:
                return existing
            raise

        except Exception:
            self.db.rollback()
            raise

    async def _generate_packet_content(self, lead: Lead) -> Dict[str, Any]:
        # If OpenAI not configured, fallback
        if not self._client:
            return self._fallback_packet(lead)

        prompt = self._build_prompt(lead)

        try:
            resp = await asyncio.to_thread(
                self._client.chat.completions.create,
                model=self._model,
                temperature=0.4,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You generate outbound sales enablement 'data packets'. "
                            "Return STRICT JSON only (no markdown, no prose)."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
            )

            text = (resp.choices[0].message.content or "").strip()
            data = _extract_json_object(text)

            if not data:
                logger.warning("LLM returned non-JSON; using fallback. Raw=%r", text[:2000])
                return self._fallback_packet(lead)

            return self._normalize_packet_dict(data, lead)

        except Exception as e:
            logger.exception("Packet generation failed (LLM). Falling back. Error=%s", e)
            return self._fallback_packet(lead)

    def _build_prompt(self, lead: Lead) -> str:
        company = lead.company or "Unknown Company"
        industry = getattr(lead, "company_industry", None) or ""
        size = getattr(lead, "company_size", None) or ""
        location = getattr(lead, "company_location", None) or ""
        website = getattr(lead, "company_website", None) or ""
        title = lead.title or ""
        name = lead.name or ""

        return (
            "Create a sales data packet JSON for the following lead.\n\n"
            f"Lead name: {name}\n"
            f"Lead title: {title}\n"
            f"Company: {company}\n"
            f"Industry: {industry}\n"
            f"Company size: {size}\n"
            f"Location: {location}\n"
            f"Website: {website}\n\n"
            "Output JSON schema (all fields required):\n"
            "{\n"
            '  "company_analysis": string,\n'
            '  "pain_points": [string, string, string],\n'
            '  "use_case_1_title": string,\n'
            '  "use_case_1_description": string,\n'
            '  "use_case_1_impact": string,\n'
            '  "use_case_2_title": string,\n'
            '  "use_case_2_description": string,\n'
            '  "use_case_2_impact": string,\n'
            '  "use_case_3_title": string,\n'
            '  "use_case_3_description": string,\n'
            '  "use_case_3_impact": string,\n'
            '  "solution_1_title": string,\n'
            '  "solution_1_description": string,\n'
            '  "solution_1_roi": string,\n'
            '  "solution_2_title": string,\n'
            '  "solution_2_description": string,\n'
            '  "solution_2_roi": string,\n'
            '  "solution_3_title": string,\n'
            '  "solution_3_description": string,\n'
            '  "solution_3_roi": string,\n'
            '  "confidence_score": number\n'
            "}\n"
        )

    def _normalize_packet_dict(self, data: Dict[str, Any], lead: Lead) -> Dict[str, Any]:
        fallback = self._fallback_packet(lead)

        pain_points = data.get("pain_points", fallback["pain_points"])
        if not isinstance(pain_points, list):
            pain_points = fallback["pain_points"]
        pain_points = [str(x) for x in pain_points][:3] if pain_points else fallback["pain_points"]

        normalized = {**fallback, **data}
        normalized["pain_points"] = pain_points

        try:
            normalized["confidence_score"] = float(normalized.get("confidence_score") or 0.7)
        except Exception:
            normalized["confidence_score"] = 0.7

        return normalized

    def _fallback_packet(self, lead: Lead) -> Dict[str, Any]:
        company = lead.company or "the company"
        industry = getattr(lead, "company_industry", None) or "their industry"
        title = lead.title or "the team"

        return {
            "company_analysis": (
                f"{company} operates in {industry}. A likely priority is improving pipeline quality, "
                "reducing manual outbound effort, and increasing conversion from outreach to meetings."
            ),
            "pain_points": [
                "Low reply rates / poor targeting leading to wasted outreach volume",
                "Manual personalization is slow and inconsistent across reps",
                "Limited visibility into what messaging and channels are working",
            ],
            "use_case_1_title": "AI-personalized outbound sequences",
            "use_case_1_description": f"Generate targeted messaging for {title} personas using company context.",
            "use_case_1_impact": "Higher reply rates and faster iteration on what works.",
            "use_case_2_title": "Lead scoring and prioritization",
            "use_case_2_description": "Rank leads based on fit and intent signals for focused calling.",
            "use_case_2_impact": "More meetings booked with fewer calls.",
            "use_case_3_title": "Conversation insights and follow-up automation",
            "use_case_3_description": "Summarize calls, extract objections, and draft follow-up emails automatically.",
            "use_case_3_impact": "Improved follow-up consistency and faster pipeline movement.",
            "solution_1_title": "Outbound copilot",
            "solution_1_description": "AI generates outreach and talk tracks aligned to personas and pain points.",
            "solution_1_roi": "Reduce rep prep time and increase conversion.",
            "solution_2_title": "Sales ops dashboard",
            "solution_2_description": "Track funnel, activity, and outcomes across channels in one view.",
            "solution_2_roi": "Better decisions and faster optimization.",
            "solution_3_title": "Auto-generated call notes + next steps",
            "solution_3_description": "Structured summaries and recommended next actions after each call.",
            "solution_3_roi": "Less admin work and fewer dropped follow-ups.",
            "confidence_score": 0.7,
        }
