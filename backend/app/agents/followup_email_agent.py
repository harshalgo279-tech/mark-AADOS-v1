# backend/app/agents/followup_email_agent.py
"""
Follow-up Email Agent

Handles automated email triggers based on call outcomes:

1. DEMO_CONFIRMED: Call concludes with demo confirmation (positive response)
   - Includes demo scheduling link
   - Comprehensive Algonox description
   - What to expect from demo

2. CALL_COMPLETED_NO_DEMO: Call completed but no demo confirmation
   - Relevant use case specific to lead's business
   - How Algonox addresses the use case
   - Soft call-to-action

3. UNANSWERED: Call not answered/picked up
   - Who we are (Algonox intro)
   - What we do (services/solutions)
   - Why we reached out (personalized reason)
   - Use cases (multiple relevant examples)
   - CTA to reply for scheduling

Uses scraped company data and lead position for personalization.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from enum import Enum

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.config import settings
from app.models.call import Call
from app.models.data_packet import DataPacket
from app.models.email import Email
from app.models.lead import Lead
from app.services.email_service import EmailService, generate_tracking_id
from app.services.openai_service import OpenAIService
from app.utils.logger import logger

# Duplicate prevention: minimum hours between same email types to same lead
DUPLICATE_COOLDOWN_HOURS = 24


class CallOutcome(Enum):
    """Possible call outcomes for follow-up email selection"""
    DEMO_CONFIRMED = "demo_confirmed"
    CALL_COMPLETED_NO_DEMO = "call_completed_no_demo"
    UNANSWERED = "unanswered"
    UNKNOWN = "unknown"


class FollowUpEmailAgent:
    """
    Generates and sends follow-up emails based on call outcomes.

    Implements Requirements:
    - 4.x: Demo Confirmation Follow-up
    - 5.x: Call Completed - No Demo Follow-up
    - 6.x: No Response/Unanswered Call Follow-up
    """

    def __init__(self, db: Session):
        self.db = db
        self.openai = OpenAIService()
        self.email_service = EmailService()

        # Configuration
        self.demo_link = getattr(settings, "DEMO_SCHEDULING_LINK", "https://calendly.com/algonox/demo")
        self.company_name = getattr(settings, "ALGONOX_COMPANY_NAME", "Algonox")
        self.company_description = getattr(settings, "ALGONOX_COMPANY_DESCRIPTION", "")

        # Sender info for email signatures
        self.sender_name = getattr(settings, "EMAIL_SENDER_NAME", "Harsha")
        self.sender_title = getattr(settings, "EMAIL_SENDER_TITLE", "Business Development")
        self.reply_to = getattr(settings, "EMAIL_REPLY_TO", "")

    def _check_lead_can_receive_email(self, lead: Lead) -> tuple[bool, Optional[str]]:
        """
        Check if lead can receive emails (not unsubscribed, has valid email).

        Returns:
            (can_send, reason_if_blocked)
        """
        # Check unsubscribed
        if lead.unsubscribed_at:
            return False, "Lead has unsubscribed from emails"

        # Check email validity (marked invalid from bounces)
        if hasattr(lead, "email_valid") and lead.email_valid is False:
            return False, "Lead email marked as invalid (bounced)"

        # Check has email
        if not (getattr(lead, "email", "") or "").strip():
            return False, "Lead has no email address"

        return True, None

    def _check_duplicate_email(
        self,
        lead_id: int,
        email_type: str,
        cooldown_hours: int = DUPLICATE_COOLDOWN_HOURS,
    ) -> bool:
        """
        Check if a similar email was recently sent to this lead.

        Returns:
            True if duplicate exists (should skip), False if OK to send
        """
        cutoff = datetime.utcnow() - timedelta(hours=cooldown_hours)

        existing = self.db.query(Email).filter(
            Email.lead_id == lead_id,
            Email.email_type == email_type,
            Email.created_at >= cutoff,
            Email.status.in_(["sent", "draft", "pending", "scheduled"]),
        ).first()

        if existing:
            logger.info(
                f"Skipping duplicate email: lead_id={lead_id}, type={email_type}, "
                f"existing_id={existing.id}, created={existing.created_at}"
            )
            return True

        return False

    def determine_call_outcome(self, call: Call) -> CallOutcome:
        """
        Analyze call status/transcript to determine outcome type.

        Returns:
            CallOutcome enum indicating the type of follow-up needed
        """
        status = (call.status or "").lower().strip()

        # Check for unanswered calls
        unanswered_statuses = ["no-answer", "busy", "failed", "canceled", "no_answer", "unanswered"]
        if status in unanswered_statuses:
            return CallOutcome.UNANSWERED

        # Check for demo requested
        if call.demo_requested:
            return CallOutcome.DEMO_CONFIRMED

        # Check transcript/sentiment for demo indicators
        if call.full_transcript:
            transcript_lower = call.full_transcript.lower()

            # Strong demo confirmation indicators
            demo_phrases = [
                "book a demo", "schedule a demo", "set up a demo",
                "i'd like a demo", "show me", "let's schedule",
                "sounds interesting", "let's do it", "yes, let's talk",
                "book that", "schedule that"
            ]

            if any(phrase in transcript_lower for phrase in demo_phrases):
                if call.sentiment in ["positive", "interested"]:
                    return CallOutcome.DEMO_CONFIRMED

        # If call completed but no demo confirmation
        if status == "completed" and call.full_transcript:
            return CallOutcome.CALL_COMPLETED_NO_DEMO

        return CallOutcome.UNKNOWN

    async def generate_and_send_followup(
        self,
        call: Call,
        outcome: Optional[CallOutcome] = None,
        send_immediately: bool = True,
        skip_duplicate_check: bool = False,
    ) -> Dict[str, Any]:
        """
        Generate and optionally send follow-up email based on call outcome.

        Args:
            call: The Call object
            outcome: Optional pre-determined outcome (auto-detected if None)
            send_immediately: Whether to send the email right away
            skip_duplicate_check: Skip duplicate email prevention (for manual resend)

        Returns:
            Dict with status, email_id, and any errors
        """
        # Get lead
        lead = self.db.query(Lead).filter(Lead.id == call.lead_id).first()
        if not lead:
            return {"success": False, "error": "Lead not found"}

        # Check if lead can receive emails (unsubscribed, valid email, etc.)
        can_send, block_reason = self._check_lead_can_receive_email(lead)
        if not can_send:
            logger.info(f"Skipping email to lead {lead.id}: {block_reason}")
            return {"success": False, "error": block_reason, "blocked": True}

        # Determine outcome if not provided
        if outcome is None:
            outcome = self.determine_call_outcome(call)

        if outcome == CallOutcome.UNKNOWN:
            return {"success": False, "error": "Could not determine call outcome"}

        # Check for duplicate emails (same type to same lead recently)
        if not skip_duplicate_check:
            if self._check_duplicate_email(lead.id, outcome.value):
                return {
                    "success": False,
                    "error": f"Duplicate email prevented: {outcome.value} already sent to lead within {DUPLICATE_COOLDOWN_HOURS}h",
                    "duplicate": True,
                }

        # Get data packet for use cases
        data_packet = self.db.query(DataPacket).filter(DataPacket.lead_id == lead.id).first()

        # Generate email content based on outcome
        if outcome == CallOutcome.DEMO_CONFIRMED:
            email_content = await self._generate_demo_confirmation_email(lead, call, data_packet)
        elif outcome == CallOutcome.CALL_COMPLETED_NO_DEMO:
            email_content = await self._generate_no_demo_followup_email(lead, call, data_packet)
        elif outcome == CallOutcome.UNANSWERED:
            email_content = await self._generate_unanswered_intro_email(lead, call, data_packet)
        else:
            return {"success": False, "error": f"Unhandled outcome: {outcome}"}

        # Generate tracking ID for this email
        tracking_id = generate_tracking_id()

        # Store email in database
        email = Email(
            lead_id=lead.id,
            call_id=call.id,
            subject=email_content["subject"],
            body_html=email_content["body_html"],
            body_text=email_content.get("body_text", ""),
            preview_text=email_content.get("preview_text", ""),
            email_type=outcome.value,
            tracking_id=tracking_id,
            status="draft",
            created_at=datetime.utcnow(),
        )

        self.db.add(email)
        self.db.commit()
        self.db.refresh(email)

        result = {
            "success": True,
            "email_id": email.id,
            "tracking_id": tracking_id,
            "outcome": outcome.value,
            "sent": False,
        }

        # Send if requested
        if send_immediately:
            send_result = await self._send_email(email, lead)
            result["sent"] = send_result["success"]
            result["send_error"] = send_result.get("error")

        return result

    async def _generate_demo_confirmation_email(
        self,
        lead: Lead,
        call: Call,
        data_packet: Optional[DataPacket],
    ) -> Dict[str, str]:
        """
        Generate demo confirmation email (Requirement 4.x)

        Includes:
        - Demo scheduling link
        - Comprehensive Algonox description
        - What to expect from demo
        """
        first_name = (lead.name or "there").split()[0]
        company = lead.company or "your company"

        # Build use cases from data packet
        use_cases = self._format_use_cases(data_packet)

        # Get scraped company data for additional context
        scraped_overview = getattr(lead, "scraped_company_overview", "") or ""
        scraped_services = getattr(lead, "scraped_services", []) or []

        prompt = f"""You are writing a demo confirmation follow-up email for Algonox.

