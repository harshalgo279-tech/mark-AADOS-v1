# backend/app/services/pdf_service.py
from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.config import settings
from app.utils.logger import logger


class PDFService:
    """Service for PDF generation operations"""

    def __init__(self):
        out_dir = getattr(settings, "PDF_OUTPUT_DIR", None)
        if not out_dir or not str(out_dir).strip():
            raise ValueError(
                "PDF_OUTPUT_DIR is not set. Add PDF_OUTPUT_DIR to your .env with an absolute Windows path."
            )

        self.output_dir = str(out_dir).strip()
        os.makedirs(self.output_dir, exist_ok=True)
        logger.info(f"PDFService output_dir set to: {self.output_dir}")

    def _safe(self, text: str) -> str:
        return escape((text or "").strip())

    def _slug(self, s: str) -> str:
        """
        Make a Windows-safe filename segment.
        Removes: \ / : * ? " < > | and trims length.
        """
        s = (s or "").strip()
        s = re.sub(r"\s+", "_", s)
        s = re.sub(r'[\\/:*?"<>|]+', "", s)  # Windows illegal chars
        s = re.sub(r"[^A-Za-z0-9_\-]+", "", s)
        return s[:60] if s else "Unknown"

    def _paragraph(self, text: str, style_name: str = "BodyText") -> Paragraph:
        styles = getSampleStyleSheet()
        return Paragraph(self._safe(text).replace("\n", "<br/>"), styles[style_name])

    def create_table(self, data: list, col_widths: list = None, style: list = None) -> Table:
        table = Table(data, colWidths=col_widths)
        if style:
            table.setStyle(TableStyle(style))
        else:
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 11),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
                ("BACKGROUND", (0, 1), (-1, -1), colors.beige),
                ("GRID", (0, 0), (-1, -1), 1, colors.black),
            ]))
        return table

    def generate_pdf(self, filename: str, title: str, content: list) -> str:
        try:
            # Force output into configured folder
            filepath = os.path.join(self.output_dir, filename)

            doc = SimpleDocTemplate(filepath, pagesize=letter)
            story: List[Any] = []

            styles = getSampleStyleSheet()
            title_style = ParagraphStyle(
                "CustomTitle",
                parent=styles["Heading1"],
                fontSize=20,
                textColor=colors.HexColor("#2B8AFF"),
                spaceAfter=12,
                alignment=TA_CENTER,
            )

            story.append(Paragraph(self._safe(title), title_style))
            story.append(Spacer(1, 0.3 * inch))
            story.extend(content)

            doc.build(story)

            logger.info(f"PDF generated: {filepath}")
            return filepath

        except Exception as e:
            logger.error(f"Error generating PDF: {str(e)}")
            raise

    def generate_linkedin_pack_pdf(
        self,
        lead: Dict[str, Any],
        call: Dict[str, Any],
        linkedin_pack: Dict[str, Any],
        filename: Optional[str] = None,
    ) -> str:
        lead_name = self._slug(str(lead.get("name", "")))
        company = self._slug(str(lead.get("company", "")))
        call_id = str(call.get("id", ""))

        if not filename:
            ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            filename = f"{lead_name}_{company}_linkedin_pack_call_{call_id}_{ts}.pdf"

        content: List[Any] = []

        table_data = [
            ["Field", "Value", "Field", "Value"],
            ["Lead ID", str(lead.get("id", "")), "Call ID", str(call.get("id", ""))],
            ["Name", lead.get("name", "") or "", "Email", lead.get("email", "") or ""],
            ["Phone", lead.get("phone", "") or "", "Company", lead.get("company", "") or ""],
            ["Title", lead.get("title", "") or "", "Industry", lead.get("company_industry", "") or ""],
            ["Call Status", call.get("status", "") or "", "Duration (s)", str(call.get("duration", "") or "")],
            ["Interest", call.get("lead_interest_level", "") or "", "Sentiment", call.get("sentiment", "") or ""],
        ]

        content.append(self.create_table(
            table_data,
            col_widths=[1.2 * inch, 2.8 * inch, 1.2 * inch, 2.8 * inch],
            style=[
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2B8AFF")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 10),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("BACKGROUND", (0, 1), (-1, -1), colors.whitesmoke),
            ],
        ))
        content.append(Spacer(1, 0.25 * inch))

        bd_summary = (linkedin_pack.get("bd_summary") or "").strip()
        if bd_summary:
            content.append(self._paragraph("BD Summary", "Heading2"))
            content.append(self._paragraph(bd_summary, "BodyText"))
            content.append(Spacer(1, 0.2 * inch))

        def add_block(title: str, text: str):
            txt = (text or "").strip()
            if not txt:
                return
            content.append(self._paragraph(title, "Heading3"))
            content.append(self._paragraph(txt, "BodyText"))
            content.append(Spacer(1, 0.15 * inch))

        add_block("Connection Request", linkedin_pack.get("connection_request"))
        add_block("Use Case 1 Message", linkedin_pack.get("use_case_1_message"))
        add_block("Use Case 2 Message", linkedin_pack.get("use_case_2_message"))
        add_block("Use Case 3 Message", linkedin_pack.get("use_case_3_message"))
        add_block("Follow Up 1", linkedin_pack.get("follow_up_1"))
        add_block("Follow Up 2", linkedin_pack.get("follow_up_2"))

        title = f"LinkedIn Message Pack — {lead.get('company', '')}".strip()
        return self.generate_pdf(filename=filename, title=title, content=content)
