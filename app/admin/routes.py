"""Admin area (/admin/...).

SECURITY MODEL
* One `before_request` hook protects EVERY route of this blueprint on the server:
  anonymous -> redirected to login, logged-in non-admin -> HTTP 403.
* Hiding the sidebar link is only cosmetic; typing the URL does not help a normal user.
* All changes are POST + CSRF protected, validated, and written to the activity log.
* An admin cannot deactivate or change the role of THEIR OWN account, so the last
  administrator can never lock everyone out by accident.
* Promoting / demoting someone requires the acting admin's password again.
"""
import logging

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import func, or_

from app import categories as cat
from app.admin import services
from app.ai import ai_service
from app.extensions import db, login_manager
from app.models import ROLE_ADMIN, ROLES, Category, Expense, User, log_activity
from app.utils import escape_like

bp = Blueprint("admin", __name__, url_prefix="/admin")
logger = logging.getLogger(__name__)
PER_PAGE = 10


@bp.before_request
def require_admin():
    if not current_user.is_authenticated:
        return login_manager.unauthorized()
    if not current_user.is_admin:
        abort(403)


# ------------------------------------------------------------------ dashboard
@bp.route("/")
def dashboard():
    return render_template(
        "admin/dashboard.html",
        counts=services.overview_counts(),
        charts=services.chart_payload(),
        activity=services.recent_activity(),
    )


# ------------------------------------------------------------------ users
@bp.route("/users")
def users():
    q = request.args.get("q", "").strip()[:100]
    status = request.args.get("status", "")
    role = request.args.get("role", "")
    query = User.query
    if q:
        like = f"%{escape_like(q)}%"
        query = query.filter(or_(User.name.ilike(like, escape="\\"), User.email.ilike(like, escape="\\")))
    if status in ("active", "inactive"):
        query = query.filter(User.is_active.is_(status == "active"))
    if role in ROLES:
        query = query.filter(User.role == role)
    page = request.args.get("page", 1, type=int)
    pagination = query.order_by(User.created_at.desc(), User.id.desc()).paginate(
        page=page, per_page=PER_PAGE, error_out=False
    )
    counts = dict(
        db.session.query(Expense.user_id, func.count(Expense.id))
        .filter(Expense.user_id.in_([u.id for u in pagination.items]))
        .group_by(Expense.user_id).all()
    ) if pagination.items else {}
    args = {k: v for k, v in {"q": q, "status": status, "role": role}.items() if v}
    return render_template("admin/users.html", pagination=pagination, expense_counts=counts,
                           filters={"q": q, "status": status, "role": role}, query_args=args)


def _get_user_or_404(user_id: int) -> User:
    user = db.session.get(User, user_id)
    if user is None:
        abort(404)
    return user


@bp.route("/users/<int:user_id>")
def user_detail(user_id):
    user = _get_user_or_404(user_id)
    # Counts only - no amounts, stores or descriptions are shown to admins.
    expense_count = Expense.query.filter_by(user_id=user.id).count()
    last_expense = db.session.query(func.max(Expense.created_at)).filter_by(user_id=user.id).scalar()
    return render_template("admin/user_detail.html", u=user, expense_count=expense_count,
                           last_expense=last_expense, is_self=user.id == current_user.id)


@bp.route("/users/<int:user_id>/status", methods=["POST"])
def set_user_status(user_id):
    user = _get_user_or_404(user_id)
    if user.id == current_user.id:
        flash("You cannot deactivate your own account.", "danger")
        return redirect(url_for("admin.user_detail", user_id=user.id))
    activate = request.form.get("active") == "1"
    if user.is_active != activate:
        user.is_active = activate
        log_activity("user_activated" if activate else "user_deactivated",
                     f"Admin #{current_user.id} {'activated' if activate else 'deactivated'} user #{user.id}",
                     actor_id=current_user.id)
        db.session.commit()
    flash(f"{user.name} is now {'active' if activate else 'deactivated'}.", "success")
    return redirect(request.referrer if _same_site(request.referrer) else url_for("admin.users"))


@bp.route("/users/<int:user_id>/role", methods=["POST"])
def set_user_role(user_id):
    user = _get_user_or_404(user_id)
    back = redirect(url_for("admin.user_detail", user_id=user.id))
    if user.id == current_user.id:
        flash("You cannot change your own role.", "danger")
        return back
    new_role = request.form.get("role", "")
    if new_role not in ROLES:
        flash("Invalid role.", "danger")
        return back
    if not current_user.check_password(request.form.get("admin_password", "")):
        flash("Your password was incorrect, so the role was not changed.", "danger")
        return back
    if new_role == ROLE_ADMIN and not user.is_active:
        flash("Activate this account before making it an administrator.", "warning")
        return back
    if user.role != new_role:
        old = user.role
        user.role = new_role
        log_activity("role_changed", f"Admin #{current_user.id} changed user #{user.id} role {old} -> {new_role}",
                     actor_id=current_user.id)
        db.session.commit()
    flash(f"{user.name} is now a{'n' if new_role == ROLE_ADMIN else ''} {new_role}.", "success")
    return back


