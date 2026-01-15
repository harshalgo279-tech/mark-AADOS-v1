# backend/app/services/playwright_scraper_service.py
"""
Playwright-based Web Scraping Service

Handles dynamic content and JavaScript-rendered pages for comprehensive
company data extraction.

Features:
- Headless browser automation
- JavaScript rendering support
- Multiple page scraping
- Structured data extraction via LLM
- Error handling for blocked/restricted sites
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse
from dataclasses import dataclass, asdict
from datetime import datetime

from app.services.openai_service import OpenAIService
from app.utils.logger import logger

# Try to import playwright
try:
    from playwright.async_api import async_playwright, Browser, Page, TimeoutError as PlaywrightTimeout
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    logger.warning("[PlaywrightScraper] playwright not installed. Run: pip install playwright && playwright install chromium")


@dataclass
class PlaywrightScrapedData:
    """Structured company data extracted from website using Playwright"""
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
    social_links: Dict[str, str] = None
    raw_text: str = ""
    scrape_success: bool = False
    scrape_errors: List[str] = None
    sources_scraped: List[str] = None
    confidence_score: float = 0.0
    scrape_duration_ms: int = 0

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
        if self.social_links is None:
            self.social_links = {}
        if self.scrape_errors is None:
            self.scrape_errors = []
        if self.sources_scraped is None:
            self.sources_scraped = []

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class PlaywrightScraperService:
    """
    Playwright-based web scraping service for comprehensive company data extraction.

    Features:
    - Headless Chromium browser
    - JavaScript rendering
    - Multi-page scraping
    - Smart content extraction
    - LLM-powered data structuring
    """

    def __init__(self):
        self.openai = OpenAIService()
        self.enabled = PLAYWRIGHT_AVAILABLE

        # Target pages to scrape
        self.target_paths = [
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
            "/team",
            "/careers",
        ]

        # Maximum pages to scrape per company
        self.max_pages = 6

        # Timeouts
        self.page_timeout_ms = 30000  # 30 seconds per page
        self.navigation_timeout_ms = 20000  # 20 seconds for navigation

        # Metrics tracking
        self.metrics = {
            "total_scrapes": 0,
            "successful_scrapes": 0,
            "failed_scrapes": 0,
            "pages_scraped": 0,
        }

    def is_enabled(self) -> bool:
        return self.enabled

    def _normalize_url(self, url: str) -> str:
        """Normalize URL format"""
        url = (url or "").strip()
        if not url:
            return ""
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        return url.rstrip("/")

    def _get_base_url(self, url: str) -> str:
        """Extract base URL (scheme + domain)"""
        try:
            parsed = urlparse(url)
            if parsed.scheme and parsed.netloc:
                return f"{parsed.scheme}://{parsed.netloc}"
        except Exception:
            pass
        return ""

    def _build_urls_to_scrape(self, company_url: str) -> List[str]:
        """Build list of URLs to scrape"""
        company_url = self._normalize_url(company_url)
        base = self._get_base_url(company_url)

        if not base:
            return [company_url] if company_url else []

        urls = []
        seen = set()

        for path in self.target_paths:
            full_url = urljoin(base + "/", path.lstrip("/"))
            if full_url not in seen:
                seen.add(full_url)
                urls.append(full_url)

        return urls[:self.max_pages]

    async def scrape_company(
        self,
        company_url: str,
        company_name: str = "",
    ) -> PlaywrightScrapedData:
        """
        Main method to scrape comprehensive company data using Playwright.

        Args:
            company_url: Company website URL
            company_name: Optional company name for context

        Returns:
            PlaywrightScrapedData with all extracted information
        """
        start_time = datetime.utcnow()
        self.metrics["total_scrapes"] += 1

        result = PlaywrightScrapedData(company_name=company_name)

        if not self.enabled:
            result.scrape_errors.append("Playwright not available. Install with: pip install playwright && playwright install chromium")
            logger.error("[PlaywrightScraper] Playwright not installed")
            return result

        company_url = self._normalize_url(company_url)
        if not company_url:
            result.scrape_errors.append("No valid company URL provided")
            return result

        urls = self._build_urls_to_scrape(company_url)
        if not urls:
            result.scrape_errors.append("Could not build URLs from company URL")
            return result

        # Scrape using Playwright
        combined_text = await self._scrape_with_playwright(urls, result)

        if not combined_text:
            self.metrics["failed_scrapes"] += 1
            result.scrape_errors.append("No content extracted from website")
            return result

        result.raw_text = combined_text

        # Extract structured data using LLM
        extracted = await self._extract_structured_data(
            text_content=combined_text,
            company_name=company_name,
            company_url=company_url,
        )

        # Update result with extracted data
        self._update_result_from_extraction(result, extracted)

        # Calculate confidence score
        result.confidence_score = self._calculate_confidence(result)
        result.scrape_success = result.confidence_score > 0.3

        # Calculate duration
        end_time = datetime.utcnow()
        result.scrape_duration_ms = int((end_time - start_time).total_seconds() * 1000)

        if result.scrape_success:
            self.metrics["successful_scrapes"] += 1
        else:
            self.metrics["failed_scrapes"] += 1

        logger.info(
            f"[PlaywrightScraper] Completed scrape for {company_url} - "
            f"success={result.scrape_success} confidence={result.confidence_score:.2f} "
            f"duration={result.scrape_duration_ms}ms"
        )

        return result

    async def _scrape_with_playwright(
        self,
        urls: List[str],
        result: PlaywrightScrapedData,
    ) -> str:
        """Scrape multiple pages using Playwright browser"""
        all_content = []

        try:
            async with async_playwright() as p:
                # Launch headless browser
                browser = await p.chromium.launch(
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-gpu",
                    ]
                )

                # Create context with realistic browser settings
                context = await browser.new_context(
                    viewport={"width": 1920, "height": 1080},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    locale="en-US",
                )

                # Set default timeout
                context.set_default_timeout(self.page_timeout_ms)

                for url in urls:
                    try:
                        page = await context.new_page()

                        # Navigate to page
                        try:
                            response = await page.goto(
                                url,
                                wait_until="domcontentloaded",
                                timeout=self.navigation_timeout_ms,
                            )

                            if response and response.status >= 400:
                                result.scrape_errors.append(f"HTTP {response.status} for {url}")
                                await page.close()
                                continue

                        except PlaywrightTimeout:
                            result.scrape_errors.append(f"Navigation timeout for {url}")
                            await page.close()
                            continue
                        except Exception as nav_error:
                            result.scrape_errors.append(f"Navigation error for {url}: {str(nav_error)[:100]}")
                            await page.close()
                            continue

                        # Wait for content to load
                        try:
                            await page.wait_for_load_state("networkidle", timeout=10000)
                        except Exception:
                            # Continue anyway - some content may be loaded
                            pass

                        # Extract text content
                        text_content = await self._extract_page_content(page, url)

                        if text_content:
                            all_content.append(f"=== SOURCE: {url} ===\n\n{text_content}")
                            result.sources_scraped.append(url)
                            self.metrics["pages_scraped"] += 1

                        # Extract social links from homepage
                        if url == urls[0]:
                            social = await self._extract_social_links(page)
                            if social:
                                result.social_links = social

                        await page.close()

                    except Exception as e:
                        error_msg = str(e)[:150]
                        result.scrape_errors.append(f"Error scraping {url}: {error_msg}")
                        logger.error(f"[PlaywrightScraper] Page scrape error for {url}: {e}")

                await browser.close()

        except Exception as e:
            result.scrape_errors.append(f"Browser error: {str(e)[:150]}")
            logger.error(f"[PlaywrightScraper] Browser launch error: {e}")

        return "\n\n---\n\n".join(all_content)

    async def _extract_page_content(self, page: Page, url: str) -> str:
        """Extract meaningful text content from a page"""
        try:
            # Get main content - try multiple selectors
            content_selectors = [
                "main",
                "article",
                "#content",
                ".content",
                "#main-content",
                ".main-content",
                "[role='main']",
                "body",
            ]

            text_parts = []

            # Get page title
            title = await page.title()
            if title:
                text_parts.append(f"Page Title: {title}")

            # Get meta description
            meta_desc = await page.evaluate("""
                () => {
                    const meta = document.querySelector('meta[name="description"]');
                    return meta ? meta.getAttribute('content') : '';
                }
            """)
            if meta_desc:
                text_parts.append(f"Meta Description: {meta_desc}")

            # Get main content
            for selector in content_selectors:
                try:
                    element = await page.query_selector(selector)
                    if element:
                        text = await element.inner_text()
                        if text and len(text.strip()) > 100:
                            # Clean up the text
                            cleaned = self._clean_text(text)
                            if cleaned:
                                text_parts.append(cleaned)
                                break
                except Exception:
                    continue

            # If no main content found, get body text
            if len(text_parts) <= 2:
                try:
                    body_text = await page.evaluate("""
                        () => {
                            // Remove script and style elements
                            const clone = document.body.cloneNode(true);
                            clone.querySelectorAll('script, style, nav, footer, header, iframe, noscript').forEach(el => el.remove());
                            return clone.innerText;
                        }
                    """)
                    if body_text:
                        cleaned = self._clean_text(body_text)
                        if cleaned:
                            text_parts.append(cleaned)
                except Exception:
                    pass

            # Get structured data if available
            structured = await self._extract_structured_json_ld(page)
            if structured:
                text_parts.append(f"Structured Data: {structured}")

            combined = "\n\n".join(text_parts)

            # Limit content length
            if len(combined) > 15000:
                combined = combined[:15000] + "\n\n[TRUNCATED]"

            return combined

        except Exception as e:
            logger.error(f"[PlaywrightScraper] Content extraction error: {e}")
            return ""

    async def _extract_structured_json_ld(self, page: Page) -> str:
        """Extract JSON-LD structured data from page"""
        try:
            json_ld = await page.evaluate("""
                () => {
                    const scripts = document.querySelectorAll('script[type="application/ld+json"]');
                    const data = [];
                    scripts.forEach(script => {
                        try {
                            const parsed = JSON.parse(script.textContent);
                            if (parsed['@type'] && ['Organization', 'Corporation', 'LocalBusiness', 'Company'].includes(parsed['@type'])) {
                                data.push(parsed);
                            }
                        } catch (e) {}
                    });
                    return data.length > 0 ? JSON.stringify(data[0]) : '';
                }
            """)
            return json_ld
        except Exception:
            return ""

    async def _extract_social_links(self, page: Page) -> Dict[str, str]:
        """Extract social media links from page"""
        try:
            social = await page.evaluate("""
                () => {
                    const links = {};
                    const socialPatterns = {
                        'linkedin': /linkedin\.com/i,
                        'twitter': /twitter\.com|x\.com/i,
                        'facebook': /facebook\.com/i,
                        'instagram': /instagram\.com/i,
                        'youtube': /youtube\.com/i,
                        'github': /github\.com/i,
                    };

                    document.querySelectorAll('a[href]').forEach(a => {
                        const href = a.getAttribute('href');
                        for (const [name, pattern] of Object.entries(socialPatterns)) {
                            if (pattern.test(href) && !links[name]) {
                                links[name] = href;
                            }
                        }
                    });

                    return links;
                }
            """)
            return social if social else {}
        except Exception:
            return {}

    def _clean_text(self, text: str) -> str:
        """Clean and normalize extracted text"""
        if not text:
            return ""

        # Remove excessive whitespace
        text = re.sub(r'\s+', ' ', text)

        # Remove common noise patterns
        noise_patterns = [
            r'Cookie\s*(Policy|Settings|Preferences)',
            r'Accept\s*(All\s*)?Cookies',
            r'Privacy\s*Policy',
            r'Terms\s*(of\s*Service|and\s*Conditions)',
            r'Subscribe\s*to\s*our\s*newsletter',
            r'Sign\s*up\s*for\s*updates',
        ]

        for pattern in noise_patterns:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE)

        return text.strip()

    async def _extract_structured_data(
        self,
        text_content: str,
        company_name: str,
        company_url: str,
    ) -> Dict[str, Any]:
        """Use LLM to extract structured company data"""

        # Truncate if too long
        if len(text_content) > 25000:
            text_content = text_content[:25000] + "\n\n[TRUNCATED]"

        prompt = f"""Analyze this company website content and extract business information.

