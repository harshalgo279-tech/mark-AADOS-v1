# backend/app/pipelines/call_pipeline.py
from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional, List

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.call import Call
from app.models.lead import Lead
from app.models.data_packet import DataPacket
from app.models.linkedin import LinkedInMessage

from app.api.websocket import manager
from app.services.openai_service import OpenAIService
from app.services.email_service import EmailService
from app.agents.linkedin_agent import LinkedInAgent
from app.agents.email_agent import EmailAgent
from app.agents.followup_email_agent import FollowUpEmailAgent, CallOutcome
from app.utils.logger import logger
from app.config import settings


# -----------------------------
# Helpers
# -----------------------------

def _clean_transcript_for_summary(txt: str) -> str:
    if not txt:
        return ""
    txt = re.sub(r"\bAGENT:\s*AGENT:\s*", "AGENT: ", txt, flags=re.IGNORECASE)
    txt = re.sub(r"\bLEAD:\s*LEAD:\s*", "LEAD: ", txt, flags=re.IGNORECASE)
    txt = re.sub(r"[ \t]+", " ", txt)
    return txt.strip()


async def ensure_call_analysis(db: Session, call: Call) -> Call:
    """
    Ensures call.transcript_summary/sentiment/lead_interest_level exist.
    Uses OpenAI if possible; falls back if not.
    """
    if (
        (call.transcript_summary or "").strip()
        and (call.sentiment or "").strip()
        and (call.lead_interest_level or "").strip()
    ):
        return call

    transcript = _clean_transcript_for_summary((call.full_transcript or "").strip())

    # no transcript yet -> safe defaults
    if not transcript:
        call.transcript_summary = call.transcript_summary or "No transcript available."
        call.sentiment = call.sentiment or "neutral"
        call.lead_interest_level = call.lead_interest_level or "medium"
        call.objections_raised = call.objections_raised or []
        call.questions_asked = call.questions_asked or []
        call.use_cases_discussed = call.use_cases_discussed or []
        db.commit()
        db.refresh(call)
        return call

    try:
        svc = OpenAIService()
        prompt = f"""
Analyze this outbound sales call transcript and return JSON only.

TRANSCRIPT:
{transcript}

Return JSON with keys:
- summary_paragraph: 1 paragraph, 3-5 sentences, NO speaker labels
- sentiment: "positive"|"neutral"|"negative"
- interest_level: "low"|"medium"|"high"
- objections: array of strings
- questions: array of strings
- use_cases_discussed: array of strings
- demo_requested: true/false
- follow_up_requested: true/false
""".strip()

        resp = await svc.generate_completion(
            prompt=prompt,
            temperature=0.2,
            max_tokens=900,
            timeout_s=15.0,
        )
        data = json.loads(resp) if resp else {}

        call.transcript_summary = (data.get("summary_paragraph") or "").strip() or call.transcript_summary
        call.sentiment = (data.get("sentiment") or "neutral").strip().lower() or call.sentiment or "neutral"
        call.lead_interest_level = (data.get("interest_level") or "medium").strip().lower() or call.lead_interest_level or "medium"

        call.objections_raised = data.get("objections") or call.objections_raised or []
        call.questions_asked = data.get("questions") or call.questions_asked or []
        call.use_cases_discussed = data.get("use_cases_discussed") or call.use_cases_discussed or []

        if data.get("demo_requested") is not None:
            call.demo_requested = bool(data.get("demo_requested"))
        if data.get("follow_up_requested") is not None:
            call.follow_up_requested = bool(data.get("follow_up_requested"))

        db.commit()
        db.refresh(call)
        return call

    except Exception as e:
        logger.error(f"ensure_call_analysis failed, using fallback: {e}")

    # fallback heuristics
    flattened = re.sub(r"\b(AGENT|LEAD):\s*", "", transcript, flags=re.IGNORECASE).strip()
    if len(flattened) > 650:
        flattened = flattened[:650].rsplit(" ", 1)[0] + "..."
    call.transcript_summary = call.transcript_summary or flattened

    t = transcript.lower()
    negative_markers = ["not interested", "bye", "stop", "no thanks", "don't call", "not now"]
    positive_markers = ["yes", "sure", "interested", "sounds good", "tell me more", "demo"]

    if any(m in t for m in negative_markers):
        call.sentiment = call.sentiment or "negative"
        call.lead_interest_level = call.lead_interest_level or "low"
    elif any(m in t for m in positive_markers):
        call.sentiment = call.sentiment or "positive"
        call.lead_interest_level = call.lead_interest_level or "high"
    else:
        call.sentiment = call.sentiment or "neutral"
        call.lead_interest_level = call.lead_interest_level or "medium"

    call.objections_raised = call.objections_raised or []
    call.questions_asked = call.questions_asked or []
    call.use_cases_discussed = call.use_cases_discussed or []

    db.commit()
    db.refresh(call)
    return call


