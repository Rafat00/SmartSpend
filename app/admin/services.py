"""Statistics for the admin dashboard and system page.

Privacy: only counts and non-financial metadata are returned. Individual expense
amounts, descriptions and stores are never exposed to the admin pages.
"""
import platform
import time
from datetime import date, datetime, timedelta, timezone

import flask
from importlib.metadata import version as pkg_version
from sqlalchemy import func, text

from app import monitoring
from app.extensions import db
from app.models import ActivityLog, Budget, Category, Expense, ROLE_ADMIN, User
from app.utils import add_months


def _month_labels(n: int):
    first = add_months(date.today().replace(day=1), -(n - 1))
    return [add_months(first, i) for i in range(n)]


def overview_counts() -> dict:
    now = datetime.now(timezone.utc)
    total_users = db.session.query(func.count(User.id)).scalar()
    active = db.session.query(func.count(User.id)).filter(User.is_active.is_(True)).scalar()
    return {
        "total_users": total_users,
        "active_users": active,
        "inactive_users": total_users - active,
        "admins": db.session.query(func.count(User.id)).filter(User.role == ROLE_ADMIN).scalar(),
        "new_users_30d": db.session.query(func.count(User.id)).filter(User.created_at >= now - timedelta(days=30)).scalar(),
        "total_expenses": db.session.query(func.count(Expense.id)).scalar(),
        "expenses_30d": db.session.query(func.count(Expense.id)).filter(Expense.date >= date.today() - timedelta(days=30)).scalar(),
        "total_budgets": db.session.query(func.count(Budget.id)).scalar(),
        "total_categories": db.session.query(func.count(Category.id)).scalar(),
        "active_categories": db.session.query(func.count(Category.id)).filter(Category.is_active.is_(True)).scalar(),
    }


def chart_payload() -> dict:
    """Data for the four admin charts (counts only)."""
    months = _month_labels(12)
    labels = [m.strftime("%b %Y") for m in months]
    index = {(m.year, m.month): i for i, m in enumerate(months)}

    # 1. expense records per month (by expense date)
    expense_counts = [0] * 12
    year, month = func.extract("year", Expense.date), func.extract("month", Expense.date)
    for y, m, c in (
        db.session.query(year, month, func.count(Expense.id))
        .filter(Expense.date >= months[0]).group_by(year, month)
    ):
        i = index.get((int(y), int(m)))
        if i is not None:
            expense_counts[i] = c

    # 2. new registrations per month
    signups = [0] * 12
    uy, um = func.extract("year", User.created_at), func.extract("month", User.created_at)
    for y, m, c in db.session.query(uy, um, func.count(User.id)).group_by(uy, um):
        i = index.get((int(y), int(m)))
        if i is not None:
            signups[i] = c

    # 3. distinct users logging in per day (last 14 days)
    days = [date.today() - timedelta(days=13 - i) for i in range(14)]
    since = datetime.now(timezone.utc) - timedelta(days=15)
    day_col = func.date(ActivityLog.created_at)
    per_day: dict[str, set] = {}
    for d, actor in (
        db.session.query(day_col, ActivityLog.actor_id)
        .filter(ActivityLog.action == "user_login", ActivityLog.created_at >= since).distinct()
    ):
        per_day.setdefault(str(d), set()).add(actor)
    logins = [len(per_day.get(d.isoformat(), ())) for d in days]

    # 4. expense records by category (count)
    cat_rows = (
        db.session.query(Expense.category, func.count(Expense.id))
        .group_by(Expense.category).order_by(func.count(Expense.id).desc()).limit(8).all()
    )
    return {
        "months": labels, "expense_counts": expense_counts, "signups": signups,
        "days": [d.strftime("%d %b") for d in days], "logins": logins,
        "categories": [c for c, _ in cat_rows], "category_counts": [n for _, n in cat_rows],
    }


def recent_activity(limit: int = 10):
    return ActivityLog.query.order_by(ActivityLog.created_at.desc(), ActivityLog.id.desc()).limit(limit).all()


def database_health() -> dict:
    start = time.perf_counter()
    try:
        db.session.execute(text("SELECT 1"))
        latency = round((time.perf_counter() - start) * 1000, 1)
        result = {"ok": True, "latency_ms": latency, "engine": db.engine.dialect.name, "size": None}
        if db.engine.dialect.name == "postgresql":
            size = db.session.execute(text("SELECT pg_size_pretty(pg_database_size(current_database()))")).scalar()
            result["size"] = size
        return result
    except Exception:  # noqa: BLE001 - never leak connection strings / driver errors
        db.session.rollback()
        return {"ok": False, "latency_ms": None, "engine": None, "size": None}


def ai_status(client) -> dict:
    """AI availability WITHOUT exposing the key. Only booleans and a host name."""
    snap = monitoring.snapshot()
    if not client.configured:
        state, label = "unconfigured", "Not configured (rule-based fallbacks active)"
    elif snap["ai_last_failure"] and (not snap["ai_last_success"] or snap["ai_last_failure"] > snap["ai_last_success"]):
        state, label = "degraded", "Configured, but the most recent request failed"
    else:
        state, label = "ok", "Configured and working" if snap["ai_last_success"] else "Configured (no requests yet since restart)"
    host = client.base_url.split("//")[-1].split("/")[0] if client.base_url else ""
    return {"state": state, "label": label, "model": client.model if client.configured else None,
            "provider_host": host, **snap}


def runtime_info() -> dict:
    snap = monitoring.snapshot()
    uptime = datetime.now(timezone.utc) - snap["started_at"]
    return {
        "python": platform.python_version(),
        "flask": pkg_version("flask"),
        "uptime": str(timedelta(seconds=int(uptime.total_seconds()))),
        "debug": flask.current_app.debug,
        "server_errors": snap["server_errors"],
        "last_server_error": snap["last_server_error"],
    }
