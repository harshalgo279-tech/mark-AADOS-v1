# backend/app/services/firecrawl_service.py
from __future__ import annotations

import os
from typing import Any, Dict, Optional

from app.utils.logger import logger

try:
    # firecrawl SDK
    from firecrawl import FirecrawlApp  # type: ignore

    logger.info("[Firecrawl] FirecrawlApp import OK")
except Exception as e:
    FirecrawlApp = None  # type: ignore
    logger.warning(f"[Firecrawl] FirecrawlApp import FAILED: {e}")


class FirecrawlService:
    def __init__(self):
        self.api_key = (os.getenv("FIRECRAWL_API_KEY") or "").strip()
        self.enabled = bool(self.api_key) and FirecrawlApp is not None

        self.client = None
        if self.enabled:
            try:
                self.client = FirecrawlApp(api_key=self.api_key)  # type: ignore
            except Exception as e:
                self.client = None
                self.enabled = False
                logger.error(f"[Firecrawl] FirecrawlApp init FAILED: {e}")

        # ✅ IMPORTANT DEBUG LOG (tells you if scraping can ever happen)
        logger.info(
            f"[Firecrawl] enabled={self.enabled} api_key_len={len(self.api_key)} client_is_none={self.client is None}"
        )

    def is_enabled(self) -> bool:
        return bool(self.enabled and self.client)

    def scrape_markdown(self, url: str, timeout_ms: int = 20000) -> Optional[Dict[str, Any]]:
        """
        Returns Firecrawl scrape result for a URL.
        We request markdown format.
        """
        if not self.client:
            logger.warning("[Firecrawl] scrape_markdown called but client is None")
            return None

        url = (url or "").strip()
        if not url:
            return None

        try:
            result = self.client.scrape(  # type: ignore
                url,
                params={
                    "formats": ["markdown"],
                    "timeout": timeout_ms,
                },
            )
            return result
        except Exception as e:
            logger.error(f"[Firecrawl] scrape error url={url}: {e}")
            return None

    def extract_structured(
        self, url: str, schema: Dict[str, Any], timeout_ms: int = 30000
    ) -> Optional[Dict[str, Any]]:
        """
        Extract structured fields from a URL using Firecrawl Extract.
        """
        if not self.client:
            logger.warning("[Firecrawl] extract_structured called but client is None")
            return None

        url = (url or "").strip()
        if not url:
            return None

        try:
            result = self.client.extract(  # type: ignore
                [url],
                params={
                    "schema": schema,
                    "timeout": timeout_ms,
                },
            )
            return result
        except Exception as e:
            logger.error(f"[Firecrawl] extract error url={url}: {e}")
            return None