LEAD INFORMATION:
- Name: {lead.name}
- First Name: {first_name}
- Title: {lead.title}
- Company: {company}
- Industry: {getattr(lead, 'company_industry', '') or getattr(lead, 'scraped_industry', '')}

COMPANY RESEARCH:
{scraped_overview[:500] if scraped_overview else "[No scraped data available]"}

Their services: {json.dumps(scraped_services[:5]) if scraped_services else "[Unknown]"}

CALL SUMMARY:
{(call.transcript_summary or '')[:400]}

USE CASES RELEVANT TO THEM:
{use_cases}

ALGONOX DESCRIPTION (include this):
{self.company_description}

DEMO SCHEDULING LINK: {self.demo_link}

SENDER INFO (for signature):
- Name: {self.sender_name}
- Title: {self.sender_title}
- Company: {self.company_name}

REQUIREMENTS:
1. Thank them for their time and interest
2. Confirm the next step is a demo
3. Include the demo scheduling link prominently
4. Provide a comprehensive paragraph about Algonox (who we are, what we do, value prop)
5. Briefly mention what they can expect from the demo
6. Keep tone professional and enthusiastic
7. End with proper signature using sender name above (e.g., "Best regards,\\n{self.sender_name}\\n{self.sender_title}, {self.company_name}")
8. Length: 250-350 words

