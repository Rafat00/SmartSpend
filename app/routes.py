"""Main pages: landing redirect, dashboard, chart data API, profile."""
from datetime import date

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.analytics import services as analytics
from app.auth.routes import validate_password
from app.extensions import db
from app.models import Expense

bp = Blueprint("main", __name__)


@bp.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("admin.dashboard" if current_user.is_admin else "main.dashboard"))
    return redirect(url_for("auth.login"))


@bp.route("/dashboard")
@login_required
def dashboard():
    today = date.today()
    cards = analytics.dashboard_cards(current_user.id, today)
    budget = analytics.budget_status(current_user.id, today.year, today.month)
    recent = (
        Expense.query.filter_by(user_id=current_user.id)
        .order_by(Expense.date.desc(), Expense.id.desc())
        .limit(5)
        .all()
    )
    return render_template("dashboard.html", cards=cards, budget=budget, recent=recent, today=today)


@bp.route("/api/charts")
@login_required
def chart_data():
    """JSON used by Chart.js on the dashboard (always the logged-in user's data)."""
    return jsonify(analytics.chart_payload(current_user.id))


@bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "update_name":
            name = request.form.get("name", "").strip()
            if not name or len(name) > 100:
                flash("Name is required and must be 100 characters or fewer.", "danger")
            else:
                current_user.name = name
                db.session.commit()
                flash("Profile updated.", "success")
        elif action == "change_password":
            current = request.form.get("current_password", "")
            new = request.form.get("new_password", "")
            confirm = request.form.get("confirm_password", "")
            errors = []
            if not current_user.check_password(current):
                errors.append("Your current password is incorrect.")
            errors += validate_password(new, confirm)
            if errors:
                for message in errors:
                    flash(message, "danger")
            else:
                current_user.set_password(new)
                db.session.commit()
                flash("Password changed successfully.", "success")
        return redirect(url_for("main.profile"))

    stats = analytics.dashboard_cards(current_user.id)
    return render_template("profile.html", stats=stats)
