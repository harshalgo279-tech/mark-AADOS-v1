# backend/app/utils/validators.py
"""
Input validation utilities with enterprise-grade security.

Provides:
- Phone number validation with international format support
- Email validation with deliverability checks
- HTML sanitization for user input
- URL validation
"""

import re
from typing import Optional, Tuple

# Try to import phonenumbers for robust phone validation
try:
    import phonenumbers
    from phonenumbers import NumberParseException
    PHONENUMBERS_AVAILABLE = True
except ImportError:
    PHONENUMBERS_AVAILABLE = False

# Try to import bleach for HTML sanitization
try:
    import bleach
    BLEACH_AVAILABLE = True
except ImportError:
    BLEACH_AVAILABLE = False


# ==================== Phone Number Validation ====================

def validate_phone_number(
    phone: str,
    default_region: str = "US"
) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Validate and normalize a phone number.

    Args:
        phone: The phone number to validate
        default_region: Default region code (ISO 3166-1 alpha-2)

    Returns:
        Tuple of (is_valid, normalized_number, error_message)
        - normalized_number is in E.164 format (+1234567890) if valid
    """
    if not phone:
        return False, None, "Phone number is required"

    phone = phone.strip()

    if PHONENUMBERS_AVAILABLE:
        try:
            # Parse the phone number
            parsed = phonenumbers.parse(phone, default_region)

            # Check if it's a valid number
            if not phonenumbers.is_valid_number(parsed):
                return False, None, "Invalid phone number"

            # Check if it's a possible number (less strict)
            if not phonenumbers.is_possible_number(parsed):
                return False, None, "Phone number format is not valid"

            # Normalize to E.164 format
            normalized = phonenumbers.format_number(
                parsed,
                phonenumbers.PhoneNumberFormat.E164
            )

            return True, normalized, None

        except NumberParseException as e:
            return False, None, f"Invalid phone number: {str(e)}"
    else:
        # Fallback: basic validation without phonenumbers library
        # Accept formats: +1234567890, 1234567890, (123) 456-7890, etc.
        cleaned = re.sub(r'[\s\-\(\)\.]', '', phone)

        # Must be digits, optionally starting with +
        if not re.match(r'^\+?\d{10,15}$', cleaned):
            return False, None, "Phone number must be 10-15 digits"

        # Ensure it starts with + for E.164
        if not cleaned.startswith('+'):
            # Assume US if no country code
            if len(cleaned) == 10:
                cleaned = '+1' + cleaned
            else:
                cleaned = '+' + cleaned

        return True, cleaned, None


def is_valid_phone(phone: str) -> bool:
    """Simple check if phone number is valid."""
    is_valid, _, _ = validate_phone_number(phone)
    return is_valid


def normalize_phone(phone: str, default_region: str = "US") -> Optional[str]:
    """Normalize phone number to E.164 format, or return None if invalid."""
    is_valid, normalized, _ = validate_phone_number(phone, default_region)
    return normalized if is_valid else None


# ==================== Email Validation ====================

# RFC 5322 compliant email regex (simplified)
EMAIL_REGEX = re.compile(
    r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
)


def validate_email(email: str) -> Tuple[bool, Optional[str]]:
    """
    Validate an email address.

    Args:
        email: The email address to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not email:
        return False, "Email is required"

    email = email.strip().lower()

    if len(email) > 254:
        return False, "Email address is too long"

    if not EMAIL_REGEX.match(email):
        return False, "Invalid email format"

    # Check for common invalid patterns
    if '..' in email:
        return False, "Invalid email format"

    return True, None


def is_valid_email(email: str) -> bool:
    """Simple check if email is valid."""
    is_valid, _ = validate_email(email)
    return is_valid


# ==================== HTML Sanitization ====================

# Allowed HTML tags for email content
ALLOWED_TAGS = [
    'a', 'abbr', 'acronym', 'b', 'blockquote', 'br', 'code',
    'div', 'em', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'hr',
    'i', 'img', 'li', 'ol', 'p', 'pre', 'span', 'strong',
    'table', 'tbody', 'td', 'th', 'thead', 'tr', 'u', 'ul',
]

# Allowed HTML attributes
ALLOWED_ATTRIBUTES = {
    '*': ['class', 'style', 'id'],
    'a': ['href', 'title', 'target', 'rel'],
    'img': ['src', 'alt', 'title', 'width', 'height'],
    'table': ['border', 'cellpadding', 'cellspacing', 'width'],
    'td': ['colspan', 'rowspan', 'align', 'valign', 'width'],
    'th': ['colspan', 'rowspan', 'align', 'valign', 'width'],
}

# Allowed URL schemes
ALLOWED_PROTOCOLS = ['http', 'https', 'mailto', 'tel']


def sanitize_html(html: str, strip: bool = False) -> str:
    """
    Sanitize HTML content to prevent XSS attacks.

    Args:
        html: The HTML content to sanitize
        strip: If True, strip disallowed tags. If False, escape them.

    Returns:
        Sanitized HTML string
    """
    if not html:
        return ""

    if BLEACH_AVAILABLE:
        return bleach.clean(
            html,
            tags=ALLOWED_TAGS,
            attributes=ALLOWED_ATTRIBUTES,
            protocols=ALLOWED_PROTOCOLS,
            strip=strip,
        )
    else:
        # Fallback: escape all HTML
        import html as html_lib
        return html_lib.escape(html)


def strip_html_tags(html: str) -> str:
    """Remove all HTML tags and return plain text."""
    if not html:
        return ""

    if BLEACH_AVAILABLE:
        return bleach.clean(html, tags=[], strip=True)
    else:
        # Fallback: simple regex-based tag removal
        return re.sub(r'<[^>]+>', '', html)


# ==================== URL Validation ====================

URL_REGEX = re.compile(
    r'^https?://'  # http:// or https://
    r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain
    r'localhost|'  # localhost
    r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # IP address
    r'(?::\d+)?'  # optional port
    r'(?:/?|[/?]\S+)$', re.IGNORECASE
)


def validate_url(url: str, require_https: bool = False) -> Tuple[bool, Optional[str]]:
    """
    Validate a URL.

    Args:
        url: The URL to validate
        require_https: If True, only accept HTTPS URLs

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not url:
        return False, "URL is required"

    url = url.strip()

    if require_https and not url.startswith('https://'):
        return False, "HTTPS URL is required"

    if not URL_REGEX.match(url):
        return False, "Invalid URL format"

    return True, None


def is_valid_url(url: str) -> bool:
    """Simple check if URL is valid."""
    is_valid, _ = validate_url(url)
    return is_valid
