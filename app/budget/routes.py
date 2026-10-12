"""Monthly budget: set, view progress, delete."""
from datetime import date

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.analytics import services as analytics
from app.extensions import db
from app.models import Budget
from app.utils import parse_amount

bp = Blueprint("budget", __name__, url_prefix="/budget")

MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July",
               "August", "September", "October", "November", "December"]


def _int_arg(source, key, default, low, high):
    try:
        value = int(source.get(key, default))
    except (TypeError, ValueError):
        return default
    return value if low <= value <= high else default


@bp.route("/", methods=["GET", "POST"])
@login_required
def manage():
    today = date.today()

    if request.method == "POST":
        year = _int_arg(request.form, "year", today.year, 2000, 2100)
        month = _int_arg(request.form, "month", today.month, 1, 12)
        try:
            amount = parse_amount(request.form.get("amount"))
        except ValueError as exc:
            flash(f"Budget not saved: {exc}", "danger")
            return redirect(url_for("budget.manage", year=year, month=month))

        budget = Budget.query.filter_by(user_id=current_user.id, year=year, month=month).first()
        if budget is None:
            budget = Budget(user_id=current_user.id, year=year, month=month, amount=amount)
            db.session.add(budget)
        else:
            budget.amount = amount
        db.session.commit()
        flash(f"Budget for {MONTH_NAMES[month - 1]} {year} saved.", "success")
        return redirect(url_for("budget.manage", year=year, month=month))

    year = _int_arg(request.args, "year", today.year, 2000, 2100)
    month = _int_arg(request.args, "month", today.month, 1, 12)
    status = analytics.budget_status(current_user.id, year, month)

    history = []
    budgets = (
        Budget.query.filter_by(user_id=current_user.id)
        .order_by(Budget.year.desc(), Budget.month.desc())
        .limit(12)
        .all()
    )
    for b in budgets:
        history.append(analytics.budget_status(current_user.id, b.year, b.month) | {"id": b.id})

    return render_template(
        "budget.html", status=status, year=year, month=month, month_names=MONTH_NAMES,
        history=history, today=today,
    )


@bp.route("/<int:budget_id>/delete", methods=["POST"])
@login_required
def delete(budget_id):
    budget = Budget.query.filter_by(id=budget_id, user_id=current_user.id).first()
    if budget is None:
        abort(404)
    db.session.delete(budget)
    db.session.commit()
    flash("Budget removed.", "info")
    return redirect(url_for("budget.manage"))