class DataPacketAgent:
    """
    Generates + stores DataPacket to MySQL.
    lead_id is unique -> returns existing if already created.

    IMPORTANT:
    - Your updated flow creates DataPackets when the lead is created/updated (manual leads screen).
    - This class stays here because your API routes import it (and it may still be used for manual regeneration).
    """

    def __init__(self, db: Session):
        self.db = db
        self.openai = OpenAIService()

    async def create_data_packet(self, lead: Lead) -> DataPacket:
        existing = self.db.query(DataPacket).filter(DataPacket.lead_id == lead.id).first()
        if existing:
            return existing

        company = getattr(lead, "company", "") or ""
        title = getattr(lead, "title", "") or ""
        industry = getattr(lead, "company_industry", "") or ""

        iip = getattr(lead, "iip_data", None) or {}
        company_desc = ""
        if isinstance(iip, dict):
            company_desc = (iip.get("company_description") or "").strip()

        prompt = f"""
You generate a B2B SDR "data packet" for outbound sales.

Return JSON ONLY with keys:
- company_analysis (string, 4-6 lines)
- pain_points (array of strings, 4-7)
- use_case_1_title/use_case_1_description/use_case_1_impact
- use_case_2_title/use_case_2_description/use_case_2_impact
- use_case_3_title/use_case_3_description/use_case_3_impact
- solution_1_title/solution_1_description/solution_1_roi
- solution_2_title/solution_2_description/solution_2_roi
- solution_3_title/solution_3_description/solution_3_roi
- confidence_score (0.0-1.0)

LEAD:
Name: {lead.name}
Title: {title}
Company: {company}
Industry: {industry}
Company Description:
{company_desc or "[none]"}

Rules:
- Keep it realistic and non-fictional.
- No markdown. JSON only.
""".strip()

        raw = ""
        data: Dict[str, Any] = {}
        try:
            raw = await self.openai.generate_completion(
                prompt=prompt,
                temperature=0.3,
                max_tokens=1600,
                timeout_s=20.0,
            )
            data = self._safe_parse_json(raw)
        except Exception as e:
            logger.error(f"DataPacketAgent OpenAI failed: {e}")

        packet = DataPacket(
            lead_id=lead.id,
            company_analysis=data.get("company_analysis") or f"{company} operates in {industry}. Starter analysis (no enrichment).",
            pain_points=data.get("pain_points") or [],
            use_case_1_title=data.get("use_case_1_title") or "Process automation",
            use_case_1_description=data.get("use_case_1_description") or "Automate repetitive workflows to reduce manual effort.",
            use_case_1_impact=data.get("use_case_1_impact") or "Lower operational cost and faster throughput.",
            use_case_2_title=data.get("use_case_2_title") or "Support augmentation",
            use_case_2_description=data.get("use_case_2_description") or "AI triage and response drafting for faster resolutions.",
            use_case_2_impact=data.get("use_case_2_impact") or "Better CSAT and reduced response time.",
            use_case_3_title=data.get("use_case_3_title") or "Knowledge + insights",
            use_case_3_description=data.get("use_case_3_description") or "Extract insights from internal docs, calls and reports.",
            use_case_3_impact=data.get("use_case_3_impact") or "Faster decisions and improved visibility.",
            solution_1_title=data.get("solution_1_title") or "Automation Agents",
            solution_1_description=data.get("solution_1_description") or "Agents for repeated operational workflows.",
            solution_1_roi=data.get("solution_1_roi") or "Weeks to measurable time savings.",
            solution_2_title=data.get("solution_2_title") or "AI Knowledge Assistant",
            solution_2_description=data.get("solution_2_description") or "Internal assistant trained on SOPs and docs.",
            solution_2_roi=data.get("solution_2_roi") or "Lower escalations; faster onboarding.",
            solution_3_title=data.get("solution_3_title") or "Decision Copilot",
            solution_3_description=data.get("solution_3_description") or "Copilots for teams to operationalize insights.",
            solution_3_roi=data.get("solution_3_roi") or "Higher throughput and better outcomes.",
            confidence_score=float(data.get("confidence_score") or 0.6),
        )

        self.db.add(packet)
        self.db.commit()
        self.db.refresh(packet)
        logger.info(f"✅ DataPacket stored in MySQL lead_id={lead.id} packet_id={packet.id}")
        return packet

    def _safe_parse_json(self, raw: str) -> Dict[str, Any]:
        raw = (raw or "").strip()
        if not raw:
            return {}
        if "{" in raw and "}" in raw:
            raw = raw[raw.find("{") : raw.rfind("}") + 1]
        try:
            obj = json.loads(raw)
            return obj if isinstance(obj, dict) else {}
        except Exception:
            return {}


