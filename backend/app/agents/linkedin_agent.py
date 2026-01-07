# backend/app/agents/linkedin_agent.py
from __future__ import annotations

from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from datetime import datetime
import json

from app.models.lead import Lead
from app.models.data_packet import DataPacket
from app.models.call import Call
from app.models.linkedin import LinkedInMessage
from app.services.openai_service import OpenAIService
from app.utils.logger import logger


class LinkedInAgent:
    """
    Generates LinkedIn message sequences tailored to:
    - Lead profile
    - Data packet use cases
    - What actually happened in the call (summary + transcript)
    """

    def __init__(self, db: Session):
        self.db = db
        self.openai = OpenAIService()

    # ✅ Keep BOTH names so older/newer endpoints won't break
    async def generate_linkedin_scripts(
        self,
        lead: Lead,
        data_packet: DataPacket,
        call: Optional[Call] = None,
    ) -> LinkedInMessage:
        return await self._generate_and_store(lead=lead, data_packet=data_packet, call=call)

    async def generate_linkedin_messages(
        self,
        lead: Lead,
        data_packet: DataPacket,
        call: Optional[Call] = None,
    ) -> LinkedInMessage:
        # alias
        return await self._generate_and_store(lead=lead, data_packet=data_packet, call=call)

    async def _generate_and_store(
        self,
        lead: Lead,
        data_packet: DataPacket,
        call: Optional[Call] = None,
    ) -> LinkedInMessage:
        try:
            logger.info(f"Generating LinkedIn scripts for {lead.name} at {lead.company}")

            scripts = await self._generate_with_llm(lead, data_packet, call)

            linkedin_msg = LinkedInMessage(
                lead_id=lead.id,
                use_case_1_message=scripts.get("use_case_1_message"),
                use_case_2_message=scripts.get("use_case_2_message"),
                use_case_3_message=scripts.get("use_case_3_message"),
                connection_request=scripts.get("connection_request"),
                follow_up_1=scripts.get("follow_up_1"),
                follow_up_2=scripts.get("follow_up_2"),
                generated_at=datetime.utcnow(),
            )

            self.db.add(linkedin_msg)
            self.db.commit()
            self.db.refresh(linkedin_msg)

            logger.info(f"LinkedIn scripts generated for {lead.company}")
            return linkedin_msg

        except Exception as e:
            logger.error(f"Error generating LinkedIn scripts: {str(e)}")
            raise

    async def _generate_with_llm(
        self,
        lead: Lead,
        data_packet: DataPacket,
        call: Optional[Call],
    ) -> Dict[str, Any]:
        call_summary = (getattr(call, "transcript_summary", None) or "").strip()
        transcript_tail = ((getattr(call, "full_transcript", None) or "").strip())[-2500:]

        prompt = f"""
You are a LinkedIn messaging expert for B2B sales.

Generate personalized LinkedIn messages based on:
1) the lead profile,
2) the 3 use cases,
3) what happened in the phone call.

LEAD INFORMATION:
- Name: {lead.name}
- Title: {lead.title}
- Company: {lead.company}
- Industry: {getattr(lead, "company_industry", "")}
- LinkedIn: {getattr(lead, "linkedin_url", "")}

CALL CONTEXT:
- Call summary (if available):
{call_summary or "[Not available yet]"}

- Transcript tail (latest part, may include objections):
{transcript_tail or "[No transcript]"}

USE CASES TO PITCH:
1) {data_packet.use_case_1_title}
   {data_packet.use_case_1_description}

2) {data_packet.use_case_2_title}
   {data_packet.use_case_2_description}

3) {data_packet.use_case_3_title}
   {data_packet.use_case_3_description}

TASK:
Write these LinkedIn messages:

1) CONNECTION REQUEST (<= 300 characters)
2) USE CASE 1 MESSAGE (<= 1000 characters)
3) USE CASE 2 MESSAGE (<= 1000 characters)
4) USE CASE 3 MESSAGE (<= 1000 characters)
5) FOLLOW-UP 1 (<= 500 characters)
6) FOLLOW-UP 2 (<= 500 characters)

STYLE RULES:
- Natural, not salesy
- Mirror the call outcome: if they were hesitant, be softer; if interested, be more direct
- Mention value/impact but avoid exaggerated claims
- End each message with ONE simple question

Return valid JSON only with keys:
connection_request, use_case_1_message, use_case_2_message, use_case_3_message, follow_up_1, follow_up_2
"""

        response = await self.openai.generate_completion(
            prompt=prompt,
            temperature=0.7,
            max_tokens=1800,
        )

        try:
            return json.loads(response)
        except json.JSONDecodeError:
            logger.error("Failed to parse LinkedIn scripts JSON. Using fallback.")
            return self._generate_fallback_scripts(lead, data_packet)

    def _generate_fallback_scripts(self, lead: Lead, data_packet: DataPacket) -> Dict[str, Any]:
        first_name = (lead.name or "there").split()[0]
        company = lead.company or "your company"
        industry = getattr(lead, "company_industry", "") or "your industry"

        return {
            "connection_request": f"Hi {first_name} — I work with teams in {industry} on practical AI automation. Would love to connect and share a quick idea relevant to {company}.",
            "use_case_1_message": f"Thanks for connecting, {first_name}. One area we often improve is {data_packet.use_case_1_title}. Would it be useful to compare notes on how {company} handles this today?",
            "use_case_2_message": f"{first_name}, another complementary area is {data_packet.use_case_2_title}. If you’re exploring efficiency improvements, open to a quick 10–15 min chat?",
            "use_case_3_message": f"Last idea: {data_packet.use_case_3_title}. If you’re prioritizing outcomes this quarter, would it be worth a brief walkthrough?",
            "follow_up_1": f"Hi {first_name} — quick follow-up. If I share a 1-page example of how teams reduce manual work using automation, would that help?",
            "follow_up_2": f"{first_name}, I’ll keep this short — should I close the loop, or is there someone else at {company} who owns automation/process improvements?",
        }