Return JSON only:
{{
    "subject": "Demo confirmed - [personalized subject]",
    "body_html": "<html content with paragraphs>",
    "body_text": "plain text version"
}}
"""

        return await self._generate_email_via_llm(prompt, lead, "Demo Confirmation")

    async def _generate_no_demo_followup_email(
        self,
        lead: Lead,
        call: Call,
        data_packet: Optional[DataPacket],
    ) -> Dict[str, str]:
        """
        Generate follow-up for completed call without demo (Requirement 5.x)

        Includes:
        - Relevant use case specific to lead's business
        - How Algonox addresses the use case
        - Connection to their services
        - Soft CTA
        """
        first_name = (lead.name or "there").split()[0]
        company = lead.company or "your company"

        # Get scraped company data
        scraped_overview = getattr(lead, "scraped_company_overview", "") or ""
        scraped_services = getattr(lead, "scraped_services", []) or []
        scraped_products = getattr(lead, "scraped_products", []) or []

        # Build use cases
        use_cases = self._format_use_cases(data_packet)

        # Analyze objections/sentiment from call
        objections = call.objections_raised or []
        sentiment = call.sentiment or "neutral"

        prompt = f"""You are writing a follow-up email after a sales call that did NOT result in a demo booking.

LEAD INFORMATION:
- Name: {lead.name}
- First Name: {first_name}
- Title: {lead.title}
- Company: {company}
- Industry: {getattr(lead, 'company_industry', '') or getattr(lead, 'scraped_industry', '')}

SCRAPED COMPANY DATA:
Overview: {scraped_overview[:600] if scraped_overview else "[Not available]"}
Services: {json.dumps(scraped_services[:5]) if scraped_services else "[Unknown]"}
Products: {json.dumps(scraped_products[:5]) if scraped_products else "[Unknown]"}

CALL ANALYSIS:
- Sentiment: {sentiment}
- Objections raised: {json.dumps(objections) if objections else "None"}
- Summary: {(call.transcript_summary or '')[:400]}

