"""All spending statistics. Every function takes user_id so queries are always
limited to ONE user's data.

Dates: ranges are [start, end) - "end" is exclusive.
"""
from collections import defaultdict
from datetime import date, timedelta

import pandas as pd
from sqlalchemy import desc, func

from app.extensions import db
from app.models import Budget, Expense
from app.utils import add_months, month_range


def _num(value) -> float:
    return round(float(value or 0), 2)


# ----------------------------------------------------------------- totals
def total_between(user_id, start=None, end=None) -> float:
    q = db.session.query(func.coalesce(func.sum(Expense.amount), 0)).filter(
        Expense.user_id == user_id
    )
    if start is not None:
        q = q.filter(Expense.date >= start)
    if end is not None:
        q = q.filter(Expense.date < end)
    return _num(q.scalar())


def count_between(user_id, start=None, end=None) -> int:
    q = db.session.query(func.count(Expense.id)).filter(Expense.user_id == user_id)
    if start is not None:
        q = q.filter(Expense.date >= start)
    if end is not None:
        q = q.filter(Expense.date < end)
    return int(q.scalar() or 0)


def dashboard_cards(user_id, today=None) -> dict:
    today = today or date.today()
    week_start = today - timedelta(days=today.weekday())  # Monday
    m_start, m_end = month_range(today.year, today.month)
    tomorrow = today + timedelta(days=1)
    return {
        "today": total_between(user_id, today, tomorrow),
        "week": total_between(user_id, week_start, tomorrow),
        "month": total_between(user_id, m_start, m_end),
        "total": total_between(user_id),
        "transactions": count_between(user_id),
    }


# ----------------------------------------------------------------- time series
def _daily_map(user_id, start, end) -> dict:
    rows = (
        db.session.query(Expense.date, func.sum(Expense.amount))
        .filter(Expense.user_id == user_id, Expense.date >= start, Expense.date < end)
        .group_by(Expense.date)
        .all()
    )
    return {d: _num(t) for d, t in rows}


def daily_series(user_id, days=30, today=None) -> list[dict]:
    today = today or date.today()
    start = today - timedelta(days=days - 1)
    data = _daily_map(user_id, start, today + timedelta(days=1))
    return [
        {"date": d.isoformat(), "label": d.strftime("%d %b"), "total": data.get(d, 0.0)}
        for d in (start + timedelta(days=i) for i in range(days))
    ]


def weekly_totals(user_id, weeks=8, today=None) -> list[dict]:
    today = today or date.today()
    this_week = today - timedelta(days=today.weekday())
    first = this_week - timedelta(days=7 * (weeks - 1))
    data = _daily_map(user_id, first, today + timedelta(days=1))
    buckets = defaultdict(float)
    for d, total in data.items():
        buckets[d - timedelta(days=d.weekday())] += total
    result = []
    for i in range(weeks):
        ws = first + timedelta(days=7 * i)
        result.append(
            {"label": ws.strftime("%d %b"), "week_start": ws.isoformat(), "total": round(buckets.get(ws, 0.0), 2)}
        )
    return result


def monthly_totals(user_id, months=6, today=None) -> list[dict]:
    today = today or date.today()
    first = add_months(today.replace(day=1), -(months - 1))
    end = month_range(today.year, today.month)[1]
    data = _daily_map(user_id, first, end)
    buckets = defaultdict(float)
    for d, total in data.items():
        buckets[(d.year, d.month)] += total
    result = []
    for i in range(months):
        m = add_months(first, i)
        result.append(
            {
                "label": m.strftime("%b %Y"),
                "year": m.year,
                "month": m.month,
                "total": round(buckets.get((m.year, m.month), 0.0), 2),
            }
        )
    return result


# ----------------------------------------------------------------- breakdowns
def category_breakdown(user_id, start=None, end=None) -> list[dict]:
    total_expr = func.sum(Expense.amount)
    q = db.session.query(Expense.category, total_expr, func.count(Expense.id)).filter(
        Expense.user_id == user_id
    )
    if start is not None:
        q = q.filter(Expense.date >= start)
    if end is not None:
        q = q.filter(Expense.date < end)
    rows = q.group_by(Expense.category).order_by(desc(total_expr)).all()
    return [{"category": c, "total": _num(t), "count": int(n)} for c, t, n in rows]


def top_stores(user_id, limit=5, start=None, end=None) -> list[dict]:
    total_expr = func.sum(Expense.amount)
    q = db.session.query(Expense.store, total_expr, func.count(Expense.id)).filter(
        Expense.user_id == user_id, Expense.store.isnot(None), Expense.store != ""
    )
    if start is not None:
        q = q.filter(Expense.date >= start)
    if end is not None:
        q = q.filter(Expense.date < end)
    rows = q.group_by(Expense.store).order_by(desc(total_expr)).limit(limit).all()
    return [{"store": s, "total": _num(t), "count": int(n)} for s, t, n in rows]


def category_comparison(user_id, today=None) -> list[dict]:
    """This month vs last month per category, with % change."""
    today = today or date.today()
    cs, ce = month_range(today.year, today.month)
    prev = add_months(today.replace(day=1), -1)
    ps, pe = month_range(prev.year, prev.month)
    cur = {r["category"]: r["total"] for r in category_breakdown(user_id, cs, ce)}
    old = {r["category"]: r["total"] for r in category_breakdown(user_id, ps, pe)}
    rows = []
    for cat in sorted(set(cur) | set(old), key=lambda c: -cur.get(c, 0.0)):
        c, p = cur.get(cat, 0.0), old.get(cat, 0.0)
        rows.append(
            {
                "category": cat,
                "current": c,
                "previous": p,
                "diff": round(c - p, 2),
                "change_pct": round((c - p) / p * 100, 1) if p > 0 else None,
            }
        )
    return rows


