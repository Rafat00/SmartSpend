"""Category helpers shared by expenses, AI and the admin pages.

Categories live in the `categories` table (managed by admins). If the table is empty
(fresh test database, or before the migration seeded it) the built-in list from
app/constants.py is used, so nothing breaks.
"""
import re

from flask import g

from app.constants import CATEGORIES, CATEGORY_COLORS
from app.extensions import db
from app.models import Category

PROTECTED_CATEGORY = "Other"  # fallback category: cannot be renamed or deactivated
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 &/'\-]{0,48}[A-Za-z0-9]$|^[A-Za-z0-9]$")
COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def ensure_default_categories() -> None:
    """Insert the built-in categories if the table is empty (idempotent)."""
    if db.session.query(Category.id).first() is None:
        for name in CATEGORIES:
            db.session.add(Category(name=name, color=CATEGORY_COLORS.get(name, "#94a3b8")))
        db.session.commit()


def active_category_names() -> list[str]:
    names = [n for (n,) in db.session.query(Category.name).filter_by(is_active=True).order_by(Category.name)]
    return names or list(CATEGORIES)


def all_category_names() -> list[str]:
    """Active + deactivated: used for filters so old expenses stay searchable."""
    names = [n for (n,) in db.session.query(Category.name).order_by(Category.name)]
    return names or list(CATEGORIES)


def match_active(name: str) -> str | None:
    """Case-insensitive match against active categories; returns the canonical name."""
    lowered = (name or "").strip().lower()
    return next((c for c in active_category_names() if c.lower() == lowered), None)


def color_for(name: str) -> str:
    """Colour for a category name (cached per request)."""
    colors = getattr(g, "_category_colors", None)
    if colors is None:
        colors = {n: c for n, c in db.session.query(Category.name, Category.color)}
        g._category_colors = colors
    return colors.get(name) or CATEGORY_COLORS.get(name) or CATEGORY_COLORS["Other"]


def validate_category_fields(name: str, color: str) -> list[str]:
    errors = []
    if not name:
        errors.append("Category name is required.")
    elif len(name) > 50 or not NAME_RE.match(name):
        errors.append("Category name may only contain letters, numbers, spaces and & / ' - (max 50 characters).")
    if not COLOR_RE.match(color or ""):
        errors.append("Colour must look like #1a2b3c.")
    return errors
