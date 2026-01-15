# backend/app/utils/normalize.py
import re
from typing import Optional

def normalize_industry(industry: Optional[str]) -> Optional[str]:
    if not industry:
        return None
    s = industry.strip()
    if not s:
        return None

    # collapse spaces, unify case for comparisons
    key = re.sub(r"\s+", " ", s).lower()

    # common mappings
    if key in {"saas", "saas ", "software as a service", "software-as-a-service"}:
        return "SaaS"
    if key in {"it", "information technology"}:
        return "IT"
    if key in {"ai", "artificial intelligence"}:
        return "AI"

    # Title case default, but keep acronyms readable
    # e.g. "healthcare" -> "Healthcare"
    return s[:1].upper() + s[1:]
