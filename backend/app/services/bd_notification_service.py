# backend/app/services/bd_notification_service.py
from __future__ import annotations

from typing import Optional

from app.config import settings
from app.models.call import Call
from app.models.data_packet import DataPacket
from app.models.lead import Lead
from app.models.linkedin import LinkedInMessage
from app.services.email_service import EmailService
from app.utils.logger import logger


class BDNotificationService:
    """
    Sends an internal BD email (NOT stored in MySQL).
    """

    def __init__(self):
        self.mail = EmailService()

    async def send_bd_summary(
        self,
        lead: Lead,
        call: Call,
        packet: Optional[DataPacket],
        linkedin: Optional[LinkedInMessage],
    ) -> bool:
        to_list = (getattr(settings, "BD_EMAIL_TO", "") or "").strip()
        if not to_list:
            logger.warning("BD_EMAIL_TO not set; skipping BD email.")
            return False

        recipients = [x.strip() for x in to_list.split(",") if x.strip()]
        if not recipients:
            logger.warning("BD_EMAIL_TO empty after parsing; skipping BD email.")
            return False

        subject = f"[AADOS] Call Complete: {lead.name or 'Lead'} — {lead.company or ''}".strip()

        def esc(s: str) -> str:
            return (
                (s or "")
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )

        summary = esc(getattr(call, "transcript_summary", "") or "")
        sentiment = esc(getattr(call, "sentiment", "") or "")
        interest = esc(getattr(call, "lead_interest_level", "") or "")
        duration = getattr(call, "duration", None)

        html_parts = []
        html_parts.append("<h2>AADOS — BD Handoff</h2>")
        html_parts.append("<h3>Lead</h3>")
        html_parts.append(
            f"""
            <ul>
              <li><b>Name:</b> {esc(getattr(lead, "name", "") or "")}</li>
              <li><b>Email:</b> {esc(getattr(lead, "email", "") or "")}</li>
              <li><b>Phone:</b> {esc(getattr(lead, "phone", "") or "")}</li>
              <li><b>Company:</b> {esc(getattr(lead, "company", "") or "")}</li>
              <li><b>Title:</b> {esc(getattr(lead, "title", "") or "")}</li>
              <li><b>Industry:</b> {esc(getattr(lead, "company_industry", "") or "")}</li>
            </ul>
            """
        )

        html_parts.append("<h3>Call</h3>")
        html_parts.append(
            f"""
            <ul>
              <li><b>Call ID:</b> {call.id}</li>
              <li><b>Status:</b> {esc(getattr(call, "status", "") or "")}</li>
              <li><b>Duration:</b> {duration if duration is not None else "-"}s</li>
              <li><b>Sentiment:</b> {sentiment or "-"}</li>
              <li><b>Interest:</b> {interest or "-"}</li>
            </ul>
            """
        )

        html_parts.append("<h3>Summary</h3>")
        html_parts.append(f"<p>{summary or 'No summary available.'}</p>")

        if packet is not None:
            html_parts.append("<h3>Data Packet</h3>")
            html_parts.append(f"<p><b>Company analysis:</b><br/>{esc(packet.company_analysis or '')}</p>")
            html_parts.append("<p><b>Pain points:</b></p>")
            pains = packet.pain_points or []
            html_parts.append("<ul>" + "".join([f"<li>{esc(str(x))}</li>" for x in pains]) + "</ul>")
            html_parts.append("<p><b>Use cases:</b></p>")
            html_parts.append(
                "<ol>"
                + f"<li><b>{esc(packet.use_case_1_title or '')}</b> — {esc(packet.use_case_1_impact or '')}</li>"
                + f"<li><b>{esc(packet.use_case_2_title or '')}</b> — {esc(packet.use_case_2_impact or '')}</li>"
                + f"<li><b>{esc(packet.use_case_3_title or '')}</b> — {esc(packet.use_case_3_impact or '')}</li>"
                + "</ol>"
            )

        if linkedin is not None:
            html_parts.append("<h3>LinkedIn Messages</h3>")
            html_parts.append("<ul>")
            html_parts.append(f"<li><b>Connection request:</b><br/>{esc(linkedin.connection_request or '')}</li>")
            html_parts.append(f"<li><b>Use case 1:</b><br/>{esc(linkedin.use_case_1_message or '')}</li>")
            html_parts.append(f"<li><b>Use case 2:</b><br/>{esc(linkedin.use_case_2_message or '')}</li>")
            html_parts.append(f"<li><b>Use case 3:</b><br/>{esc(linkedin.use_case_3_message or '')}</li>")
            html_parts.append(f"<li><b>Follow up 1:</b><br/>{esc(linkedin.follow_up_1 or '')}</li>")
            html_parts.append(f"<li><b>Follow up 2:</b><br/>{esc(linkedin.follow_up_2 or '')}</li>")
            html_parts.append("</ul>")

        html_body = "\n".join(html_parts)
        text_body = (
            f"AADOS BD Handoff\n\n"
            f"Lead: {getattr(lead,'name','')} | {getattr(lead,'company','')}\n"
            f"Call ID: {call.id} | Status: {getattr(call,'status','')}\n"
            f"Sentiment: {getattr(call,'sentiment','')} | Interest: {getattr(call,'lead_interest_level','')}\n\n"
            f"Summary:\n{getattr(call,'transcript_summary','')}\n"
        )

        ok_all = True
        for to_email in recipients:
            # BD emails are internal, skip template wrapping and throttling
            success, _, _ = await self.mail.send_email(
                to_email=to_email,
                to_name="BD",
                subject=subject,
                html_body=html_body,
                text_body=text_body,
                attachments=None,
                use_template=False,  # Internal email, no branded template
                skip_throttle=True,  # System email, skip throttling
            )
            ok_all = ok_all and success

        return ok_all