def largest_expenses(user_id, start, end, limit=5) -> list[dict]:
    rows = (
        Expense.query.filter(Expense.user_id == user_id, Expense.date >= start, Expense.date < end)
        .order_by(Expense.amount.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "name": e.expense_name,
            "amount": _num(e.amount),
            "category": e.category,
            "store": e.store or "",
            "date": e.date.isoformat(),
        }
        for e in rows
    ]


# ----------------------------------------------------------------- budget
def budget_status(user_id, year, month) -> dict:
    budget = Budget.query.filter_by(user_id=user_id, year=year, month=month).first()
    start, end = month_range(year, month)
    spent = total_between(user_id, start, end)
    if budget is None:
        return {
            "has_budget": False, "budget": 0.0, "spent": spent, "remaining": None,
            "percent": 0.0, "exceeded": False, "over_by": 0.0, "year": year, "month": month,
        }
    amount = _num(budget.amount)
    remaining = round(amount - spent, 2)
    percent = round(spent / amount * 100, 1) if amount > 0 else 0.0
    return {
        "has_budget": True,
        "budget": amount,
        "spent": spent,
        "remaining": remaining,
        "percent": percent,
        "exceeded": spent > amount,
        "over_by": round(max(spent - amount, 0.0), 2),
        "year": year,
        "month": month,
    }


# ----------------------------------------------------------------- chart payload
def chart_payload(user_id, today=None) -> dict:
    today = today or date.today()
    m_start, m_end = month_range(today.year, today.month)
    categories = category_breakdown(user_id, m_start, m_end)
    scope = today.strftime("%B %Y")
    if not categories:
        categories = category_breakdown(user_id)
        scope = "All time"
    monthly = monthly_totals(user_id, 6, today)
    stores = top_stores(user_id, 5)
    daily = daily_series(user_id, 30, today)
    return {
        "monthly": {"labels": [m["label"] for m in monthly], "values": [m["total"] for m in monthly]},
        "categories": {
            "scope": scope,
            "labels": [c["category"] for c in categories],
            "values": [c["total"] for c in categories],
        },
        "stores": {"labels": [s["store"] for s in stores], "values": [s["total"] for s in stores]},
        "daily": {"labels": [d["label"] for d in daily], "values": [d["total"] for d in daily]},
    }


# ----------------------------------------------------------------- AI summary
def build_ai_summary(user_id, today=None) -> dict:
    """A compact, anonymous summary of ONE user's spending.

    This is the only thing that is ever sent to the AI provider. It contains
    totals and a few top items - never the user's name, email or password.
    """
    today = today or date.today()
    cs, ce = month_range(today.year, today.month)
    prev = add_months(today.replace(day=1), -1)
    ps, pe = month_range(prev.year, prev.month)

    cur_cat = {r["category"]: r["total"] for r in category_breakdown(user_id, cs, ce)}
    prev_cat = {r["category"]: r["total"] for r in category_breakdown(user_id, ps, pe)}
    change = {
        cat: (round((cur_cat.get(cat, 0.0) - p) / p * 100, 1) if p > 0 else None)
        for cat, p in {**{c: 0.0 for c in cur_cat}, **prev_cat}.items()
    }
    budget = budget_status(user_id, today.year, today.month)

    return {
        "currency": "BDT (৳)",
        "today": today.isoformat(),
        "current_month": {
            "label": today.strftime("%B %Y"),
            "total": total_between(user_id, cs, ce),
            "transactions": count_between(user_id, cs, ce),
            "days_elapsed": today.day,
        },
        "previous_month": {
            "label": prev.strftime("%B %Y"),
            "total": total_between(user_id, ps, pe),
            "transactions": count_between(user_id, ps, pe),
        },
        "category_current_month": cur_cat,
        "category_previous_month": prev_cat,
        "category_change_percent_vs_previous_month": change,
        "monthly_totals_last_6_months": [
            {"month": m["label"], "total": m["total"]} for m in monthly_totals(user_id, 6, today)
        ],
        "top_stores_all_time": top_stores(user_id, 5),
        "top_stores_current_month": top_stores(user_id, 5, cs, ce),
        "largest_expenses_current_month": largest_expenses(user_id, cs, ce, 5),
        "budget_current_month": budget if budget["has_budget"] else None,
        "total_transactions_all_time": count_between(user_id),
    }


# ----------------------------------------------------------------- ML dataframe
def expenses_dataframe(user_id) -> pd.DataFrame:
    """All of one user's expenses as a pandas DataFrame (for the ML code)."""
    rows = (
        db.session.query(Expense.id, Expense.date, Expense.amount, Expense.category, Expense.store)
        .filter(Expense.user_id == user_id)
        .order_by(Expense.date)
        .all()
    )
    df = pd.DataFrame(
        [(r.id, r.date, float(r.amount), r.category, r.store) for r in rows],
        columns=["id", "date", "amount", "category", "store"],
    )
    df["date"] = pd.to_datetime(df["date"])
    return df