COMPANY NAME (if known): {company_name or "[Unknown]"}
COMPANY WEBSITE: {company_url}

WEBSITE CONTENT:
{text_content}

Extract the following and return as JSON only:

{{
    "company_name": "Official company name",
    "company_overview": "2-4 sentence description of what the company does",
    "services": ["service 1", "service 2", ...],
    "products": ["product 1", "product 2", ...],
    "industry": "Primary industry (Technology, Healthcare, Finance, etc.)",
    "sector": "Specific sector (SaaS, Medical Devices, etc.)",
    "contact_email": "main contact email if found",
    "contact_phone": "main phone number if found",
    "headquarters_location": "city, state/country",
    "founded_year": "year founded if mentioned",
    "company_size": "employee count or range",
    "key_differentiators": ["unique selling point 1", ...],
    "target_customers": "who they sell to",
    "technology_stack": ["technology 1", ...],
    "certifications": ["certification 1", ...],
    "partnerships": ["partner 1", ...]
}}

RULES:
- Extract only explicitly stated or clearly implied information
- Use "" for text fields not found
- Use [] for list fields not found
- Do NOT hallucinate or make up information
- Return ONLY valid JSON
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

            return self._safe_parse_json(response)

        except Exception as e:
            logger.error(f"[PlaywrightScraper] LLM extraction error: {e}")
            return {}

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

        # Find JSON boundaries
        if "{" in raw and "}" in raw:
            start = raw.find("{")
            end = raw.rfind("}") + 1
            raw = raw[start:end]

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}

    def _update_result_from_extraction(
        self,
        result: PlaywrightScrapedData,
        extracted: Dict[str, Any],
    ) -> None:
        """Update result with extracted data"""
        if not extracted:
            return

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

    def _calculate_confidence(self, result: PlaywrightScrapedData) -> float:
        """Calculate confidence based on data completeness"""
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
        """Get scraping metrics"""
        total = self.metrics["total_scrapes"]
        return {
            **self.metrics,
            "success_rate": self.metrics["successful_scrapes"] / total if total > 0 else 0,
        }


# Synchronous wrapper for non-async contexts
def scrape_company_sync(company_url: str, company_name: str = "") -> PlaywrightScrapedData:
    """Synchronous wrapper for company scraping"""
    scraper = PlaywrightScraperService()
    return asyncio.run(scraper.scrape_company(company_url, company_name))
