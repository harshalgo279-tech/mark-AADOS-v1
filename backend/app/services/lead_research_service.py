# backend/app/services/lead_research_service.py
from __future__ import annotations

from typing import Any, Dict, List
from urllib.parse import urljoin, urlparse

from app.services.firecrawl_service import FirecrawlService
from app.utils.logger import logger


def _normalize_url(u: str) -> str:
    u = (u or "").strip()
    if not u:
        return ""
    if not u.startswith(("http://", "https://")):
        u = "https://" + u
    return u


def _base_domain(url: str) -> str:
    try:
        p = urlparse(url)
        if not p.scheme or not p.netloc:
            return ""
        return f"{p.scheme}://{p.netloc}".rstrip("/")
    except Exception:
        return ""


class LeadResearchService:
    """
    Firecrawl wrapper that returns an LLM-ready research bundle.

    Output:
      {
        "ok": bool,
        "sources": [url, ...],
        "markdown": "combined markdown"
      }
    """

    def __init__(self):
        self.firecrawl = FirecrawlService()

    def is_enabled(self) -> bool:
        return bool(getattr(self.firecrawl, "is_enabled", lambda: False)())

    def build_urls_to_scrape(self, company_url: str) -> List[str]:
        """
        Conservative scraping: homepage + a few standard pages.
        Keep small to avoid cost/time blowups.
        """
        company_url = _normalize_url(company_url)
        base = _base_domain(company_url)
        if not base:
            return [company_url] if company_url else []

        paths = [
            "",            # homepage
            "/about",
            "/company",
            "/solutions",
            "/product",
            "/products",
        ]

        urls: List[str] = []
        for path in paths:
            urls.append(urljoin(base + "/", path.lstrip("/")))

        # de-dupe preserving order
        out: List[str] = []
        seen = set()
        for u in urls:
            if u and u not in seen:
                seen.add(u)
                out.append(u)

        return out[:4]  # cap pages

    def scrape_company_markdown(self, company_url: str) -> Dict[str, Any]:
        if not self.is_enabled():
            return {"ok": False, "sources": [], "markdown": ""}

        urls = self.build_urls_to_scrape(company_url)
        if not urls:
            return {"ok": False, "sources": [], "markdown": ""}

        chunks: List[str] = []
        sources: List[str] = []

        for u in urls:
            try:
                res = self.firecrawl.scrape_markdown(u)
                if not res:
                    continue

                # Firecrawl SDK response shapes vary; support common variants.
                md = (res.get("markdown") or res.get("data", {}).get("markdown") or "").strip()
                if md:
                    chunks.append(md[:9000])
                    sources.append(u)
            except Exception as e:
                logger.error(f"Firecrawl scrape failed for {u}: {e}")

        combined = "\n\n---\n\n".join(chunks).strip()
        return {"ok": bool(combined), "sources": sources, "markdown": combined}
