from app.models import User
from tests.conftest import login, make_user


def register(client, **overrides):
    data = {
        "name": "Alice", "email": "alice@example.com",
        "password": "Password123", "confirm_password": "Password123",
    }
    data.update(overrides)
    return client.post("/register", data=data, follow_redirects=True)


def test_registration_creates_user_with_hashed_password(client, app):
    response = register(client)
    assert b"Account created" in response.data
    user = User.query.filter_by(email="alice@example.com").first()
    assert user is not None
    assert user.password_hash != "Password123"  # never stored in plain text
    assert user.check_password("Password123")


def test_registration_rejects_duplicate_email(client, app):
    register(client)
    response = register(client, name="Other")
    assert b"already exists" in response.data
    assert User.query.count() == 1


def test_registration_validates_input(client, app):
    assert b"valid email" in register(client, email="not-an-email").data
    assert b"do not match" in register(client, confirm_password="Different123").data
    assert b"at least 8 characters" in register(client, password="a1", confirm_password="a1").data
    assert b"Name is required" in register(client, name="  ").data
    assert User.query.count() == 0


def test_login_success(client, app):
    make_user()
    response = login(client)
    assert b"Welcome back" in response.data


def test_login_invalid_credentials(client, app):
    make_user()
    assert b"Invalid email or password" in login(client, password="WrongPass1").data
    assert b"Invalid email or password" in login(client, email="nobody@example.com").data


def test_logout(alice):
    response = alice.post("/logout", follow_redirects=True)
    assert b"logged out" in response.data
    assert alice.get("/dashboard").status_code == 302  # protected again


def test_protected_routes_redirect_to_login(client, app):
    for url in ["/dashboard", "/expenses/", "/expenses/add", "/budget/", "/analytics/",
                "/ai/chat", "/ai/analysis", "/predictions/", "/profile", "/expenses/export.csv"]:
        response = client.get(url)
        assert response.status_code == 302, url
        assert "/login" in response.headers["Location"], url


def test_login_does_not_redirect_to_external_site(client, app):
    make_user()
    response = client.post(
        "/login?next=https://evil.example.com/",
        data={"email": "alice@example.com", "password": "Password123"},
    )
    assert response.status_code == 302
    assert "evil.example.com" not in response.headers["Location"]