def _format_data_packet_text(packet: DataPacket) -> str:
    pp = packet.pain_points or []
    pp_lines = "\n".join([f"- {x}" for x in pp]) if isinstance(pp, list) else f"- {pp}"

    return f"""
COMPANY ANALYSIS:
{packet.company_analysis or ""}

PAIN POINTS:
{pp_lines}

USE CASES:
1) {packet.use_case_1_title or ""} — {packet.use_case_1_impact or ""}
   {packet.use_case_1_description or ""}

2) {packet.use_case_2_title or ""} — {packet.use_case_2_impact or ""}
   {packet.use_case_2_description or ""}

3) {packet.use_case_3_title or ""} — {packet.use_case_3_impact or ""}
   {packet.use_case_3_description or ""}

SOLUTIONS:
1) {packet.solution_1_title or ""} — {packet.solution_1_roi or ""}
   {packet.solution_1_description or ""}

2) {packet.solution_2_title or ""} — {packet.solution_2_roi or ""}
   {packet.solution_2_description or ""}

3) {packet.solution_3_title or ""} — {packet.solution_3_roi or ""}
   {packet.solution_3_description or ""}
""".strip()


def _format_linkedin_text(li: LinkedInMessage) -> str:
    return f"""
LINKEDIN:
Connection Request:
{li.connection_request or ""}

Use Case 1:
{li.use_case_1_message or ""}

Use Case 2:
{li.use_case_2_message or ""}

Use Case 3:
{li.use_case_3_message or ""}

Follow Up 1:
{li.follow_up_1 or ""}

Follow Up 2:
{li.follow_up_2 or ""}
""".strip()


