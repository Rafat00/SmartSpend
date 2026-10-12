"""Admin side: authentication, authorization, user + category management, monitoring."""
import pytest
from click.testing import CliRunner

from datetime import date

from app.extensions import db
from app.models import ActivityLog, Category, Expense, User
from tests.conftest import EXPENSE_FORM, login, make_user

ADMIN_GET_URLS = [
    "/admin/", "/admin/users", "/admin/users/1", "/admin/categories", "/admin/categories/new",
    "/admin/categories/1/edit", "/admin/system",
]
ADMIN_POST_URLS = [
    "/admin/users/1/status", "/admin/users/1/role", "/admin/categories/1/toggle",
    "/admin/categories/new", "/admin/categories/1/edit", "/admin/system/test-ai",
]


# ----------------------------------------------------------- access control
@pytest.mark.parametrize("url", ADMIN_GET_URLS)
def test_anonymous_is_redirected_to_login(client, app, url):
    response = client.get(url)
    assert response.status_code == 302 and "/login" in response.headers["Location"]


@pytest.mark.parametrize("url", ADMIN_POST_URLS)
def test_anonymous_cannot_post_admin_routes(client, app, url):
    response = client.post(url, data={"active": "0", "role": "admin", "name": "X", "color": "#112233"})
    assert response.status_code == 302 and "/login" in response.headers["Location"]


@pytest.mark.parametrize("url", ADMIN_GET_URLS)
def test_ordinary_user_gets_403_on_admin_pages(alice, url):
    assert alice.get(url).status_code == 403


@pytest.mark.parametrize("url", ADMIN_POST_URLS)
def test_ordinary_user_gets_403_on_admin_posts(alice, url):
    response = alice.post(url, data={"active": "0", "role": "admin", "name": "X", "color": "#112233"})
    assert response.status_code == 403


def test_ordinary_user_has_no_admin_link_and_admin_has(app, client):
    make_user()
    login(client)
    assert b"Admin Panel" not in client.get("/dashboard").data


def test_admin_sees_admin_panel_link_on_user_dashboard(admin):
    assert b"Admin Panel" in admin.get("/dashboard").data


@pytest.mark.parametrize("url", ADMIN_GET_URLS)
def test_admin_can_open_admin_pages(app, admin, url):
    assert admin.get(url).status_code == 200


def test_admin_login_redirects_to_admin_dashboard(app, client):
    make_user(email="a@example.com", role="admin")
    response = client.post("/login", data={"email": "a@example.com", "password": "Password123"})
    assert response.headers["Location"].endswith("/admin/")


def test_user_login_still_goes_to_user_dashboard(app, client):
    make_user()
    response = client.post("/login", data={"email": "alice@example.com", "password": "Password123"})
    assert response.headers["Location"].endswith("/dashboard")


# ----------------------------------------------------------- no self-promotion
def test_registration_cannot_create_admin(client, app):
    client.post("/register", data={"name": "Eve", "email": "eve@example.com", "password": "Password123",
                                   "confirm_password": "Password123", "role": "admin", "is_active": "1"})
    assert User.query.filter_by(email="eve@example.com").one().role == "user"


def test_profile_cannot_change_role(alice):
    alice.post("/profile", data={"action": "update_name", "name": "Alice 2", "role": "admin"})
    user = User.query.filter_by(email="alice@example.com").one()
    assert user.name == "Alice 2" and user.role == "user"


# ----------------------------------------------------------- deactivated accounts
def test_deactivated_user_cannot_log_in(app, client):
    make_user(is_active=False)
    response = login(client)
    assert b"deactivated" in response.data
    assert client.get("/dashboard").status_code == 302


def test_wrong_password_on_deactivated_account_gives_generic_error(app, client):
    make_user(is_active=False)
    assert b"Invalid email or password" in login(client, password="wrongpass1").data


def test_deactivation_logs_out_existing_session(app, alice):
    assert alice.get("/dashboard").status_code == 200
    user = User.query.filter_by(email="alice@example.com").one()
    user.is_active = False
    db.session.commit()
    assert alice.get("/dashboard").status_code == 302


