from datetime import date

from app.analytics.services import budget_status
from app.extensions import db
from app.models import Budget, Expense
from tests.conftest import make_user


def add_expense(user_id, amount, when=date(2026, 10, 5), category="Food"):
    db.session.add(Expense(user_id=user_id, expense_name="x", category=category, amount=amount, date=when))
    db.session.commit()


def test_budget_calculation_within_budget(app):
    user = make_user()
    db.session.add(Budget(user_id=user.id, year=2026, month=10, amount=30000))
    add_expense(user.id, 20000)
    add_expense(user.id, 2500, date(2026, 10, 20))
    add_expense(user.id, 9999, date(2026, 9, 30))  # other month: must be ignored

    status = budget_status(user.id, 2026, 10)
    assert status["budget"] == 30000
    assert status["spent"] == 22500
    assert status["remaining"] == 7500
    assert status["percent"] == 75.0
    assert status["exceeded"] is False


def test_budget_exceeded(app):
    user = make_user()
    db.session.add(Budget(user_id=user.id, year=2026, month=10, amount=1000))
    add_expense(user.id, 1500)
    status = budget_status(user.id, 2026, 10)
    assert status["exceeded"] is True
    assert status["remaining"] == -500
    assert status["over_by"] == 500


def test_no_budget_set(app):
    user = make_user()
    add_expense(user.id, 100)
    status = budget_status(user.id, 2026, 10)
    assert status["has_budget"] is False
    assert status["remaining"] is None
    assert status["spent"] == 100


def test_set_budget_via_route_and_update(alice, app):
    r = alice.post("/budget/", data={"month": "10", "year": "2026", "amount": "30000"}, follow_redirects=True)
    assert b"saved" in r.data
    assert Budget.query.one().amount == 30000

    alice.post("/budget/", data={"month": "10", "year": "2026", "amount": "35000"})
    assert Budget.query.count() == 1  # updated, not duplicated
    assert Budget.query.one().amount == 35000


def test_invalid_budget_rejected(alice, app):
    r = alice.post("/budget/", data={"month": "10", "year": "2026", "amount": "-10"}, follow_redirects=True)
    assert b"greater than zero" in r.data
    r = alice.post("/budget/", data={"month": "10", "year": "2026", "amount": "abc"}, follow_redirects=True)
    assert b"valid number" in r.data
    assert Budget.query.count() == 0


def test_exceeded_warning_shown_on_budget_page(alice, app):
    from app.models import User

    uid = User.query.one().id
    today = date.today()
    db.session.add(Budget(user_id=uid, year=today.year, month=today.month, amount=100))
    add_expense(uid, 500, today)
    page = alice.get("/budget/").data
    assert "exceeded your monthly budget".encode() in page
