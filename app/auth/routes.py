"""Registration, login and logout."""
import re

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import User, log_activity, utcnow
from app.utils import is_safe_url

bp = Blueprint("auth", __name__)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def validate_password(password: str, confirm: str | None = None) -> list[str]:
    errors = []
    if len(password) < 8:
        errors.append("Password must be at least 8 characters long.")
    if not (re.search(r"[A-Za-z]", password) and re.search(r"\d", password)):
        errors.append("Password must contain at least one letter and one number.")
    if confirm is not None and password != confirm:
        errors.append("Passwords do not match.")
    return errors


@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    form = {"name": "", "email": ""}
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        form = {"name": name, "email": email}

        errors = []
        if not name:
            errors.append("Name is required.")
        elif len(name) > 100:
            errors.append("Name must be 100 characters or fewer.")
        if not EMAIL_RE.match(email) or len(email) > 255:
            errors.append("Please enter a valid email address.")
        errors += validate_password(password, confirm)

        if not errors and User.query.filter_by(email=email).first():
            errors.append("An account with this email already exists. Try logging in.")

        if not errors:
            user = User(name=name, email=email)
            user.set_password(password)
            db.session.add(user)
            try:
                db.session.commit()
            except IntegrityError:  # two people registering the same email at once
                db.session.rollback()
                errors.append("An account with this email already exists. Try logging in.")
            else:
                # NOTE: role is never read from the form - new accounts are always plain users.
                log_activity("user_registered", f"User #{user.id} registered", actor_id=user.id)
                db.session.commit()
                flash("Account created successfully! Please log in.", "success")
                return redirect(url_for("auth.login"))

        for message in errors:
            flash(message, "danger")

    return render_template("auth/register.html", form=form)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("admin.dashboard" if current_user.is_admin else "main.dashboard"))

    email = ""
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()

        if user is None or not user.check_password(password):
            # Same message for "no such user" and "wrong password" on purpose.
            flash("Invalid email or password.", "danger")
        elif not user.is_active:
            # Only revealed after the correct password was given.
            flash("This account has been deactivated. Please contact an administrator.", "danger")
        else:
            login_user(user, remember=bool(request.form.get("remember")))
            user.last_login_at = utcnow()
            log_activity("user_login", f"User #{user.id} logged in", actor_id=user.id)
            db.session.commit()
            next_url = request.args.get("next")
            if next_url and is_safe_url(next_url):
                return redirect(next_url)
            return redirect(url_for("admin.dashboard" if user.is_admin else "main.dashboard"))

    return render_template("auth/login.html", email=email)


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))
