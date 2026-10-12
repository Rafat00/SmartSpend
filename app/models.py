"""Database models (SQLAlchemy ORM)."""
from datetime import datetime, timezone

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db, login_manager


ROLE_USER = "user"
ROLE_ADMIN = "admin"
ROLES = (ROLE_USER, ROLE_ADMIN)


def utcnow():
    return datetime.now(timezone.utc)


class User(UserMixin, db.Model):
    __tablename__ = "users"
    __table_args__ = (db.CheckConstraint("role IN ('user', 'admin')", name="ck_users_role"),)

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    # --- admin / access control ---
    # Role is NEVER read from a form on registration or profile pages; it can only be
    # changed by an administrator (app/admin) or the `flask create-admin` command.
    role = db.Column(db.String(20), nullable=False, default=ROLE_USER, server_default=ROLE_USER)
    # Overrides UserMixin.is_active. Deactivated accounts cannot log in and existing
    # sessions stop working immediately (see load_user below).
    is_active = db.Column(db.Boolean, nullable=False, default=True, server_default=db.true())
    last_login_at = db.Column(db.DateTime(timezone=True))

    # One user -> many expenses / budgets. Deleting a user deletes their data too.
    expenses = db.relationship(
        "Expense", backref="user", lazy="dynamic", cascade="all, delete-orphan"
    )
    budgets = db.relationship(
        "Budget", backref="user", lazy="dynamic", cascade="all, delete-orphan"
    )

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    @property
    def is_admin(self) -> bool:
        return self.role == ROLE_ADMIN

    def __repr__(self):
        return f"<User {self.email}>"


class Expense(db.Model):
    __tablename__ = "expenses"
    __table_args__ = (db.Index("ix_expenses_user_date", "user_id", "date"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    expense_name = db.Column(db.String(120), nullable=False)
    category = db.Column(db.String(50), nullable=False, index=True)
    subcategory = db.Column(db.String(50))  # filled by AI / fallback categorizer (optional)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    date = db.Column(db.Date, nullable=False)
    store = db.Column(db.String(120))
    payment_method = db.Column(db.String(30))
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    def __repr__(self):
        return f"<Expense {self.expense_name} {self.amount}>"


class Budget(db.Model):
    __tablename__ = "budgets"
    __table_args__ = (
        db.UniqueConstraint("user_id", "year", "month", name="uq_budget_user_year_month"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    month = db.Column(db.Integer, nullable=False)  # 1-12
    year = db.Column(db.Integer, nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)

    def __repr__(self):
        return f"<Budget {self.year}-{self.month:02d} {self.amount}>"


class Category(db.Model):
    """Expense categories managed by administrators.

    Expenses keep storing the category *name* (a plain string, as before), so no existing
    expense row is touched when a category is deactivated. Deactivating only hides the
    category from "Add expense" / AI suggestions; old expenses keep it and still show up
    in history, filters, charts and exports.
    """

    __tablename__ = "categories"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    color = db.Column(db.String(7), nullable=False, default="#94a3b8", server_default="#94a3b8")
    is_active = db.Column(db.Boolean, nullable=False, default=True, server_default=db.true())
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False,
                           server_default=db.func.now())

    def __repr__(self):
        return f"<Category {self.name}>"


class ActivityLog(db.Model):
    """Small audit trail shown on the admin dashboard (no financial data is stored here)."""

    __tablename__ = "activity_logs"

    id = db.Column(db.Integer, primary_key=True)
    actor_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), index=True)
    action = db.Column(db.String(50), nullable=False, index=True)
    detail = db.Column(db.String(255))
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False, index=True)

    actor = db.relationship("User", lazy="joined")


def log_activity(action: str, detail: str | None = None, actor_id: int | None = None) -> None:
    """Add an activity row to the current session (the caller commits)."""
    db.session.add(ActivityLog(action=action, detail=(detail or "")[:255] or None, actor_id=actor_id))


@login_manager.user_loader
def load_user(user_id: str):
    user = db.session.get(User, int(user_id))
    # A deactivated user is treated as logged out, even if their session cookie is still valid.
    if user is None or not user.is_active:
        return None
    return user