USE CASES WE CAN OFFER:
{use_cases}

SENDER INFO (for signature):
- Name: {self.sender_name}
- Title: {self.sender_title}
- Company: {self.company_name}

REQUIREMENTS:
1. Pick ONE use case most relevant to their business/industry
2. Explain how this use case directly addresses a challenge they likely face
3. Connect it to their services/products (show you understand their business)
4. Tone: consultative, value-focused, NOT pushy
5. End with a soft CTA (e.g., "Happy to share more details if helpful")
6. Address any objections subtly if relevant
7. End with proper signature using sender name above (e.g., "Best regards,\\n{self.sender_name}\\n{self.sender_title}, {self.company_name}")
8. Length: 180-250 words

Return JSON only:
{{
    "subject": "[Personalized value-focused subject]",
    "body_html": "<html content>",
    "body_text": "plain text"
}}
"""

        return await self._generate_email_via_llm(prompt, lead, "Use Case Follow-up")

    async def _generate_unanswered_intro_email(
        self,
        lead: Lead,
        call: Call,
        data_packet: Optional[DataPacket],
    ) -> Dict[str, str]:
        """
        Generate intro email for unanswered call (Requirement 6.x)

        Sections:
        - Who we are: Algonox intro
        - What we do: Services/solutions
        - Why we reached out: Personalized reason
        - Use cases: Multiple relevant examples
        - CTA: Reply to schedule
        """
        first_name = (lead.name or "there").split()[0]
        company = lead.company or "your company"

        # Get all available data about the company
        scraped_overview = getattr(lead, "scraped_company_overview", "") or ""
        scraped_services = getattr(lead, "scraped_services", []) or []
        scraped_industry = getattr(lead, "scraped_industry", "") or getattr(lead, "company_industry", "")

        # Format use cases
        use_cases = self._format_use_cases(data_packet)

        prompt = f"""You are writing an introductory email to a lead whose call was not answered.

LEAD INFORMATION:
- Name: {lead.name}
- First Name: {first_name}
- Title: {lead.title}
- Company: {company}
- Industry: {scraped_industry}

SCRAPED COMPANY DATA:
Overview: {scraped_overview[:600] if scraped_overview else "[Not available]"}
Services: {json.dumps(scraped_services[:5]) if scraped_services else "[Unknown]"}

USE CASES TO PRESENT:
{use_cases}

ALGONOX INFO:
{self.company_description}

EMAIL STRUCTURE REQUIRED:

1. **WHO WE ARE** - Brief intro to Algonox (credentials, what we specialize in)
   - 2-3 sentences

2. **WHAT WE DO** - Clear description of services
   - AI automation, intelligent agents, knowledge solutions
   - 3-4 sentences

3. **WHY WE REACHED OUT** - Personalized reason based on their company
   - Reference their industry/services
   - Show you did research
   - 2-3 sentences

4. **USE CASES** - 2-3 relevant examples
   - How we can help their specific business
   - Brief bullet points with impact

5. **CALL TO ACTION** - Clear invitation to reply
   - "Reply to this email and I'll send over some times that work"
   - Keep it low-pressure

SENDER INFO (for signature):
- Name: {self.sender_name}
- Title: {self.sender_title}
- Company: {self.company_name}

REQUIREMENTS:
- Informative yet concise
- Professional, not salesy
- Length: 300-400 words
- Include clear contact path
- Use cases must be relevant to their industry/position
- End with proper signature using sender name above (e.g., "Best regards,\\n{self.sender_name}\\n{self.sender_title}, {self.company_name}")

Return JSON only:
{{
    "subject": "[Personalized intro subject - not 'We tried to reach you']",
    "body_html": "<html with clear sections>",
    "body_text": "plain text"
}}
"""

        return await self._generate_email_via_llm(prompt, lead, "Introduction")

    def _format_use_cases(self, data_packet: Optional[DataPacket]) -> str:
        """Format use cases from data packet for prompts"""
        if not data_packet:
            return """
1. Process Automation - Automate repetitive workflows
2. AI-Powered Support - Intelligent customer/employee assistance
3. Knowledge Extraction - Insights from documents and data
"""

        return f"""
1. {data_packet.use_case_1_title or 'Process Automation'}
   Impact: {data_packet.use_case_1_impact or 'Reduced operational costs'}
   {data_packet.use_case_1_description or ''}

