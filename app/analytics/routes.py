"""Analytics page: daily / weekly / monthly spending, categories and stores."""
from datetime import date

from flask import Blueprint, render_template
from flask_login import current_user, login_required

from app.analytics import services as analytics
from app.utils import month_range

bp = Blueprint("analytics", __name__, url_prefix="/analytics")


@bp.route("/")
@login_required
def overview():
    today = date.today()
    uid = current_user.id
    m_start, m_end = month_range(today.year, today.month)

    daily = analytics.daily_series(uid, 14, today)
    weekly = analytics.weekly_totals(uid, 8, today)
    monthly = analytics.monthly_totals(uid, 12, today)
    comparison = analytics.category_comparison(uid, today)
    stores = analytics.top_stores(uid, 10)
    month_categories = analytics.category_breakdown(uid, m_start, m_end)

    chart = {
        "weekly": {"labels": [w["label"] for w in weekly], "values": [w["total"] for w in weekly]},
        "comparison": {
            "labels": [c["category"] for c in comparison],
            "current": [c["current"] for c in comparison],
            "previous": [c["previous"] for c in comparison],
        },
    }
    return render_template(
        "analytics.html",
        today=today,
        daily=daily,
        weekly=weekly,
        monthly=monthly,
        comparison=comparison,
        stores=stores,
        month_categories=month_categories,
        chart=chart,
    )
