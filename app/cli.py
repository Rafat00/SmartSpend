"""Custom `flask` commands.

    flask seed-demo     creates a demo user with ~9 months of realistic expenses,
                        so the charts, predictions and anomaly detection can be demonstrated.
"""
import calendar
import random
from datetime import date

import click

from app.extensions import db
from app.models import Budget, Expense, User
from app.utils import add_months

DEMO_EMAIL = "demo@smartspend.local"
DEMO_PASSWORD = "Demo@12345"

# (name, category, subcategory, store, payment, min, max, min_per_month, max_per_month)
TEMPLATES = [
    ("Lunch", "Food", "Restaurant", "Sultan's Dine", "Cash", 220, 450, 8, 12),
    ("Tea & snacks", "Food", "Cafe", "Campus Canteen", "Cash", 40, 120, 8, 14),
    ("Groceries", "Groceries", "Groceries", "Shwapno", "Card", 700, 1800, 3, 5),
    ("Uber ride", "Transport", "Ride Sharing", "Uber", "bKash", 120, 380, 6, 10),
    ("Rickshaw fare", "Transport", "Public Transport", "Local", "Cash", 30, 90, 8, 14),
    ("Clothes", "Shopping", "Clothing", "Bashundhara City", "Card", 500, 2000, 1, 3),
    ("Internet bill", "Bills", "Utilities", "Link3", "bKash", 900, 900, 1, 1),
    ("Mobile recharge", "Bills", "Mobile", "Grameenphone", "bKash", 199, 399, 1, 2),
    ("Hostel rent", "Rent", "Housing", "Hostel", "Bank Transfer", 6500, 6500, 1, 1),
    ("Movie night", "Entertainment", "Leisure", "Star Cineplex", "Card", 400, 900, 1, 2),
    ("Medicine", "Health", "Medical", "Lazz Pharma", "Cash", 150, 600, 0, 2),
    ("Course material", "Education", "Study", "Nilkhet Book Market", "Cash", 300, 1200, 0, 2),
]


def register_cli(app):
    @app.cli.command("create-admin")
    @click.option("--email", prompt="Admin email", help="Email address of the administrator.")
    @click.option("--name", default=None, help="Display name (only used when creating a new account).")
    @click.option(
        "--password",
        prompt=True, hide_input=True, confirmation_prompt=True,
        envvar="SMARTSPEND_ADMIN_PASSWORD",
        help="Prompted securely if omitted. Prefer the prompt; the password is never stored in code.",
    )
    def create_admin(email, name, password):
        """Create an administrator (or promote an existing user).

        Run:  flask create-admin
        """
        from app.auth.routes import EMAIL_RE, validate_password
        from app.models import ROLE_ADMIN, log_activity

        email = email.strip().lower()
        if not EMAIL_RE.match(email) or len(email) > 255:
            raise click.ClickException("Please enter a valid email address.")

        user = User.query.filter_by(email=email).first()
        if user:
            if user.is_admin and user.is_active:
                click.echo(f"{email} is already an active administrator. Nothing changed.")
                return
            if not click.confirm(f"{email} already exists. Promote/activate this account as admin?"):
                raise click.Abort()
            if not user.check_password(password):
                raise click.ClickException("Wrong password for the existing account. Nothing changed.")
            user.role, user.is_active = ROLE_ADMIN, True
            action = "promoted to administrator"
        else:
            problems = validate_password(password)
            if problems:
                raise click.ClickException(" ".join(problems))
            user = User(name=(name or "Administrator").strip()[:100], email=email, role=ROLE_ADMIN)
            user.set_password(password)  # hashed with the same mechanism as normal registration
            db.session.add(user)
            action = "created"
        db.session.flush()
        log_activity("admin_provisioned", f"Admin account #{user.id} {action} via CLI", actor_id=user.id)
        db.session.commit()
        click.echo(f"Administrator {email} {action}. Log in at /login.")

    @app.cli.command("seed-demo")
    def seed_demo():
        """Create (or reset) a demo account with sample data."""
        existing = User.query.filter_by(email=DEMO_EMAIL).first()
        if existing:
            db.session.delete(existing)
            db.session.commit()

        user = User(name="Demo Student", email=DEMO_EMAIL)
        user.set_password(DEMO_PASSWORD)
        db.session.add(user)
        db.session.flush()

        rng = random.Random(42)
        today = date.today()
        first_this_month = today.replace(day=1)

        for months_back in range(8, -1, -1):
            month_start = add_months(first_this_month, -months_back)
            last_day = calendar.monthrange(month_start.year, month_start.month)[1]
            growth = 1 + (8 - months_back) * 0.02  # spending drifts up ~2% per month
            for name, cat, sub, store, pay, low, high, cmin, cmax in TEMPLATES:
                for _ in range(rng.randint(cmin, cmax)):
                    when = month_start.replace(day=rng.randint(1, last_day))
                    if when > today:
                        continue
                    amount = round(rng.uniform(low, high) * (growth if cat != "Rent" else 1), 2)
                    db.session.add(
                        Expense(user_id=user.id, expense_name=name, category=cat, subcategory=sub,
                                amount=amount, date=when, store=store, payment_method=pay)
                    )
            db.session.add(
                Budget(user_id=user.id, year=month_start.year, month=month_start.month, amount=30000)
            )

        # One deliberately unusual purchase so anomaly detection has something to find.
        db.session.add(
            Expense(user_id=user.id, expense_name="Laptop bag + accessories", category="Shopping",
                    subcategory="General", amount=9500, date=max(first_this_month, today.replace(day=1)),
                    store="Daraz", payment_method="Card", description="Unusually large purchase (demo)")
        )
        db.session.commit()
        click.echo(f"Demo data created.\n  Email:    {DEMO_EMAIL}\n  Password: {DEMO_PASSWORD}")