# ----------------------------------------------------------- user management
def test_users_list_search_filter_and_pagination(app, admin):
    for i in range(12):
        make_user(email=f"user{i}@example.com", name=f"Student {i}", is_active=(i % 2 == 0))
    page1 = admin.get("/admin/users").data
    assert b"Next" in page1
    assert b"user11@example.com" in admin.get("/admin/users?page=2").data or b"user0@example.com" in admin.get("/admin/users?page=2").data
    found = admin.get("/admin/users?q=user7").data
    assert b"user7@example.com" in found and b"user3@example.com" not in found
    inactive = admin.get("/admin/users?status=inactive").data
    assert b"user1@example.com" in inactive and b"user2@example.com" not in inactive
    assert b"admin@example.com" in admin.get("/admin/users?role=admin").data
    # LIKE wildcards are matched literally
    assert b"No users match" in admin.get("/admin/users?q=%25").data


def test_user_detail_shows_counts_but_no_password_or_amounts(app, admin):
    user = make_user()
    db.session.add(Expense(user_id=user.id, expense_name="Secret thing", category="Food", amount=98765, date=date(2026, 10, 1)))
    db.session.commit()
    html = admin.get(f"/admin/users/{user.id}").data.decode()
    assert "alice@example.com" in html and "Expenses recorded" in html
    assert user.password_hash not in html and "Secret thing" not in html and "98765" not in html
    assert admin.get("/admin/users/9999").status_code == 404


def test_admin_can_deactivate_and_activate_user(app, admin):
    user = make_user()
    admin.post(f"/admin/users/{user.id}/status", data={"active": "0"})
    assert db.session.get(User, user.id).is_active is False
    admin.post(f"/admin/users/{user.id}/status", data={"active": "1"})
    assert db.session.get(User, user.id).is_active is True
    actions = {a.action for a in ActivityLog.query}
    assert {"user_deactivated", "user_activated"} <= actions


def test_admin_cannot_deactivate_self(app, admin):
    me = User.query.filter_by(email="admin@example.com").one()
    response = admin.post(f"/admin/users/{me.id}/status", data={"active": "0"}, follow_redirects=True)
    assert b"cannot deactivate your own" in response.data
    assert db.session.get(User, me.id).is_active is True


def test_admin_cannot_change_own_role(app, admin):
    me = User.query.filter_by(email="admin@example.com").one()
    response = admin.post(f"/admin/users/{me.id}/role", data={"role": "user", "admin_password": "Password123"},
                          follow_redirects=True)
    assert b"cannot change your own role" in response.data
    assert db.session.get(User, me.id).is_admin


def test_role_change_requires_admin_password(app, admin):
    user = make_user()
    admin.post(f"/admin/users/{user.id}/role", data={"role": "admin", "admin_password": "wrong-pass1"})
    assert db.session.get(User, user.id).role == "user"
    admin.post(f"/admin/users/{user.id}/role", data={"role": "admin", "admin_password": "Password123"})
    assert db.session.get(User, user.id).role == "admin"
    admin.post(f"/admin/users/{user.id}/role", data={"role": "user", "admin_password": "Password123"})
    assert db.session.get(User, user.id).role == "user"


def test_invalid_role_is_rejected(app, admin):
    user = make_user()
    admin.post(f"/admin/users/{user.id}/role", data={"role": "superuser", "admin_password": "Password123"})
    assert db.session.get(User, user.id).role == "user"


def test_cannot_promote_inactive_user(app, admin):
    user = make_user(is_active=False)
    admin.post(f"/admin/users/{user.id}/role", data={"role": "admin", "admin_password": "Password123"})
    assert db.session.get(User, user.id).role == "user"


def test_admin_post_requires_csrf_when_enabled(app, admin):
    app.config["WTF_CSRF_ENABLED"] = True
    user = make_user()
    response = admin.post(f"/admin/users/{user.id}/status", data={"active": "0"})
    assert response.status_code in (302, 400)
    assert db.session.get(User, user.id).is_active is True


