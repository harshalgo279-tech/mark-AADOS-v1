# backend/app/agents/pdf_generator_agent.py
from __future__ import annotations

from typing import Dict, Any, Optional
from sqlalchemy.orm import Session

from app.services.pdf_service import PDFService
from app.utils.logger import logger


class PDFGeneratorAgent:
    """
    Agent wrapper around PDFService for generating PDFs from pipeline outputs.
    Keeps orchestration logic out of api/calls.py.
    """

    def __init__(self, db: Session):
        self.db = db
        self.pdf = PDFService()

    def generate_linkedin_pack(
        self,
        lead: Dict[str, Any],
        call: Dict[str, Any],
        linkedin_pack: Dict[str, Any],
        filename: Optional[str] = None,
    ) -> str:
        """
        Generates the LinkedIn pack PDF and returns the path.
        """
        try:
            path = self.pdf.generate_linkedin_pack_pdf(
                lead=lead,
                call=call,
                linkedin_pack=linkedin_pack,
                filename=filename,
            )
            logger.info("LinkedIn pack PDF created: %s", path)
            return path
        except Exception as e:
            logger.error("PDF generation failed: %s", str(e))
            raise
