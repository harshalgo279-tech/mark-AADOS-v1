# backend/app/services/company_scraper_service.py
"""
Enhanced Company Scraping Service

Extracts comprehensive company information from websites:
- Company overview/description
- Services offered
- Industry/sector
- Key products
- Contact information
- Other relevant business information

Implements error handling for:
- Scraping restrictions (403, robots.txt)
- Dynamic content (JS-rendered pages)
- Unusual page structures
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse
from dataclasses import dataclass, asdict

from app.services.firecrawl_service import FirecrawlService
from app.services.openai_service import OpenAIService
from app.utils.logger import logger


@dataclass
class ScrapedCompanyData:
    """Structured company data extracted from website"""
    company_name: str = ""
    company_overview: str = ""
    services: List[str] = None
    products: List[str] = None
    industry: str = ""
    sector: str = ""
    contact_email: str = ""
    contact_phone: str = ""
    headquarters_location: str = ""
    founded_year: str = ""
    company_size: str = ""
    key_differentiators: List[str] = None
    target_customers: str = ""
    technology_stack: List[str] = None
    certifications: List[str] = None
    partnerships: List[str] = None
    raw_markdown: str = ""
    scrape_success: bool = False
    scrape_errors: List[str] = None
    sources_scraped: List[str] = None
    confidence_score: float = 0.0

    def __post_init__(self):
        if self.services is None:
            self.services = []
        if self.products is None:
            self.products = []
        if self.key_differentiators is None:
            self.key_differentiators = []
        if self.technology_stack is None:
            self.technology_stack = []
        if self.certifications is None:
            self.certifications = []
        if self.partnerships is None:
            self.partnerships = []
        if self.scrape_errors is None:
            self.scrape_errors = []
        if self.sources_scraped is None:
            self.sources_scraped = []

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class CompanyScraperService:
    """
    Enhanced web scraping service for comprehensive company data extraction.

    Features:
    - Multi-page scraping (homepage, about, services, products, contact)
    - LLM-powered structured extraction
    - Error handling for restricted/dynamic content
    - Accuracy tracking and confidence scoring
    """

    def __init__(self):
        self.firecrawl = FirecrawlService()
        self.openai = OpenAIService()

        # Pages to scrape for comprehensive data
        self.target_pages = [
            "",              # homepage
            "/about",
            "/about-us",
            "/company",
            "/services",
            "/solutions",
            "/products",
            "/product",
            "/contact",
            "/contact-us",
        ]

        # Maximum pages to scrape (cost control)
        self.max_pages = 6

        # Track scraping metrics
        self.metrics = {
            "total_attempts": 0,
            "successful_scrapes": 0,
            "failed_scrapes": 0,
            "partial_scrapes": 0,
        }

    def is_enabled(self) -> bool:
        return self.firecrawl.is_enabled()

    def _normalize_url(self, url: str) -> str:
        """Normalize URL to standard format"""
        url = (url or "").strip()
        if not url:
            return ""
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        # Remove trailing slash for consistency
        return url.rstrip("/")

    def _get_base_domain(self, url: str) -> str:
        """Extract base domain from URL"""
        try:
            parsed = urlparse(url)
            if parsed.scheme and parsed.netloc:
                return f"{parsed.scheme}://{parsed.netloc}"
        except Exception:
            pass
        return ""

    def _build_scrape_urls(self, company_url: str) -> List[str]:
        """Build list of URLs to scrape for comprehensive data"""
        company_url = self._normalize_url(company_url)
        base = self._get_base_domain(company_url)

        if not base:
            return [company_url] if company_url else []

        urls = []
        seen = set()

        for path in self.target_pages:
            full_url = urljoin(base + "/", path.lstrip("/"))
            if full_url not in seen:
                seen.add(full_url)
                urls.append(full_url)

        return urls[:self.max_pages]

    async def scrape_company(self, company_url: str, company_name: str = "") -> ScrapedCompanyData:
        """
        Main method to scrape and extract comprehensive company data.

        Args:
            company_url: Company website URL
            company_name: Optional company name for context

        Returns:
            ScrapedCompanyData with all extracted information
        """
        self.metrics["total_attempts"] += 1

        result = ScrapedCompanyData(
            company_name=company_name,
        )

        if not self.is_enabled():
            result.scrape_errors.append("Firecrawl service not enabled (missing API key)")
            logger.warning("[CompanyScraper] Firecrawl not enabled")
            return result

        company_url = self._normalize_url(company_url)
        if not company_url:
            result.scrape_errors.append("No valid company URL provided")
            return result

        # Build URLs to scrape
        urls = self._build_scrape_urls(company_url)
        if not urls:
            result.scrape_errors.append("Could not build URLs from provided company URL")
            return result

        # Scrape all pages
        combined_markdown = await self._scrape_multiple_pages(urls, result)

        if not combined_markdown:
            self.metrics["failed_scrapes"] += 1
            result.scrape_errors.append("Failed to extract any content from website")
            return result

        result.raw_markdown = combined_markdown

        # Extract structured data using LLM
        extracted = await self._extract_structured_data(
            markdown=combined_markdown,
            company_name=company_name,
            company_url=company_url,
        )

        # Update result with extracted data
        self._update_result_from_extraction(result, extracted)

        # Calculate confidence score
        result.confidence_score = self._calculate_confidence(result)
        result.scrape_success = result.confidence_score > 0.3

        if result.scrape_success:
            self.metrics["successful_scrapes"] += 1
        else:
            self.metrics["partial_scrapes"] += 1

        logger.info(
            f"[CompanyScraper] Completed scrape for {company_url} - "
            f"success={result.scrape_success} confidence={result.confidence_score:.2f}"
        )

        return result

    async def _scrape_multiple_pages(
        self, urls: List[str], result: ScrapedCompanyData
    ) -> str:
        """Scrape multiple pages and combine markdown content"""
        chunks = []

        for url in urls:
            try:
                scrape_result = self.firecrawl.scrape_markdown(url, timeout_ms=25000)

                if not scrape_result:
                    result.scrape_errors.append(f"Empty response from {url}")
                    continue

                # Handle different Firecrawl response formats
                markdown = (
                    scrape_result.get("markdown")
                    or scrape_result.get("data", {}).get("markdown")
                    or ""
                ).strip()

                if markdown:
                    # Limit individual page content
                    chunks.append(f"=== SOURCE: {url} ===\n\n{markdown[:12000]}")
                    result.sources_scraped.append(url)
                else:
                    result.scrape_errors.append(f"No markdown content from {url}")

            except Exception as e:
                error_msg = str(e)

                # Categorize error types
                if "403" in error_msg or "forbidden" in error_msg.lower():
                    result.scrape_errors.append(f"Access forbidden (403) for {url}")
                elif "404" in error_msg or "not found" in error_msg.lower():
                    result.scrape_errors.append(f"Page not found (404) for {url}")
                elif "timeout" in error_msg.lower():
                    result.scrape_errors.append(f"Timeout scraping {url}")
                elif "robot" in error_msg.lower():
                    result.scrape_errors.append(f"Blocked by robots.txt for {url}")
                else:
                    result.scrape_errors.append(f"Error scraping {url}: {error_msg[:100]}")

                logger.error(f"[CompanyScraper] Failed to scrape {url}: {e}")

        return "\n\n---\n\n".join(chunks)

    async def _extract_structured_data(
        self,
        markdown: str,
        company_name: str,
        company_url: str,
    ) -> Dict[str, Any]:
        """Use LLM to extract structured company data from markdown"""

        # Truncate if too long
        if len(markdown) > 25000:
            markdown = markdown[:25000] + "\n\n[TRUNCATED]"

        prompt = f"""You are analyzing a company website to extract business information.

