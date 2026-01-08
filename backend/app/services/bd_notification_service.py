from __future__ import annotations

from datetime import datetime
from typing import Optional

from app.services.email_service import EmailService
from app.models.email import Email
from app.models.lead import Lead
from app.models.data_packet import DataPacket
from app.utils.logger import logger


class BDNotificationService:
    def __init__(self, db):
        self.db = db
        self.email_service = EmailService()

    async def send_notification(self, packet: DataPacket, lead: Lead) -> None:
        try:
            recipients_raw = (getattr(__import__("app.config", fromlist=["settings"]).settings, "BD_EMAIL_TO", None) or "").strip()
            if not recipients_raw:
                return

            recipients = [r.strip() for r in recipients_raw.split(",") if r.strip()]
            if not recipients:
                return

            subject = f"New Lead: {lead.name or ''} — {lead.company or ''}"

            html_lines = []
            html_lines.append(f"<h2>Lead: {lead.name or ''} — {lead.company or ''}</h2>")
            html_lines.append("<h3>Contact</h3>")
            html_lines.append("<ul>")
            html_lines.append(f"<li>Email: {getattr(lead, 'email', '')}</li>")
            html_lines.append(f"<li>Phone: {getattr(lead, 'phone', '')}</li>")
            html_lines.append(f"<li>Title: {getattr(lead, 'title', '')}</li>")
            html_lines.append(f"<li>Industry: {getattr(lead, 'company_industry', '')}</li>")
            html_lines.append("</ul>")

            html_lines.append("<h3>Data Packet Summary</h3>")
            html_lines.append(f"<p><strong>Company analysis:</strong><br>{packet.company_analysis or ''}</p>")

            for i in (1, 2, 3):
                title = getattr(packet, f"use_case_{i}_title", None)
                impact = getattr(packet, f"use_case_{i}_impact", None)
                desc = getattr(packet, f"use_case_{i}_description", None)
                if title or desc or impact:
                    html_lines.append(f"<h4>Use case {i}: {title or ''}</h4>")
                    if desc:
                        html_lines.append(f"<p>{desc}</p>")
                    if impact:
                        html_lines.append(f"<p><em>Impact:</em> {impact}</p>")

            html_lines.append("<h3>Suggested Solutions</h3>")
            for i in (1, 2, 3):
                st = getattr(packet, f"solution_{i}_title", None)
                sd = getattr(packet, f"solution_{i}_description", None)
                sr = getattr(packet, f"solution_{i}_roi", None)
                if st or sd or sr:
                    html_lines.append(f"<h4>{st or ''}</h4>")
                    if sd:
                        html_lines.append(f"<p>{sd}</p>")
                    if sr:
                        html_lines.append(f"<p><em>ROI:</em> {sr}</p>")

            html_body = "\n".join(html_lines)

            text_lines = [f"Lead: {lead.name or ''} — {lead.company or ''}", "\nContact:"]
            text_lines.append(f"Email: {getattr(lead, 'email', '')}")
            text_lines.append(f"Phone: {getattr(lead, 'phone', '')}")
            text_lines.append("\nCompany analysis:")
            text_lines.append(packet.company_analysis or "")
            text_body = "\n".join(text_lines)

            for r in recipients:
                try:
                    ok = await self.email_service.send_email(
                        to_email=r,
                        to_name="BD Team",
                        subject=subject,
                        html_body=html_body,
                        text_body=text_body,
                    )

                    e_row = Email(
                        lead_id=lead.id,
                        call_id=None,
                        subject=subject,
                        body_html=html_body,
                        body_text=text_body,
                        email_type="bd_notification",
                        status="sent" if ok else "failed",
                        sent_at=(datetime.utcnow() if ok else None),
                        created_at=datetime.utcnow(),
                    )
                    self.db.add(e_row)
                    self.db.commit()
                except Exception as e:
                    try:
                        self.db.rollback()
                    except Exception:
                        pass
                    logger.exception("BD notification send failed: %s", e)
        except Exception as e:
            logger.exception("BD notification fatal error: %s", e)
