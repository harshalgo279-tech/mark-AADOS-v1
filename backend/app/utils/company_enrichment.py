# backend/app/utils/company_enrichment.py

import re
import httpx
from urllib.parse import quote


def _extract_meta_description(html: str) -> str | None:
    # <meta name="description" content="...">
    m = re.search(
        r'<meta\s+name=["\']description["\']\s+content=["\']([^"\']+)["\']',
        html,
        flags=re.IGNORECASE,
    )
    if m:
        return m.group(1).strip()

    # <meta property="og:description" content="...">
    m2 = re.search(
        r'<meta\s+property=["\']og:description["\']\s+content=["\']([^"\']+)["\']',
        html,
        flags=re.IGNORECASE,
    )
    if m2:
        return m2.group(1).strip()

    return None


async def get_company_description(company_name: str, website: str | None = None) -> str | None:
    """
    "Websearch-like" enrichment without paid APIs:
    1) Try the company website meta description
    2) Fallback to Wikipedia summary
    """
    company_name = (company_name or "").strip()
    website = (website or "").strip() or None

    # 1) Website meta description
    if website:
        try:
            url = website
            if not url.startswith("http"):
                url = "https://" + url

            async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
                resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
                if resp.status_code == 200 and resp.text:
                    desc = _extract_meta_description(resp.text)
                    if desc:
                        return desc
        except Exception:
            pass

    # 2) Wikipedia summary fallback
    try:
        title = quote(company_name.replace(" ", "_"))
        wiki_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            resp = await client.get(wiki_url, headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code == 200:
                data = resp.json()
                extract = (data.get("extract") or "").strip()
                if extract:
                    return extract
    except Exception:
        pass

    return None