COMPANY NAME (if known): {company_name or "[Unknown]"}
COMPANY WEBSITE: {company_url}

WEBSITE CONTENT:
{markdown}

Extract the following information and return as JSON only:

{{
    "company_name": "Official company name",
    "company_overview": "2-4 sentence description of what the company does",
    "services": ["service 1", "service 2", ...],
    "products": ["product 1", "product 2", ...],
    "industry": "Primary industry (e.g., Technology, Healthcare, Finance)",
    "sector": "Specific sector (e.g., SaaS, Medical Devices, Investment Banking)",
    "contact_email": "main contact email if found",
    "contact_phone": "main phone number if found",
    "headquarters_location": "city, state/country",
    "founded_year": "year founded if mentioned",
    "company_size": "employee count or range if mentioned",
    "key_differentiators": ["what makes them unique 1", "differentiator 2", ...],
    "target_customers": "who they sell to (e.g., Enterprise, SMB, Consumers)",
    "technology_stack": ["technology 1", "technology 2", ...],
    "certifications": ["certification 1", ...],
    "partnerships": ["partner 1", ...]
}}

RULES:
- Extract only information explicitly stated or clearly implied
- Use empty string "" for text fields not found
- Use empty array [] for list fields not found
- Do NOT make up or hallucinate information
- Return ONLY valid JSON, no markdown or explanation
"""

        try:
            response = await self.openai.generate_completion(
                prompt=prompt,
                temperature=0.1,
                max_tokens=2000,
                timeout_s=30.0,
            )

            if not response:
                return {}

            # Clean and parse JSON
            return self._safe_parse_json(response)

        except Exception as e:
            logger.error(f"[CompanyScraper] LLM extraction failed: {e}")
            return {}

    def _safe_parse_json(self, raw: str) -> Dict[str, Any]:
        """Safely parse JSON from LLM response"""
        raw = (raw or "").strip()
        if not raw:
            return {}

        # Remove markdown code blocks if present
        if "```" in raw:
            parts = raw.split("```")
            for part in parts:
                part = part.strip()
                if part.startswith("json"):
                    part = part[4:].strip()
                if part.startswith("{"):
                    raw = part
                    break

        # Find JSON object boundaries
        if "{" in raw and "}" in raw:
            start = raw.find("{")
            end = raw.rfind("}") + 1
            raw = raw[start:end]

        try:
            obj = json.loads(raw)
            return obj if isinstance(obj, dict) else {}
        except json.JSONDecodeError:
            return {}

    def _update_result_from_extraction(
        self, result: ScrapedCompanyData, extracted: Dict[str, Any]
    ) -> None:
        """Update result dataclass with extracted data"""
        if not extracted:
            return

        # String fields
        result.company_name = (extracted.get("company_name") or result.company_name or "").strip()
        result.company_overview = (extracted.get("company_overview") or "").strip()
        result.industry = (extracted.get("industry") or "").strip()
        result.sector = (extracted.get("sector") or "").strip()
        result.contact_email = (extracted.get("contact_email") or "").strip()
        result.contact_phone = (extracted.get("contact_phone") or "").strip()
        result.headquarters_location = (extracted.get("headquarters_location") or "").strip()
        result.founded_year = (extracted.get("founded_year") or "").strip()
        result.company_size = (extracted.get("company_size") or "").strip()
        result.target_customers = (extracted.get("target_customers") or "").strip()

        # List fields
        result.services = self._ensure_list(extracted.get("services"))
        result.products = self._ensure_list(extracted.get("products"))
        result.key_differentiators = self._ensure_list(extracted.get("key_differentiators"))
        result.technology_stack = self._ensure_list(extracted.get("technology_stack"))
        result.certifications = self._ensure_list(extracted.get("certifications"))
        result.partnerships = self._ensure_list(extracted.get("partnerships"))

    def _ensure_list(self, value: Any) -> List[str]:
        """Ensure value is a list of strings"""
        if isinstance(value, list):
            return [str(v).strip() for v in value if v]
        return []

    def _calculate_confidence(self, result: ScrapedCompanyData) -> float:
        """Calculate confidence score based on data completeness"""
        score = 0.0
        weights = {
            "company_overview": 0.20,
            "services": 0.15,
            "products": 0.10,
            "industry": 0.15,
            "contact_email": 0.10,
            "contact_phone": 0.05,
            "key_differentiators": 0.10,
            "target_customers": 0.10,
            "sources_scraped": 0.05,
        }

        if result.company_overview and len(result.company_overview) > 50:
            score += weights["company_overview"]

        if result.services and len(result.services) > 0:
            score += weights["services"]

        if result.products and len(result.products) > 0:
            score += weights["products"]

        if result.industry:
            score += weights["industry"]

        if result.contact_email and "@" in result.contact_email:
            score += weights["contact_email"]

        if result.contact_phone:
            score += weights["contact_phone"]

        if result.key_differentiators and len(result.key_differentiators) > 0:
            score += weights["key_differentiators"]

        if result.target_customers:
            score += weights["target_customers"]

        if result.sources_scraped and len(result.sources_scraped) >= 2:
            score += weights["sources_scraped"]

        return min(score, 1.0)

    def get_metrics(self) -> Dict[str, Any]:
        """Get scraping metrics for monitoring"""
        total = self.metrics["total_attempts"]
        if total == 0:
            success_rate = 0.0
        else:
            success_rate = self.metrics["successful_scrapes"] / total

        return {
            **self.metrics,
            "success_rate": success_rate,
        }


# Utility function for testing
async def test_scraper(url: str, company_name: str = "") -> None:
    """Test function for manual validation"""
    scraper = CompanyScraperService()

    if not scraper.is_enabled():
        print("Scraper not enabled - check FIRECRAWL_API_KEY")
        return

    result = await scraper.scrape_company(url, company_name)

    print(f"\n=== SCRAPE RESULTS FOR {url} ===")
    print(f"Success: {result.scrape_success}")
    print(f"Confidence: {result.confidence_score:.2f}")
    print(f"Sources: {result.sources_scraped}")
    print(f"Errors: {result.scrape_errors}")
    print(f"\nCompany: {result.company_name}")
    print(f"Overview: {result.company_overview[:200]}..." if result.company_overview else "Overview: N/A")
    print(f"Industry: {result.industry}")
    print(f"Services: {result.services[:5]}" if result.services else "Services: N/A")
    print(f"Products: {result.products[:5]}" if result.products else "Products: N/A")
