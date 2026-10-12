"""Expense CRUD, search/filter, AI categorization endpoint and CSV export.

SECURITY: every query includes `user_id == current_user.id`, and single-expense
lookups return 404 (not 403) for other people's expenses so nothing leaks.
"""
import csv
import io
import logging
from datetime import date

from flask import (Blueprint, Response, abort, flash, jsonify, redirect,
                   render_template, request, url_for)
from flask_login import current_user, login_required
from sqlalchemy import func, or_

from app.ai import ai_service
from app import categories as category_service
from app.constants import PAYMENT_METHODS
from app.extensions import db
from app.ml.anomaly import check_new_expense
from app.models import Expense
from app.utils import escape_like, parse_amount, parse_date

bp = Blueprint("expenses", __name__, url_prefix="/expenses")
logger = logging.getLogger(__name__)

PER_PAGE = 15


# ----------------------------------------------------------------- helpers
def _own_expense_or_404(expense_id: int) -> Expense:
    expense = Expense.query.filter_by(id=expense_id, user_id=current_user.id).first()
    if expense is None:
        abort(404)
    return expense


def _parse_form(form, keep_category: str | None = None) -> tuple[dict, list[str]]:
    """Validate the add/edit form. Returns (clean_values, error_messages)."""
    errors = []
    name = form.get("expense_name", "").strip()
    if not name:
        errors.append("Expense name cannot be empty.")
    elif len(name) > 120:
        errors.append("Expense name must be 120 characters or fewer.")

    category = form.get("category", "").strip()
    # Only active categories can be chosen; when editing, an expense may keep its
    # (possibly deactivated) current category so old records stay valid.
    if category not in category_service.active_category_names() and category != keep_category:
        errors.append("Please choose a valid category.")

    amount = None
    try:
        amount = parse_amount(form.get("amount"))
    except ValueError as exc:
        errors.append(str(exc))

    when = None
    try:
        when = parse_date(form.get("date"))
    except ValueError as exc:
        errors.append(str(exc))

    store = form.get("store", "").strip()
    if len(store) > 120:
        errors.append("Store name must be 120 characters or fewer.")

    payment = form.get("payment_method", "").strip()
    if payment and payment not in PAYMENT_METHODS:
        errors.append("Please choose a valid payment method.")

    subcategory = form.get("subcategory", "").strip()
    if len(subcategory) > 50:
        errors.append("Subcategory must be 50 characters or fewer.")

    description = form.get("description", "").strip()
    if len(description) > 1000:
        errors.append("Description must be 1000 characters or fewer.")

    clean = {
        "expense_name": name,
        "category": category,
        "subcategory": subcategory or None,
        "amount": amount,
        "date": when,
        "store": store or None,
        "payment_method": payment or None,
        "description": description or None,
    }
    return clean, errors


def _raw_values(form) -> dict:
    keys = ["expense_name", "category", "subcategory", "amount", "date", "store",
            "payment_method", "description"]
    return {k: form.get(k, "") for k in keys}


def _build_filters(args):
    """Build SQLAlchemy filters from the query string. Returns (filters, applied, warnings)."""
    filters = [Expense.user_id == current_user.id]
    applied = {k: args.get(k, "").strip() for k in ("q", "category", "store", "date_from", "date_to")}
    warnings = []

    if applied["q"]:
        like = f"%{escape_like(applied['q'])}%"
        filters.append(
            or_(
                Expense.expense_name.ilike(like, escape="\\"),
                Expense.store.ilike(like, escape="\\"),
                Expense.description.ilike(like, escape="\\"),
            )
        )
    if applied["category"]:
        filters.append(Expense.category == applied["category"])
    if applied["store"]:
        filters.append(Expense.store.ilike(f"%{escape_like(applied['store'])}%", escape="\\"))
    for key, op in (("date_from", "ge"), ("date_to", "le")):
        if applied[key]:
            try:
                d = parse_date(applied[key], "Filter date")
            except ValueError as exc:
                warnings.append(str(exc))
                applied[key] = ""
            else:
                filters.append(Expense.date >= d if op == "ge" else Expense.date <= d)
    return filters, applied, warnings


def _user_stores() -> list[str]:
    rows = (
        db.session.query(Expense.store)
        .filter(Expense.user_id == current_user.id, Expense.store.isnot(None), Expense.store != "")
        .distinct()
        .order_by(Expense.store)
        .all()
    )
    return [r[0] for r in rows]


def _warn_if_unusual(expense: Expense) -> None:
    """Run anomaly detection; never let an ML problem block saving an expense."""
    try:
        result = check_new_expense(current_user.id, expense)
        if result.get("unusual"):
            flash(result["message"], "warning")
    except Exception:  # noqa: BLE001
        logger.exception("Unusual-expense check failed")