2. {data_packet.use_case_2_title or 'Support Enhancement'}
   Impact: {data_packet.use_case_2_impact or 'Faster resolution times'}
   {data_packet.use_case_2_description or ''}

3. {data_packet.use_case_3_title or 'Knowledge Management'}
   Impact: {data_packet.use_case_3_impact or 'Better decision making'}
   {data_packet.use_case_3_description or ''}
"""

    async def _generate_email_via_llm(
        self,
        prompt: str,
        lead: Lead,
        fallback_type: str,
    ) -> Dict[str, str]:
        """Generate email content using LLM with fallback"""
        try:
            response = await self.openai.generate_completion(
                prompt=prompt,
                temperature=0.6,
                max_tokens=1500,
                timeout_s=25.0,
            )

            if response:
                data = self._safe_parse_json(response)
                if data.get("subject") and data.get("body_html"):
                    return {
                        "subject": data["subject"],
                        "body_html": data["body_html"],
                        "body_text": data.get("body_text", ""),
                    }

        except Exception as e:
            logger.error(f"LLM email generation failed: {e}")

        # Fallback
        first_name = (lead.name or "there").split()[0]
        return {
            "subject": f"{fallback_type} - {self.company_name}",
            "body_html": f"<p>Hi {first_name},</p><p>Thank you for your time. We'd love to continue the conversation about how {self.company_name} can help {lead.company or 'your organization'}.</p><p>Best regards,<br>{self.sender_name}<br>{self.sender_title}, {self.company_name}</p>",
            "body_text": f"Hi {first_name},\n\nThank you for your time. We'd love to continue the conversation about how {self.company_name} can help {lead.company or 'your organization'}.\n\nBest regards,\n{self.sender_name}\n{self.sender_title}, {self.company_name}",
        }

    def _safe_parse_json(self, raw: str) -> Dict[str, Any]:
        """Safely parse JSON from LLM response"""
        raw = (raw or "").strip()
        if not raw:
            return {}

        # Remove markdown code blocks
        if "```" in raw:
            parts = raw.split("```")
            for part in parts:
                part = part.strip()
                if part.startswith("json"):
                    part = part[4:].strip()
                if part.startswith("{"):
                    raw = part
                    break

        if "{" in raw and "}" in raw:
            start = raw.find("{")
            end = raw.rfind("}") + 1
            raw = raw[start:end]

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}

    async def _send_email(self, email: Email, lead: Lead) -> Dict[str, Any]:
        """Send email via enhanced EmailService with templates and tracking"""
        try:
            success, tracking_id, error_category = await self.email_service.send_email(
                to_email=lead.email,
                to_name=lead.name or "there",
                subject=email.subject or "",
                html_body=email.body_html or "",
                text_body=email.body_text or self._html_to_text(email.body_html or ""),
                # New: pass lead_id and tracking_id for template wrapping
                lead_id=lead.id,
                tracking_id=email.tracking_id,
                preview_text=email.preview_text or "",
                use_template=True,
            )

            if success:
                email.status = "sent"
                email.sent_at = datetime.utcnow()
                if tracking_id:
                    email.tracking_id = tracking_id
                self.db.commit()
                logger.info(f"Email {email.id} sent to {lead.email}")
                return {"success": True, "tracking_id": tracking_id}

            # Store error details
            email.status = "failed"
            email.error_category = error_category
            email.retry_count = (email.retry_count or 0) + 1
            self.db.commit()

            # If recipient error, mark lead email as invalid
            if error_category == "recipient":
                lead.email_valid = False
                self.db.commit()
                logger.warning(f"Lead {lead.id} email marked invalid due to bounce")

            return {"success": False, "error": f"SMTP send failed: {error_category}"}

        except Exception as e:
            logger.error(f"Email send failed: {e}")
            email.status = "failed"
            email.error_message = str(e)[:500]
            email.retry_count = (email.retry_count or 0) + 1
            self.db.commit()
            return {"success": False, "error": str(e)}

    def _html_to_text(self, html: str) -> str:
        """Simple HTML to text conversion"""
        import re
        text = html.replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
        text = text.replace("</p>", "\n\n").replace("<p>", "")
        text = re.sub(r"<[^>]+>", "", text)
        return text.strip()
