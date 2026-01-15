# backend/app/agents/email_agent.py
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.call import Call
from app.models.data_packet import DataPacket
from app.models.email import Email
from app.models.lead import Lead
from app.services.email_service import EmailService, generate_tracking_id
from app.services.openai_service import OpenAIService
from app.utils.logger import logger
from app.agents.email_intelligence_agent import EmailIntelligenceAgent


class EmailAgent:
    """
    Generates follow-up email drafts based on:
    - Lead profile
    - Data packet (3 use cases)
    - Call analysis (summary/sentiment/interest/objections/questions)
    - Optional PDF path stored for later (we do NOT attach for Gmail send in this feature)

    Existing behavior:
    ✅ Creates rows in `emails` table (status="draft")

    New behavior (added feature, gated by pipeline flag):
    ✅ Can send the first draft email to the lead via EmailService (Gmail SMTP)
    """

    def __init__(self, db: Session):
        self.db = db
        self.openai = OpenAIService()
        self.email_service = EmailService()
        self.intelligence = EmailIntelligenceAgent(db)

    # ---------------------------
    # Public API: Draft generation (unchanged behavior)
    # ---------------------------

    async def generate_and_store_sequence(
        self,
        call: Call,
    ) -> List[Email]:
        lead = self.db.query(Lead).filter(Lead.id == call.lead_id).first()
        if not lead:
            raise ValueError("Lead not found for call")

        existing = (
            self.db.query(Email)
            .filter(Email.call_id == call.id, Email.lead_id == lead.id)
            .order_by(Email.created_at.asc())
            .all()
        )
        if existing:
            logger.info(f"Email drafts already exist for call_id={call.id}, returning existing ({len(existing)})")
            return existing

        data_packet = self.db.query(DataPacket).filter(DataPacket.lead_id == lead.id).first()
        if not data_packet:
            raise ValueError("Missing data packet for lead. Generate DataPacket first.")

        primary_type = self._decide_primary_email_type(call)
        plan = self._build_sequence_plan(primary_type=primary_type)

        created: List[Email] = []
        for step in plan:
            content = await self._generate_email_content(
                lead=lead,
                data_packet=data_packet,
                call=call,
                email_type=step["email_type"],
                template_name=step["template_name"],
            )

            email = Email(
                lead_id=lead.id,
                call_id=call.id,
                subject=content["subject"],
                body_html=content["body_html"],
                body_text=content.get("body_text") or "",
                preview_text=content.get("preview_text") or "",
                email_type=step["email_type"],
                tracking_id=generate_tracking_id(),  # Generate unique tracking ID
                status="draft",
                created_at=datetime.utcnow(),
            )

            self.db.add(email)
            self.db.commit()
            self.db.refresh(email)
            created.append(email)

        logger.info(f"Created {len(created)} email drafts for call_id={call.id}, lead_id={lead.id}")
        return created

    async def generate_intelligent_sequence(
        self,
        call: Call,
        use_optimal_timing: bool = True,
    ) -> List[Email]:
        """
        Generate email sequence with AI-powered optimizations:
        - Optimal send time per lead
        - Subject line A/B testing consideration
        - Content quality analysis
        - Intelligent follow-up scheduling

        This is the enhanced version of generate_and_store_sequence.
        """
        lead = self.db.query(Lead).filter(Lead.id == call.lead_id).first()
        if not lead:
            raise ValueError("Lead not found for call")

        # Check existing emails
        existing = (
            self.db.query(Email)
            .filter(Email.call_id == call.id, Email.lead_id == lead.id)
            .order_by(Email.created_at.asc())
            .all()
        )
        if existing:
            logger.info(f"Email drafts already exist for call_id={call.id}")
            return existing

        data_packet = self.db.query(DataPacket).filter(DataPacket.lead_id == lead.id).first()
        if not data_packet:
            raise ValueError("Missing data packet for lead")

        # Get engagement data for personalization
        engagement = await self.intelligence.calculate_engagement_score(lead.id)

        # Get optimal send time
        optimal_time = await self.intelligence.get_optimal_send_time(lead.id) if use_optimal_timing else None

        # Determine email strategy based on engagement
        next_step = await self.intelligence.determine_next_sequence_step(lead.id, call.id)

        primary_type = self._decide_primary_email_type(call)
        plan = self._build_sequence_plan(primary_type=primary_type)

        # Adjust plan based on intelligence
        if engagement["level"] == "hot":
            # Skip nurture emails for hot leads, go straight to meeting request
            plan = [{"email_type": "meeting_request", "template_name": "meeting_request"}]
        elif engagement["level"] == "warm":
            # Add case study for warm leads
            plan[0]["include_case_study"] = True

        created: List[Email] = []
        for i, step in enumerate(plan):
            content = await self._generate_email_content(
                lead=lead,
                data_packet=data_packet,
                call=call,
                email_type=step["email_type"],
                template_name=step["template_name"],
            )

            # Analyze content quality
            analysis = await self.intelligence.analyze_email_content(
                subject=content["subject"],
                body_html=content["body_html"],
                email_type=step["email_type"],
            )

            # Calculate scheduled time for follow-ups
            scheduled_for = None
            if i > 0 and optimal_time:
                # Schedule follow-ups with delays
                from datetime import timedelta
                delays = {1: 3, 2: 8}  # Days after first email
                days_delay = delays.get(i, i * 3)
                scheduled_for = optimal_time + timedelta(days=days_delay)

            email = Email(
                lead_id=lead.id,
                call_id=call.id,
                subject=content["subject"],
                body_html=content["body_html"],
                body_text=content.get("body_text") or "",
                preview_text=content.get("preview_text") or "",
                email_type=step["email_type"],
                tracking_id=generate_tracking_id(),
                scheduled_for=scheduled_for,
                status="draft",
                created_at=datetime.utcnow(),
            )

            self.db.add(email)
            self.db.commit()
            self.db.refresh(email)
            created.append(email)

            logger.info(
                f"Created intelligent email {email.id} ({step['email_type']}) "
                f"quality_score={analysis['overall_score']} "
                f"scheduled_for={scheduled_for}"
            )

        # Update lead engagement data
        lead.email_engagement_score = engagement["score"]
        lead.email_engagement_level = engagement["level"]
        if optimal_time:
            lead.email_optimal_hour = optimal_time.hour
            lead.email_optimal_day = optimal_time.weekday()
        self.db.commit()

        return created

    # ---------------------------
    # New feature: Sending (Gmail SMTP) — does NOT change draft generation
    # ---------------------------

    async def send_email_by_id(self, email_id: int) -> Dict[str, Any]:
        """
        Sends a specific draft email to the lead via enhanced EmailService.
        Updates email.status + email.sent_at if successful.
        Includes unsubscribe checks and uses branded template.
        """
        email = self.db.query(Email).filter(Email.id == email_id).first()
        if not email:
            return {"success": False, "error": "Email not found"}

        lead = self.db.query(Lead).filter(Lead.id == email.lead_id).first()
        if not lead:
            return {"success": False, "error": "Lead not found"}

        if not (getattr(lead, "email", "") or "").strip():
            return {"success": False, "error": "Lead has no email"}

        # Check if lead unsubscribed
        if lead.unsubscribed_at:
            return {"success": False, "error": "Lead has unsubscribed from emails", "blocked": True}

        # Check if lead email is invalid
        if hasattr(lead, "email_valid") and lead.email_valid is False:
            return {"success": False, "error": "Lead email marked as invalid", "blocked": True}

        if (email.status or "").lower() == "sent":
            return {"success": True, "skipped": True, "error": None}

        # Generate tracking ID if not already set
        if not email.tracking_id:
            email.tracking_id = generate_tracking_id()
            self.db.commit()

        success, tracking_id, error_category = await self.email_service.send_email(
            to_email=lead.email,
            to_name=(lead.name or "there"),
            subject=(email.subject or "").strip(),
            html_body=(email.body_html or "").strip(),
            text_body=(email.body_text or "").strip() or self._html_to_text_fallback(email.body_html or ""),
            lead_id=lead.id,
            tracking_id=email.tracking_id,
            preview_text=getattr(email, "preview_text", "") or "",
            use_template=True,
        )

        if success:
            email.status = "sent"
            email.sent_at = datetime.utcnow()
            self.db.commit()
            logger.info(f"Email {email.id} sent to {lead.email}")
            return {"success": True, "email_id": email.id, "lead_id": lead.id, "tracking_id": tracking_id, "error": None}

        # Store error info
        email.status = "failed"
        email.error_category = error_category
        email.retry_count = (getattr(email, "retry_count", 0) or 0) + 1
        self.db.commit()

        # Mark email invalid on recipient error
        if error_category == "recipient":
            lead.email_valid = False
            self.db.commit()
            logger.warning(f"Lead {lead.id} email marked invalid")

        return {"success": False, "email_id": email.id, "lead_id": lead.id, "error": f"SMTP failed: {error_category}"}

    async def send_first_draft_for_call(self, call_id: int) -> Dict[str, Any]:
        """
        Sends ONLY the first (earliest) draft email for a call if it's still in draft status.
        This is what the post-call pipeline should call.
        """
        email = (
            self.db.query(Email)
            .filter(Email.call_id == call_id)
            .order_by(Email.created_at.asc())
            .first()
        )
        if not email:
            return {"success": False, "error": "No emails found for call"}

        # Only send if it's a draft
        if (email.status or "").lower() != "draft":
            return {"success": True, "skipped": True, "reason": f"status={email.status}"}

        return await self.send_email_by_id(email.id)

    def _html_to_text_fallback(self, html: str) -> str:
        # very simple fallback; avoids adding dependencies
        if not html:
            return ""
        t = html.replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
        t = t.replace("</p>", "\n\n").replace("<p>", "")
        # strip remaining tags crudely
        import re
        t = re.sub(r"<[^>]+>", "", t)
        return t.strip()

    # ---------------------------
    # Decision + plan (unchanged)
    # ---------------------------

    def _decide_primary_email_type(self, call: Call) -> str:
        if getattr(call, "demo_requested", False):
            return "demo_confirmation"
        if getattr(call, "follow_up_requested", False) or (getattr(call, "lead_interest_level", "") or "").lower() == "high":
            return "follow_up"
        return "nurture"

    def _build_sequence_plan(self, primary_type: str) -> List[Dict[str, str]]:
        return [
            {"email_type": primary_type, "template_name": primary_type},
            {"email_type": "follow_up_1", "template_name": "follow_up_1"},
            {"email_type": "follow_up_2", "template_name": "follow_up_2"},
        ]

    # ---------------------------
    # LLM generation (unchanged)
    # ---------------------------

    async def _generate_email_content(
        self,
        lead: Lead,
        data_packet: DataPacket,
        call: Call,
        email_type: str,
        template_name: str,
    ) -> Dict[str, Any]:
        prompt = self._build_prompt(lead, data_packet, call, email_type=email_type, template_name=template_name)

        response = await self.openai.generate_completion(
            prompt=prompt,
            temperature=0.6,
            max_tokens=1400,
        )

        try:
            data = json.loads(response)
        except json.JSONDecodeError:
            first_name = (lead.name or "there").split()[0]
            subj = f"Following up — {lead.company or 'Algonox'}"
            body = response.strip() or f"Hi {first_name},\n\nFollowing up on our conversation.\n\nBest,\nHarsha"
            data = {
                "subject": subj,
                "body_html": "<p>" + "</p><p>".join([line for line in body.split("\n") if line.strip()]) + "</p>",
                "body_text": body,
            }

        data["subject"] = (data.get("subject") or "").strip() or f"Following up — {lead.company or 'Algonox'}"
        data["body_html"] = (data.get("body_html") or "").strip() or "<p>Thanks for your time.</p>"
        data["body_text"] = (data.get("body_text") or "").strip() or "Thanks for your time."

        return data

    def _build_prompt(
        self,
        lead: Lead,
        data_packet: DataPacket,
        call: Call,
        email_type: str,
        template_name: str,
    ) -> str:
        first_name = (lead.name or "there").split()[0]
        company = lead.company or ""
        title = lead.title or ""
        industry = getattr(lead, "company_industry", "") or ""

        summary = (getattr(call, "transcript_summary", "") or "").strip()
        sentiment = (getattr(call, "sentiment", "") or "neutral").strip().lower()
        interest = (getattr(call, "lead_interest_level", "") or "medium").strip().lower()

        objections = getattr(call, "objections_raised", None) or []
        questions = getattr(call, "questions_asked", None) or []
        use_cases_discussed = getattr(call, "use_cases_discussed", None) or []

        instructions = ""
        if email_type == "demo_confirmation":
            instructions = """
Write a professional follow-up email confirming a demo.
- Thank them
- Confirm next steps
- Recap the most relevant use case(s) discussed
- Add a clear scheduling CTA (suggest 2 time slots; no links needed)
Tone: professional, upbeat, concise
Length: 150-220 words
"""
        elif email_type == "follow_up":
            instructions = """
Write a helpful, consultative follow-up email where interest was present but no hard commitment.
- Thank them
- Reference 1–2 key points from the call summary
- Address objections/questions briefly
- Propose a small next step (15-min call / quick walkthrough)
Tone: consultative, not pushy
Length: 180-260 words
"""
        elif email_type == "nurture":
            instructions = """
Write a brief nurture email for a low-interest call.
- Thank them
- Acknowledge timing may not be right
- Offer to stay in touch
- End with a low-friction question
Tone: respectful, light
Length: 100-160 words
"""
        elif email_type == "follow_up_1":
            instructions = """
Write Follow-Up #1 (if no reply).
- 3–5 short sentences
- Add ONE new piece of value (mini case-study, metric, or insight)
- End with a simple yes/no question
Tone: friendly, helpful
Length: 90-140 words
"""
        elif email_type == "follow_up_2":
            instructions = """
Write Follow-Up #2 (final follow-up).
- Respect their time
- Offer to close the loop or redirect to the right person
- End with one simple question
Tone: polite, minimal
Length: 60-110 words
"""
        else:
            instructions = """
Write a concise follow-up email.
- Thank them
- End with one simple question
"""

        return f"""
You are an SDR writing outbound follow-up emails for Algonox.

LEAD:
- Name: {lead.name}
- First name: {first_name}
- Title: {title}
- Company: {company}
- Industry: {industry}

CALL OUTCOME:
- Sentiment: {sentiment}
- Interest level: {interest}
- Demo requested: {bool(getattr(call, "demo_requested", False))}
- Follow-up requested: {bool(getattr(call, "follow_up_requested", False))}

CALL SUMMARY (use this for personalization; do NOT paste the full transcript):
{summary or "[No summary available]"}

OBJECTIONS (if any):
{json.dumps(objections) if objections else "[]"}

QUESTIONS ASKED (if any):
{json.dumps(questions) if questions else "[]"}

USE CASES AVAILABLE:
1) {data_packet.use_case_1_title} — {data_packet.use_case_1_impact}
2) {data_packet.use_case_2_title} — {data_packet.use_case_2_impact}
3) {data_packet.use_case_3_title} — {data_packet.use_case_3_impact}

USE CASES DISCUSSED (optional):
{json.dumps(use_cases_discussed) if use_cases_discussed else "[]"}

EMAIL TEMPLATE:
- template_name: {template_name}
- email_type: {email_type}

INSTRUCTIONS:
{instructions}

RULES:
- Do NOT include speaker labels like AGENT/LEAD.
- Do NOT include the raw transcript.
- Use a clear, human subject line.
- Close with "Best," and "Harsha".

Return JSON only:
{{
  "subject": "...",
  "body_html": "...",
  "body_text": "..."
}}
""".strip()