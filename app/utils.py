"""Small helper functions used across the app."""
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from urllib.parse import urljoin, urlparse

from flask import request

from app.constants import MAX_AMOUNT


def is_safe_url(target: str) -> bool:
    """Only allow redirects back to our own site (prevents open-redirect attacks)."""
    ref = urlparse(request.host_url)
    test = urlparse(urljoin(request.host_url, target))
    return test.scheme in ("http", "https") and ref.netloc == test.netloc


def parse_amount(raw) -> Decimal:
    """Convert user text to a positive Decimal with 2 places or raise ValueError."""
    text = (raw or "").strip().replace(",", "")
    if not text:
        raise ValueError("Amount is required.")
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValueError("Amount must be a valid number.") from None
    if not value.is_finite():
        raise ValueError("Amount must be a valid number.")
    if value <= 0:
        raise ValueError("Amount must be greater than zero.")
    if value > MAX_AMOUNT:
        raise ValueError("Amount is too large. Please check the number.")
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def parse_date(raw, field: str = "Date") -> date:
    """Parse YYYY-MM-DD or raise ValueError with a friendly message."""
    text = (raw or "").strip()
    if not text:
        raise ValueError(f"{field} is required.")
    try:
        value = datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError(f"{field} is not a valid date. Use the format YYYY-MM-DD.") from None
    if value < date(2000, 1, 1):
        raise ValueError(f"{field} is too far in the past.")
    if value > date.today() + timedelta(days=365):
        raise ValueError(f"{field} is too far in the future.")
    return value


def month_range(year: int, month: int):
    """Return (first day of month, first day of NEXT month). End is exclusive."""
    start = date(year, month, 1)
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return start, end


def add_months(d: date, n: int) -> date:
    """Return the first day of the month that is n months after d's month."""
    index = d.year * 12 + (d.month - 1) + n
    return date(index // 12, index % 12 + 1, 1)


def format_money(value) -> str:
    """Format a number as Bangladeshi Taka, e.g. ৳25,000 or ৳250.50."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "৳0"
    sign = "-" if v < 0 else ""
    v = abs(v)
    if abs(v - round(v)) < 0.005:
        return f"{sign}৳{v:,.0f}"
    return f"{sign}৳{v:,.2f}"


def escape_like(text: str) -> str:
    """Escape % and _ so user search text is matched literally in LIKE queries."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
