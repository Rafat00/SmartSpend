from datetime import date, timedelta
from decimal import Decimal

from app.extensions import db
from app.models import Expense
from tests.conftest import EXPENSE_FORM


def add(client, **overrides):
    data = {**EXPENSE_FORM, **overrides}
    return client.post("/expenses/add", data=data, follow_redirects=True)


def test_add_expense(alice, app):
    response = add(alice)
    assert b"Expense added successfully" in response.data
    expense = Expense.query.one()
    assert expense.expense_name == "Lunch"
    assert expense.amount == Decimal("250.00")
    assert expense.store == "Sultan's Dine"
    assert expense.date == date(2026, 10, 8)


def test_add_expense_validation(alice, app):
    assert b"Expense name cannot be empty" in add(alice, expense_name="  ").data
    assert b"valid number" in add(alice, amount="abc").data
    assert b"greater than zero" in add(alice, amount="-5").data
    assert b"greater than zero" in add(alice, amount="0").data
    assert b"not a valid date" in add(alice, date="2026-13-45").data
    assert b"valid category" in add(alice, category="Nonsense").data
    assert Expense.query.count() == 0


def test_edit_expense(alice, app):
    add(alice)
    expense = Expense.query.one()
    response = alice.post(
        f"/expenses/{expense.id}/edit",
        data={**EXPENSE_FORM, "expense_name": "Dinner", "amount": "400.50"},
        follow_redirects=True,
    )
    assert b"Expense updated" in response.data
    db.session.refresh(expense)
    assert expense.expense_name == "Dinner"
    assert expense.amount == Decimal("400.50")


def test_edit_with_invalid_data_keeps_old_values(alice, app):
    add(alice)
    expense = Expense.query.one()
    response = alice.post(f"/expenses/{expense.id}/edit", data={**EXPENSE_FORM, "amount": "oops"})
    assert b"valid number" in response.data
    db.session.refresh(expense)
    assert expense.amount == Decimal("250.00")


def test_delete_expense(alice, app):
    add(alice)
    expense = Expense.query.one()
    response = alice.post(f"/expenses/{expense.id}/delete", follow_redirects=True)
    assert b"Expense deleted" in response.data
    assert Expense.query.count() == 0


def test_search_and_filters(alice, app):
    add(alice, expense_name="Lunch", category="Food", store="Sultan's Dine", description="")
    add(alice, expense_name="Uber ride", category="Transport", store="Uber", amount="150", description="")
    add(alice, expense_name="Old shirt", category="Shopping", store="Mall", date="2026-01-05", description="")

    assert b"Uber ride" in alice.get("/expenses/?q=uber").data
    assert b"Lunch" not in alice.get("/expenses/?q=uber").data

    by_cat = alice.get("/expenses/?category=Shopping").data
    assert b"Old shirt" in by_cat and b"Uber ride" not in by_cat

    by_store = alice.get("/expenses/?store=sultan").data
    assert b"Lunch" in by_store and b"Old shirt" not in by_store

    by_date = alice.get("/expenses/?date_from=2026-10-01&date_to=2026-10-31").data
    assert b"Lunch" in by_date and b"Old shirt" not in by_date


def test_search_treats_percent_literally(alice, app):
    add(alice, expense_name="Lunch")
    assert b"Lunch" not in alice.get("/expenses/?q=%25").data  # '%' must not match everything


def test_csv_export(alice, app):
    add(alice)
    add(alice, expense_name="=HYPERLINK(\"http://x\")", store="Shop")
    response = alice.get("/expenses/export.csv")
    assert response.status_code == 200
    assert "attachment; filename=expenses.csv" in response.headers["Content-Disposition"]
    text = response.data.decode("utf-8-sig")
    lines = text.strip().splitlines()
    assert lines[0].startswith("date,expense_name,category,amount,store,payment_method")
    assert "2026-10-08,Lunch,Food,250.00,Sultan's Dine,Cash" in lines[1]
    assert "'=HYPERLINK" in text  # formula injection neutralised


def test_amount_helper_rounds_to_two_places(alice, app):
    add(alice, amount="10.555")
    assert Expense.query.one().amount == Decimal("10.56")


def test_edit_form_is_prefilled(alice, app):
    add(alice)
    expense = Expense.query.one()
    page = alice.get(f"/expenses/{expense.id}/edit")
    assert page.status_code == 200
    assert b'value="Lunch"' in page.data and b"250.00" in page.data


def test_error_pages(alice):
    assert alice.get("/does-not-exist").status_code == 404
