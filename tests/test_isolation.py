"""Each user must only ever see / change their own data."""
from app.analytics.services import build_ai_summary, budget_status, expenses_dataframe
from app.extensions import db
from app.models import Budget, Expense
from tests.conftest import EXPENSE_FORM, login, make_user


def setup_two_users(app, client):
    alice = make_user("alice@example.com", "Alice")
    bob = make_user("bob@example.com", "Bob")
    login(client, "alice@example.com")
    client.post("/expenses/add", data={**EXPENSE_FORM, "expense_name": "Alice Secret Lunch", "amount": "999"})
    client.post("/logout")
    login(client, "bob@example.com")
    return alice, bob


def test_user_cannot_see_other_users_expenses(app, client):
    setup_two_users(app, client)
    assert b"Alice Secret Lunch" not in client.get("/expenses/").data
    assert b"Alice Secret Lunch" not in client.get("/dashboard").data


def test_user_cannot_edit_or_delete_other_users_expense(app, client):
    setup_two_users(app, client)
    victim = Expense.query.filter_by(expense_name="Alice Secret Lunch").one()

    assert client.get(f"/expenses/{victim.id}/edit").status_code == 404
    assert client.post(f"/expenses/{victim.id}/edit", data={**EXPENSE_FORM, "expense_name": "Hacked"}).status_code == 404
    assert client.post(f"/expenses/{victim.id}/delete").status_code == 404

    db.session.refresh(victim)
    assert victim.expense_name == "Alice Secret Lunch"


def test_csv_export_only_contains_own_data(app, client):
    setup_two_users(app, client)
    text = client.get("/expenses/export.csv").data.decode("utf-8-sig")
    assert "Alice Secret Lunch" not in text
    assert len(text.strip().splitlines()) == 1  # header only


def test_ai_summary_and_dataframe_are_per_user(app, client):
    alice, bob = setup_two_users(app, client)
    assert build_ai_summary(alice.id)["total_transactions_all_time"] == 1
    bob_summary = build_ai_summary(bob.id)
    assert bob_summary["total_transactions_all_time"] == 0
    assert "Alice" not in str(bob_summary)
    assert expenses_dataframe(bob.id).empty
    assert len(expenses_dataframe(alice.id)) == 1


def test_chat_endpoint_uses_only_logged_in_users_data(app, client):
    setup_two_users(app, client)  # logged in as Bob, who has no expenses
    response = client.post("/ai/chat/ask", json={"message": "How much did I spend this month?"})
    assert response.status_code == 200
    reply = response.get_json()["reply"]
    assert "999" not in reply
    assert "no expenses" in reply.lower()


def test_budgets_are_per_user(app, client):
    alice, bob = setup_two_users(app, client)
    db.session.add(Budget(user_id=alice.id, year=2026, month=10, amount=5000))
    db.session.commit()
    assert budget_status(bob.id, 2026, 10)["has_budget"] is False
    assert b"5000" not in client.get("/budget/?year=2026&month=10").data
    # Bob cannot delete Alice's budget
    budget_id = Budget.query.filter_by(user_id=alice.id).one().id
    assert client.post(f"/budget/{budget_id}/delete").status_code == 404
    assert Budget.query.count() == 1