async def _send_bd_email(
    lead: Lead,
    call: Call,
    packet: Optional[DataPacket],
    li: Optional[LinkedInMessage],
) -> bool:
    """
    Sends BD email (NOT stored in DB).
    """
    bd_to_raw = (getattr(settings, "BD_EMAIL_TO", "") or "").strip()
    if not bd_to_raw:
        logger.warning("BD_EMAIL_TO not configured; skipping BD email send.")
        return False

    recipients = [x.strip() for x in bd_to_raw.split(",") if x.strip()]
    if not recipients:
        logger.warning("BD_EMAIL_TO empty after parsing; skipping BD email send.")
        return False

    subject = f"[AADOS] Call Completed: {lead.name} @ {lead.company} (call_id={call.id})"

    packet_text = _format_data_packet_text(packet) if packet else "DataPacket not available."
    linkedin_text = _format_linkedin_text(li) if li else "LinkedIn messages not available."

    transcript_summary = (call.transcript_summary or "").strip()
    interest = (call.lead_interest_level or "").strip()
    sentiment = (call.sentiment or "").strip()
    duration = call.duration or 0
    recording = (call.recording_url or "").strip()
    transcript_tail = ((call.full_transcript or "").strip())[-2500:]

    text_body = f"""
LEAD:
- Name: {lead.name}
- Email: {getattr(lead, "email", "")}
- Phone: {getattr(lead, "phone", "")}
- Company: {lead.company}
- Title: {lead.title}
- Industry: {getattr(lead, "company_industry", "")}

CALL:
- Call ID: {call.id}
- Status: {call.status}
- Duration: {duration}s
- Sentiment: {sentiment}
- Interest: {interest}
- Recording: {recording or "N/A"}

SUMMARY:
{transcript_summary or "N/A"}

{packet_text}

{linkedin_text}

TRANSCRIPT (tail):
{transcript_tail or "N/A"}
""".strip()

    html_body = (
        "<pre style='font-family:ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; white-space:pre-wrap'>"
        + (text_body.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
        + "</pre>"
    )

    svc = EmailService()

    ok_all = True
    for to_email in recipients:
        ok = await svc.send_email(
            to_email=to_email,
            to_name="BD",
            subject=subject,
            html_body=html_body,
            text_body=text_body,
            attachments=None,
        )
        ok_all = ok_all and ok

    return ok_all


# -----------------------------
# Unanswered Call Handler
# -----------------------------

async def handle_unanswered_call(call_id: int) -> None:
    """
    Handles unanswered/no-answer calls by sending intro email.

    Called from Twilio status webhook when call status is:
    - no-answer
    - busy
    - failed
    - canceled

    Sends introductory email with:
    - Who we are
    - What we do
    - Why we reached out
    - Use cases
    - CTA to reply
    """
    db = SessionLocal()
    try:
        call = db.query(Call).filter(Call.id == call_id).first()
        if not call:
            logger.warning(f"Call not found for unanswered handler: call_id={call_id}")
            return

        lead = db.query(Lead).filter(Lead.id == call.lead_id).first()
        if not lead:
            logger.warning(f"Lead not found for unanswered call: lead_id={call.lead_id}")
            return

        # Skip if no email
        if not (getattr(lead, "email", "") or "").strip():
            logger.warning(f"Lead has no email, skipping unanswered email: lead_id={lead.id}")
            return

        await manager.broadcast({
            "type": "unanswered_call_processing",
            "call_id": call.id,
            "lead_id": lead.id,
        })

        # Generate and send intro email
        followup_agent = FollowUpEmailAgent(db)
        result = await followup_agent.generate_and_send_followup(
            call=call,
            outcome=CallOutcome.UNANSWERED,
            send_immediately=True,
        )

        await manager.broadcast({
            "type": "unanswered_email_sent",
            "call_id": call.id,
            "lead_id": lead.id,
            "email_id": result.get("email_id"),
            "success": result.get("success", False),
            "sent": result.get("sent", False),
        })

        logger.info(f"Unanswered call email processed: call_id={call.id}, success={result.get('success')}")

    except Exception as e:
        logger.error(f"Unanswered call handler failed call_id={call_id}: {e}")
        try:
            await manager.broadcast({
                "type": "unanswered_email_failed",
                "call_id": call_id,
                "error": str(e),
            })
        except Exception:
            pass
    finally:
        try:
            db.close()
        except Exception:
            pass


# -----------------------------
# Main Pipeline Entrypoint
# -----------------------------

async def run_post_call_pipeline(call_id: int) -> None:
    """
    Runs after call completion (triggered after transcript is available).

    IMPORTANT (your requirement):
    - DataPacket is created when the lead is entered (manual call tab), NOT after the call.
    - So this pipeline must NOT create DataPacket; it only fetches it if present.

    Creates:
    - call analysis
    - LinkedInMessage (stored) [only if DataPacket exists]
    - Lead follow-up email drafts (stored)
    Sends:
    - BD email (NOT stored)
    Broadcasts:
    - websocket events to update UI
    """
    db = SessionLocal()
    try:
        call = db.query(Call).filter(Call.id == call_id).first()
        if not call:
            return

        lead = db.query(Lead).filter(Lead.id == call.lead_id).first()
        if not lead:
            return

        await manager.broadcast({"type": "pipeline_started", "call_id": call.id, "lead_id": lead.id})

        # 1) Ensure analysis
        await ensure_call_analysis(db, call)
        await manager.broadcast({"type": "call_analysis_ready", "call_id": call.id, "lead_id": lead.id})

        # 2) Fetch DataPacket (DO NOT CREATE HERE)
        packet: Optional[DataPacket] = (
            db.query(DataPacket).filter(DataPacket.lead_id == lead.id).first()
        )

        # Keep UI stable: only emit generated event if it exists
        if packet is not None:
            await manager.broadcast({
                "type": "data_packet_generated",
                "call_id": call.id,
                "lead_id": lead.id,
                "packet_id": packet.id,
            })
        else:
            await manager.broadcast({
                "type": "data_packet_missing",
                "call_id": call.id,
                "lead_id": lead.id,
            })

        # 3) Generate LinkedIn (stored) — only if packet exists
        linkedin_row: Optional[LinkedInMessage] = None
        if packet is not None:
            try:
                linkedin_row = await LinkedInAgent(db).generate_linkedin_messages(
                    lead=lead,
                    data_packet=packet,
                    call=call,
                )
                await manager.broadcast({
                    "type": "linkedin_messages_generated",
                    "call_id": call.id,
                    "lead_id": lead.id,
                    "linkedin_id": linkedin_row.id,
                })
            except Exception as e:
                logger.error(f"LinkedIn pipeline failed call_id={call.id}: {e}")

            if linkedin_row is None:
                linkedin_row = (
                    db.query(LinkedInMessage)
                    .filter(LinkedInMessage.lead_id == lead.id)
                    .order_by(LinkedInMessage.generated_at.desc())
                    .first()
                )
        else:
            logger.warning(f"Skipping LinkedIn generation: DataPacket missing lead_id={lead.id}")

        # 4) Generate follow-up email based on call outcome (NEW FLOW)
        # This replaces the generic email sequence with outcome-specific emails
        try:
            followup_agent = FollowUpEmailAgent(db)
            outcome = followup_agent.determine_call_outcome(call)

            logger.info(f"Call outcome detected: {outcome.value} for call_id={call.id}")

            # Generate and send appropriate follow-up
            followup_result = await followup_agent.generate_and_send_followup(
                call=call,
                outcome=outcome,
                send_immediately=True,  # Auto-send based on call outcome
            )

            await manager.broadcast({
                "type": "followup_email_processed",
                "call_id": call.id,
                "lead_id": lead.id,
                "outcome": outcome.value,
                "email_id": followup_result.get("email_id"),
                "sent": followup_result.get("sent", False),
                "success": followup_result.get("success", False),
            })

            # Also generate the standard email sequence for future follow-ups
            emails = await EmailAgent(db).generate_and_store_sequence(call=call)
            await manager.broadcast({
                "type": "emails_created",
                "call_id": call.id,
                "lead_id": lead.id,
                "count": len(emails),
            })

        except Exception as e:
            logger.error(f"Follow-up email processing failed call_id={call.id}: {e}")
            # Fallback to original email sequence
            try:
                emails = await EmailAgent(db).generate_and_store_sequence(call=call)
                await manager.broadcast({
                    "type": "emails_created",
                    "call_id": call.id,
                    "lead_id": lead.id,
                    "count": len(emails),
                })
            except Exception as e2:
                logger.error(f"Fallback email generation also failed: {e2}")

        # 5) Send BD email (NOT stored)
        try:
            ok = await _send_bd_email(lead=lead, call=call, packet=packet, li=linkedin_row)
            await manager.broadcast({
                "type": "bd_email_sent",
                "call_id": call.id,
                "lead_id": lead.id,
                "success": bool(ok),
            })
        except Exception as e:
            logger.error(f"BD email send failed call_id={call.id}: {e}")
            await manager.broadcast({
                "type": "bd_email_sent",
                "call_id": call.id,
                "lead_id": lead.id,
                "success": False,
            })

        await manager.broadcast({"type": "pipeline_completed", "call_id": call.id, "lead_id": lead.id})

    except Exception as e:
        logger.error(f"Pipeline fatal error call_id={call_id}: {e}")
        try:
            await manager.broadcast({"type": "pipeline_failed", "call_id": call_id, "error": str(e)})
        except Exception:
            pass
    finally:
        try:
            db.close()
        except Exception:
            pass
