from typing import Dict, Any, List
from datetime import datetime
import re
import json


def format_phone_number(phone: str) -> str:
    """
    Format phone number to E.164 format
    Example: 5551234567 -> +15551234567
    """
    if not phone:
        return None
    
    # Remove all non-digit characters
    digits = re.sub(r'\D', '', phone)
    
    # Add +1 if not present (assuming US numbers)
    if not digits.startswith('1') and len(digits) == 10:
        digits = '1' + digits
    
    return '+' + digits


def validate_email(email: str) -> bool:
    """Validate email format"""
    if not email:
        return False
    
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename for safe filesystem use
    """
    # Remove or replace invalid characters
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    
    # Limit length
    max_length = 200
    if len(filename) > max_length:
        name, ext = filename.rsplit('.', 1) if '.' in filename else (filename, '')
        filename = name[:max_length - len(ext) - 1] + '.' + ext if ext else name[:max_length]
    
    return filename


def format_duration(seconds: int) -> str:
    """
    Format duration in seconds to human-readable format
    Example: 125 -> "2m 5s"
    """
    if not seconds:
        return "0s"
    
    minutes = seconds // 60
    remaining_seconds = seconds % 60
    
    if minutes > 0:
        return f"{minutes}m {remaining_seconds}s"
    else:
        return f"{remaining_seconds}s"


def truncate_text(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """
    Truncate text to specified length
    """
    if not text or len(text) <= max_length:
        return text
    
    return text[:max_length - len(suffix)] + suffix


def extract_first_name(full_name: str) -> str:
    """
    Extract first name from full name
    """
    if not full_name:
        return ""
    
    return full_name.split()[0] if full_name.split() else full_name


def calculate_score(metrics: Dict[str, Any]) -> float:
    """
    Calculate a composite score based on various metrics
    Used for lead scoring
    """
    score = 0.0
    
    # Sentiment score (0-40 points)
    sentiment_map = {"positive": 40, "neutral": 20, "negative": 0}
    score += sentiment_map.get(metrics.get("sentiment", "neutral"), 20)
    
    # Interest level (0-30 points)
    interest_map = {"high": 30, "medium": 20, "low": 10, "none": 0}
    score += interest_map.get(metrics.get("interest_level", "medium"), 20)
    
    # Demo requested (0-30 points)
    if metrics.get("demo_requested", False):
        score += 30
    
    # Normalize to 0-1
    return round(score / 100, 2)


def format_currency(amount: float, currency: str = "USD") -> str:
    """
    Format amount as currency
    """
    if currency == "USD":
        return f"${amount:,.2f}"
    else:
        return f"{amount:,.2f} {currency}"


def parse_json_safely(json_str: str, default: Any = None) -> Any:
    """
    Safely parse JSON string
    """
    try:
        return json.loads(json_str)
    except (json.JSONDecodeError, TypeError):
        return default


def merge_dicts(*dicts: Dict) -> Dict:
    """
    Merge multiple dictionaries
    """
    result = {}
    for d in dicts:
        if d:
            result.update(d)
    return result


def chunk_list(lst: List, chunk_size: int) -> List[List]:
    """
    Split list into chunks
    """
    return [lst[i:i + chunk_size] for i in range(0, len(lst), chunk_size)]


def get_status_color(status: str) -> str:
    """
    Get color code for status
    """
    status_colors = {
        "new": "#A2A7AF",
        "data_packet_created": "#2B8AFF",
        "calling": "#9E5AFF",
        "call_completed": "#41FFFF",
        "pdf_generated": "#FF9500",
        "email_sent": "#41FFFF",
        "demo_booked": "#00FF88",
        "closed_won": "#00FF88",
        "closed_lost": "#FF244E"
    }
    return status_colors.get(status, "#A2A7AF")


def calculate_conversion_rate(numerator: int, denominator: int) -> float:
    """
    Calculate conversion rate as percentage
    """
    if denominator == 0:
        return 0.0
    return round((numerator / denominator) * 100, 2)


def format_timestamp(dt: datetime, format: str = "%Y-%m-%d %H:%M:%S") -> str:
    """
    Format datetime to string
    """
    if not dt:
        return ""
    return dt.strftime(format)


def days_between(start: datetime, end: datetime) -> int:
    """
    Calculate days between two dates
    """
    if not start or not end:
        return 0
    return (end - start).days


def is_business_hours(dt: datetime = None) -> bool:
    """
    Check if given datetime is within business hours (9 AM - 5 PM EST, Mon-Fri)
    """
    if dt is None:
        dt = datetime.utcnow()
    
    # Check if weekend
    if dt.weekday() >= 5:  # Saturday = 5, Sunday = 6
        return False
    
    # Check if within business hours (assuming UTC time)
    hour = dt.hour
    return 14 <= hour <= 22  # 9 AM - 5 PM EST in UTC


def generate_unique_id(prefix: str = "") -> str:
    """
    Generate a unique ID with optional prefix
    """
    import uuid
    unique_id = str(uuid.uuid4())[:8]
    return f"{prefix}_{unique_id}" if prefix else unique_id