# ----------------------------------------------------------------- list
@bp.route("/")
@login_required
def list_expenses():
    filters, applied, warnings = _build_filters(request.args)
    for w in warnings:
        flash(w, "warning")

    page = request.args.get("page", 1, type=int)
    pagination = (
        Expense.query.filter(*filters)
        .order_by(Expense.date.desc(), Expense.id.desc())
        .paginate(page=page, per_page=PER_PAGE, error_out=False)
    )
    filtered_total = db.session.query(func.coalesce(func.sum(Expense.amount), 0)).filter(*filters).scalar()
    query_args = {k: v for k, v in applied.items() if v}
    return render_template(
        "expenses/list.html",
        pagination=pagination,
        filters=applied,
        query_args=query_args,
        filtered_total=filtered_total,
        categories=category_service.all_category_names(),
        stores=_user_stores(),
    )


# ----------------------------------------------------------------- add
@bp.route("/add", methods=["GET", "POST"])
@login_required
def add_expense():
    values = {"date": date.today().isoformat(), "payment_method": "Cash"}
    if request.method == "POST":
        clean, errors = _parse_form(request.form)
        values = _raw_values(request.form)
        if not errors:
            expense = Expense(user_id=current_user.id, **clean)
            db.session.add(expense)
            db.session.commit()
            flash("Expense added successfully.", "success")
            _warn_if_unusual(expense)
            return redirect(url_for("expenses.list_expenses"))
        for message in errors:
            flash(message, "danger")
    return render_template(
        "expenses/form.html", mode="add", values=values, categories=category_service.active_category_names(),
        payment_methods=PAYMENT_METHODS, stores=_user_stores(),
    )


# ----------------------------------------------------------------- edit
@bp.route("/<int:expense_id>/edit", methods=["GET", "POST"])
@login_required
def edit_expense(expense_id):
    expense = _own_expense_or_404(expense_id)
    values = {
        "expense_name": expense.expense_name,
        "category": expense.category,
        "subcategory": expense.subcategory or "",
        "amount": f"{expense.amount:.2f}",
        "date": expense.date.isoformat(),
        "store": expense.store or "",
        "payment_method": expense.payment_method or "",
        "description": expense.description or "",
    }
    if request.method == "POST":
        clean, errors = _parse_form(request.form, keep_category=expense.category)
        values = _raw_values(request.form)
        if not errors:
            for key, value in clean.items():
                setattr(expense, key, value)
            db.session.commit()
            flash("Expense updated.", "success")
            _warn_if_unusual(expense)
            return redirect(url_for("expenses.list_expenses"))
        for message in errors:
            flash(message, "danger")
    return render_template(
        "expenses/form.html", mode="edit", expense=expense, values=values,
        categories=sorted(set(category_service.active_category_names()) | {expense.category}),
        payment_methods=PAYMENT_METHODS, stores=_user_stores(),
    )


# ----------------------------------------------------------------- delete
@bp.route("/<int:expense_id>/delete", methods=["POST"])
@login_required
def delete_expense(expense_id):
    expense = _own_expense_or_404(expense_id)
    db.session.delete(expense)
    db.session.commit()
    flash("Expense deleted.", "info")
    return redirect(request.referrer or url_for("expenses.list_expenses"))


# ----------------------------------------------------------------- AI categorize
@bp.route("/categorize", methods=["POST"])
@login_required
def categorize():
    payload = request.get_json(silent=True) or {}
    text = str(payload.get("text", "")).strip()
    if not text:
        return jsonify(error="Type an expense name first."), 400
    if len(text) > 300:
        return jsonify(error="Text is too long."), 400
    return jsonify(ai_service.categorize_expense(text))


# ----------------------------------------------------------------- CSV export
def _csv_safe(value):
    """Stop spreadsheet formula injection (a cell starting with = + - @ is run as a formula)."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


@bp.route("/export.csv")
@login_required
def export_csv():
    """Download the logged-in user's expenses (respects the current filters)."""
    filters, _applied, _warnings = _build_filters(request.args)
    rows = Expense.query.filter(*filters).order_by(Expense.date, Expense.id).all()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["date", "expense_name", "category", "amount", "store", "payment_method", "description"])
    for e in rows:
        writer.writerow([
            e.date.isoformat(),
            _csv_safe(e.expense_name),
            e.category,
            f"{e.amount:.2f}",
            _csv_safe(e.store or ""),
            e.payment_method or "",
            _csv_safe((e.description or "").replace("\r", " ").replace("\n", " ")),
        ])
    # "﻿" (BOM) makes Excel on Windows display the ৳ sign and Bengali text correctly.
    data = "﻿" + buffer.getvalue()
    return Response(
        data,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=expenses.csv"},
    )