def _same_site(url) -> bool:
    from app.utils import is_safe_url
    return bool(url) and is_safe_url(url)


# ------------------------------------------------------------------ categories
@bp.route("/categories")
def categories():
    cat.ensure_default_categories()
    usage = dict(db.session.query(Expense.category, func.count(Expense.id)).group_by(Expense.category).all())
    rows = Category.query.order_by(Category.is_active.desc(), Category.name).all()
    known = {c.name for c in rows}
    orphans = {name: n for name, n in usage.items() if name not in known}  # expenses whose category row is missing
    return render_template("admin/categories.html", rows=rows, usage=usage, orphans=orphans,
                           protected=cat.PROTECTED_CATEGORY)


def _name_taken(name: str, exclude_id: int | None = None) -> bool:
    q = Category.query.filter(func.lower(Category.name) == name.lower())
    if exclude_id:
        q = q.filter(Category.id != exclude_id)
    return db.session.query(q.exists()).scalar()


@bp.route("/categories/new", methods=["GET", "POST"])
def category_new():
    values = {"name": "", "color": "#6366f1"}
    if request.method == "POST":
        values = {"name": request.form.get("name", "").strip(), "color": request.form.get("color", "").strip()}
        errors = cat.validate_category_fields(values["name"], values["color"])
        if not errors and _name_taken(values["name"]):
            errors.append("A category with this name already exists.")
        if not errors:
            cat.ensure_default_categories()
            db.session.add(Category(name=values["name"], color=values["color"].lower()))
            log_activity("category_created", f"Category '{values['name']}' created", actor_id=current_user.id)
            db.session.commit()
            flash("Category created.", "success")
            return redirect(url_for("admin.categories"))
        for e in errors:
            flash(e, "danger")
    return render_template("admin/category_form.html", mode="new", values=values, category=None)


@bp.route("/categories/<int:category_id>/edit", methods=["GET", "POST"])
def category_edit(category_id):
    cat.ensure_default_categories()
    category = db.session.get(Category, category_id) or abort(404)
    values = {"name": category.name, "color": category.color}
    locked = category.name == cat.PROTECTED_CATEGORY
    if request.method == "POST":
        values = {"name": request.form.get("name", "").strip() if not locked else category.name,
                  "color": request.form.get("color", "").strip()}
        errors = cat.validate_category_fields(values["name"], values["color"])
        if not errors and _name_taken(values["name"], exclude_id=category.id):
            errors.append("A category with this name already exists.")
        if not errors:
            old_name = category.name
            category.color = values["color"].lower()
            if values["name"] != old_name:
                # Keep existing expenses consistent: they store the category name.
                moved = Expense.query.filter_by(category=old_name).update({"category": values["name"]})
                category.name = values["name"]
                log_activity("category_renamed", f"Category '{old_name}' renamed to '{values['name']}' ({moved} expenses updated)",
                             actor_id=current_user.id)
            else:
                log_activity("category_updated", f"Category '{old_name}' updated", actor_id=current_user.id)
            db.session.commit()
            flash("Category updated.", "success")
            return redirect(url_for("admin.categories"))
        for e in errors:
            flash(e, "danger")
    return render_template("admin/category_form.html", mode="edit", values=values, category=category, locked=locked)


@bp.route("/categories/<int:category_id>/toggle", methods=["POST"])
def category_toggle(category_id):
    cat.ensure_default_categories()
    category = db.session.get(Category, category_id) or abort(404)
    if category.name == cat.PROTECTED_CATEGORY and category.is_active:
        flash(f"'{cat.PROTECTED_CATEGORY}' is the fallback category and cannot be deactivated.", "warning")
        return redirect(url_for("admin.categories"))
    category.is_active = not category.is_active
    # Expenses are NOT touched: they keep their category name and remain visible everywhere.
    log_activity("category_activated" if category.is_active else "category_deactivated",
                 f"Category '{category.name}' {'activated' if category.is_active else 'deactivated'}",
                 actor_id=current_user.id)
    db.session.commit()
    flash(f"'{category.name}' {'activated' if category.is_active else 'deactivated'}."
          + ("" if category.is_active else " Existing expenses were kept."), "success")
    return redirect(url_for("admin.categories"))


# ------------------------------------------------------------------ system monitoring
@bp.route("/system")
def system():
    client = ai_service.get_client()
    return render_template(
        "admin/system.html",
        counts=services.overview_counts(),
        db_health=services.database_health(),
        ai=services.ai_status(client),
        runtime=services.runtime_info(),
    )


@bp.route("/system/test-ai", methods=["POST"])
def test_ai():
    client = ai_service.get_client()
    if not client.configured:
        flash("AI is not configured. Set AI_API_KEY and AI_MODEL in .env.", "warning")
    else:
        try:
            client.complete([{"role": "user", "content": "Reply with the single word: ok"}], max_tokens=5)
            flash("AI service responded successfully.", "success")
        except ai_service.AIServiceError as exc:
            flash(f"AI test failed: {exc}", "danger")  # generic message, never contains the key
    return redirect(url_for("admin.system"))