# ----------------------------------------------------------- categories
def test_categories_are_seeded_and_listed(app, admin):
    html = admin.get("/admin/categories").data
    assert b"Food" in html and b"Other" in html
    assert Category.query.count() == 11


def test_create_category_and_use_it_for_expenses(app, admin):
    admin.get("/admin/categories")  # seeds defaults
    response = admin.post("/admin/categories/new", data={"name": "Pets", "color": "#123456"}, follow_redirects=True)
    assert b"Category created" in response.data
    assert Category.query.filter_by(name="Pets").one().color == "#123456"
    # a normal user can now pick it
    make_user()
    admin.post("/logout")
    login(admin)
    r = admin.post("/expenses/add", data={**EXPENSE_FORM, "category": "Pets"}, follow_redirects=True)
    assert b"Expense added" in r.data


@pytest.mark.parametrize("name,color,message", [
    ("", "#123456", b"required"),
    ("Bad<script>", "#123456", b"may only contain"),
    ("Pets", "red", b"Colour must look like"),
    ("food", "#123456", b"already exists"),  # duplicate, case-insensitive
])
def test_category_validation(app, admin, name, color, message):
    admin.get("/admin/categories")
    response = admin.post("/admin/categories/new", data={"name": name, "color": color}, follow_redirects=True)
    assert message in response.data
    assert Category.query.count() == 11


def test_edit_and_rename_category_updates_existing_expenses(app, admin):
    admin.get("/admin/categories")
    user = make_user()
    db.session.add(Expense(user_id=user.id, expense_name="Lunch", category="Food", amount=100, date=date(2026, 10, 1)))
    db.session.commit()
    food = Category.query.filter_by(name="Food").one()
    admin.post(f"/admin/categories/{food.id}/edit", data={"name": "Meals", "color": "#abcdef"})
    assert Expense.query.one().category == "Meals"
    assert db.session.get(Category, food.id).color == "#abcdef"


def test_deactivating_category_preserves_expenses(app, admin):
    admin.get("/admin/categories")
    user = make_user()
    db.session.add(Expense(user_id=user.id, expense_name="Lunch", category="Food", amount=100, date=date(2026, 10, 1)))
    db.session.commit()
    food = Category.query.filter_by(name="Food").one()
    admin.post(f"/admin/categories/{food.id}/toggle")
    assert db.session.get(Category, food.id).is_active is False
    expense = Expense.query.one()
    assert expense.category == "Food" and expense.user_id == user.id  # untouched
    admin.post("/logout")
    login(admin)
    # the owner still sees it in history and can still edit the expense without changing the category
    assert b"Lunch" in admin.get("/expenses/?category=Food").data
    r = admin.post(f"/expenses/{expense.id}/edit", data={**EXPENSE_FORM, "category": "Food"}, follow_redirects=True)
    assert b"Expense updated" in r.data
    # ...but cannot pick the deactivated category for a NEW expense
    r = admin.post("/expenses/add", data={**EXPENSE_FORM, "category": "Food"}, follow_redirects=True)
    assert b"valid category" in r.data
    assert b'value="Food"' not in admin.get("/expenses/add").data


def test_fallback_category_cannot_be_deactivated_or_renamed(app, admin):
    admin.get("/admin/categories")
    other = Category.query.filter_by(name="Other").one()
    admin.post(f"/admin/categories/{other.id}/toggle")
    assert db.session.get(Category, other.id).is_active is True
    admin.post(f"/admin/categories/{other.id}/edit", data={"name": "Misc", "color": "#111111"})
    assert db.session.get(Category, other.id).name == "Other"


def test_ai_categorization_never_suggests_inactive_category(app, admin):
    admin.get("/admin/categories")
    transport = Category.query.filter_by(name="Transport").one()
    admin.post(f"/admin/categories/{transport.id}/toggle")
    admin.post("/logout")
    make_user()
    login(admin)
    data = admin.post("/expenses/categorize", json={"text": "Uber ride to university"}).get_json()
    assert data["category"] == "Other"


