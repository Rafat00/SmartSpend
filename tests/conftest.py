import pytest

from app import create_app
from app.extensions import db
from app.models import User
from config import TestConfig


@pytest.fixture()
def app():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def make_user(email="alice@example.com", name="Alice", password="Password123", role="user", is_active=True):
    user = User(name=name, email=email, role=role, is_active=is_active)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user


def login(client, email="alice@example.com", password="Password123"):
    return client.post("/login", data={"email": email, "password": password}, follow_redirects=True)


EXPENSE_FORM = {
    "expense_name": "Lunch",
    "category": "Food",
    "amount": "250",
    "date": "2026-10-08",
    "store": "Sultan's Dine",
    "payment_method": "Cash",
    "description": "Lunch with friends",
}


@pytest.fixture()
def alice(app, client):
    """A registered + logged-in user (Alice)."""
    make_user()
    login(client)
    return client


@pytest.fixture()
def admin(app, client):
    """A logged-in administrator."""
    make_user(email="admin@example.com", name="Admin", role="admin")
    login(client, "admin@example.com")
    return client