# ----------------------------------------------------------- dashboard + monitoring
def test_dashboard_counts_are_real(app, admin):
    make_user(email="b@example.com", is_active=False)
    u = make_user()
    db.session.add_all([Expense(user_id=u.id, expense_name="A", category="Food", amount=1, date=date(2026, 10, 1)),
                        Expense(user_id=u.id, expense_name="B", category="Food", amount=1, date=date(2026, 10, 2))])
    db.session.commit()
    from app.admin import services
    counts = services.overview_counts()
    assert counts["total_users"] == 3 and counts["active_users"] == 2 and counts["inactive_users"] == 1
    assert counts["total_expenses"] == 2 and counts["admins"] == 1
    charts = services.chart_payload()
    assert sum(charts["expense_counts"]) == 2 and sum(charts["category_counts"]) == 2
    assert b"Registered users" in admin.get("/admin/").data


def test_login_is_recorded_in_activity(app, admin):
    html = admin.get("/admin/").data
    assert b"user login" in html


def test_system_page_never_leaks_secrets(app, admin):
    app.config.update(AI_API_KEY="sk-super-secret-key", AI_MODEL="test-model", AI_BASE_URL="https://example.invalid/v1")
    html = admin.get("/admin/system").data.decode()
    assert "sk-super-secret-key" not in html and "SECRET_KEY" not in html
    assert "test-model" in html and "set (hidden)" in html
    assert "Connected" in html


def test_system_page_reports_unconfigured_and_failed_ai(app, admin, monkeypatch):
    assert b"Not configured" in admin.get("/admin/system").data
    app.config.update(AI_API_KEY="sk-secret-123", AI_MODEL="m", AI_BASE_URL="https://example.invalid/v1")
    import requests
    monkeypatch.setattr(requests, "post", lambda *a, **k: (_ for _ in ()).throw(requests.ConnectionError("boom sk-secret-123")))
    response = admin.post("/admin/system/test-ai", follow_redirects=True)
    assert b"AI test failed" in response.data and b"sk-secret-123" not in response.data
    assert b"most recent request failed" in admin.get("/admin/system").data


def test_403_page_for_user_does_not_reveal_admin_content(alice):
    response = alice.get("/admin/")
    assert response.status_code == 403 and b"Registered users" not in response.data


def test_json_clients_get_json_403(alice):
    response = alice.get("/admin/users", headers={"Accept": "application/json"})
    assert response.status_code == 403 and response.get_json()["error"]


# ----------------------------------------------------------- CLI
def test_create_admin_cli_creates_hashed_admin(app):
    runner = app.test_cli_runner()
    result = runner.invoke(args=["create-admin", "--email", "Boss@Example.com", "--name", "Boss",
                                 "--password", "StrongPass123"])
    assert result.exit_code == 0, result.output
    user = User.query.filter_by(email="boss@example.com").one()
    assert user.is_admin and user.is_active
    assert user.password_hash != "StrongPass123" and user.check_password("StrongPass123")


def test_create_admin_cli_rejects_weak_password_and_bad_email(app):
    runner = app.test_cli_runner()
    assert runner.invoke(args=["create-admin", "--email", "x@example.com", "--password", "short"]).exit_code != 0
    assert runner.invoke(args=["create-admin", "--email", "not-an-email", "--password", "StrongPass123"]).exit_code != 0
    assert User.query.count() == 0


def test_create_admin_cli_promotes_existing_user_only_with_their_password(app):
    make_user()
    runner = app.test_cli_runner()
    bad = runner.invoke(args=["create-admin", "--email", "alice@example.com", "--password", "WrongPass999"], input="y\n")
    assert bad.exit_code != 0 and not User.query.one().is_admin
    ok = runner.invoke(args=["create-admin", "--email", "alice@example.com", "--password", "Password123"], input="y\n")
    assert ok.exit_code == 0 and User.query.one().is_admin
