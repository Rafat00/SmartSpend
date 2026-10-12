from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from app.ai import ai_service
from app.ai.ai_service import AIServiceError
from app.ai.fallback import categorize_by_rules
from app.analytics.services import build_ai_summary, expenses_dataframe
from app.extensions import db
from app.ml.anomaly import check_new_expense, find_unusual_expenses
from app.ml.prediction import INSUFFICIENT_MESSAGE, predict_expenses
from app.models import Expense
from app.utils import add_months
from tests.conftest import make_user


# ---------------------------------------------------------------- categorization
@pytest.mark.parametrize("text,category", [
    ("Bought Kacchi from Sultan's Dine", "Food"),
    ("Uber ride to university", "Transport"),
    ("Monthly wifi bill", "Bills"),
    ("Paracetamol from pharmacy", "Health"),
    ("Something totally unknown xyz", "Other"),
])
def test_rule_based_categorization(text, category):
    assert categorize_by_rules(text)[0] == category


def test_categorize_falls_back_when_ai_not_configured(app):
    with app.test_request_context():
        result = ai_service.categorize_expense("Bought Kacchi from Sultan's Dine")
    assert result["category"] == "Food"
    assert result["subcategory"] == "Restaurant"
    assert result["source"] == "rules"
    assert "not configured" in result["notice"]


def test_categorize_endpoint(alice):
    response = alice.post("/expenses/categorize", json={"text": "Uber ride to university"})
    assert response.status_code == 200
    assert response.get_json()["category"] == "Transport"
    assert alice.post("/expenses/categorize", json={"text": ""}).status_code == 400


# ---------------------------------------------------------------- AI failure handling
def configure_ai(app):
    app.config.update(AI_API_KEY="test-key", AI_MODEL="test-model")


def test_ai_failure_falls_back_gracefully(app, monkeypatch):
    configure_ai(app)

    def boom(self, *a, **k):
        raise AIServiceError("down")

    monkeypatch.setattr(ai_service.LLMClient, "complete", boom)
    user = make_user()
    with app.test_request_context():
        summary = build_ai_summary(user.id)
        assert ai_service.categorize_expense("Uber ride")["source"] == "rules"
        analysis = ai_service.analyze_spending(summary)
        chat = ai_service.answer_question("How much did I spend last month?", summary)
    assert analysis["source"] == "rules" and "unavailable" in analysis["notice"]
    assert chat["source"] == "rules" and chat["reply"]


def test_ai_success_path_with_mocked_llm(app, monkeypatch):
    configure_ai(app)
    answers = iter([
        '{"category": "Transport", "subcategory": "Ride Sharing"}',
        '```json\n{"highest_category": "Food", "rapidly_increasing": ["Food +30%"], '
        '"possible_unnecessary": [], "saving_suggestions": ["Cook more"], "month_comparison": "Up"}\n```',
        "You spent about ৳500.",
    ])
    monkeypatch.setattr(ai_service.LLMClient, "complete", lambda self, *a, **k: next(answers))
    user = make_user()
    with app.test_request_context():
        summary = build_ai_summary(user.id)
        assert ai_service.categorize_expense("Pathao")["source"] == "ai"
        analysis = ai_service.analyze_spending(summary)
        assert analysis["source"] == "ai"
        assert analysis["analysis"]["saving_suggestions"] == ["Cook more"]
        assert ai_service.answer_question("hi", summary)["reply"] == "You spent about ৳500."


def test_ai_bad_category_from_llm_is_rejected(app, monkeypatch):
    configure_ai(app)
    monkeypatch.setattr(ai_service.LLMClient, "complete", lambda self, *a, **k: '{"category": "Spaceships"}')
    with app.test_request_context():
        result = ai_service.categorize_expense("Uber ride")
    assert result["source"] == "rules" and result["category"] == "Transport"


def test_pages_work_without_ai_configured(alice):
    assert alice.get("/ai/chat").status_code == 200
    page = alice.post("/ai/analysis")
    assert page.status_code == 200
    assert b"rule-based" in page.data.lower()
    reply = alice.post("/ai/chat/ask", json={"message": "Give me suggestions"}).get_json()
    assert reply["source"] == "rules"
    assert alice.post("/ai/chat/ask", json={"message": ""}).status_code == 400


# ---------------------------------------------------------------- prediction
def seed_months(user_id, months=7, per_month=6, base=10000, step=500):
    today = date.today()
    first = today.replace(day=1)
    for i in range(months, 0, -1):
        m = add_months(first, -i)
        total = base + (months - i) * step
        for k in range(per_month):
            db.session.add(Expense(user_id=user_id, expense_name="e", category="Food" if k % 2 else "Transport",
                                   amount=total / per_month, date=m.replace(day=3 + k), store="S"))
    db.session.commit()


def test_prediction_insufficient_data(app):
    user = make_user()
    result = predict_expenses(expenses_dataframe(user.id))
    assert result["status"] == "insufficient"
    assert result["message"] == INSUFFICIENT_MESSAGE


def test_prediction_with_few_months_is_insufficient(app):
    user = make_user()
    seed_months(user.id, months=2, per_month=8)
    assert predict_expenses(expenses_dataframe(user.id))["status"] == "insufficient"


def test_prediction_trend_model(app):
    user = make_user()
    seed_months(user.id, months=4, per_month=6, base=10000, step=1000)  # 10k, 11k, 12k, 13k
    result = predict_expenses(expenses_dataframe(user.id))
    assert result["status"] == "ok"
    assert "Linear regression" in result["model"]
    assert result["this_month"]["estimate"] == pytest.approx(14000, rel=0.02)
    assert result["next_month"]["estimate"] == pytest.approx(15000, rel=0.02)


def test_prediction_ridge_model_with_enough_history(app):
    user = make_user()
    seed_months(user.id, months=8, per_month=6, base=10000, step=500)
    result = predict_expenses(expenses_dataframe(user.id))
    assert result["status"] == "ok"
    assert "Ridge" in result["model"]
    assert 0 < result["next_month"]["estimate"] < 40000
    assert result["categories"]


def test_predictions_page_renders(alice, app):
    assert b"Not enough data to make a reliable prediction." in alice.get("/predictions/").data
    from app.models import User
    seed_months(User.query.one().id, months=5)
    page = alice.get("/predictions/")
    assert b"Estimated spending next month" in page.data and b"Estimate" in page.data


# ---------------------------------------------------------------- anomaly detection
def seed_shopping(user_id, n=15):
    rng = np.random.default_rng(1)
    for i in range(n):
        db.session.add(Expense(user_id=user_id, expense_name="Shirt", category="Shopping",
                               amount=float(rng.uniform(500, 2000)), date=date.today() - timedelta(days=i + 1)))
    db.session.commit()


def test_unusual_high_expense_is_flagged(app):
    user = make_user()
    seed_shopping(user.id)
    big = Expense(user_id=user.id, expense_name="Laptop bag", category="Shopping", amount=8000, date=date.today())
    db.session.add(big)
    db.session.commit()
    result = check_new_expense(user.id, big)
    assert result["unusual"] is True
    assert "unusually high" in result["message"]


def test_normal_and_cheap_expenses_not_flagged(app):
    user = make_user()
    seed_shopping(user.id)
    normal = Expense(user_id=user.id, expense_name="Shirt", category="Shopping", amount=1200, date=date.today())
    cheap = Expense(user_id=user.id, expense_name="Socks", category="Shopping", amount=20, date=date.today())
    db.session.add_all([normal, cheap])
    db.session.commit()
    assert check_new_expense(user.id, normal)["unusual"] is False
    assert check_new_expense(user.id, cheap)["unusual"] is False


def test_anomaly_check_needs_enough_history(app):
    user = make_user()
    e = Expense(user_id=user.id, expense_name="Big", category="Shopping", amount=90000, date=date.today())
    db.session.add(e)
    db.session.commit()
    assert check_new_expense(user.id, e) == {"checked": False, "unusual": False, "message": None}


def test_find_unusual_expenses_lists_outlier(app):
    user = make_user()
    seed_shopping(user.id)
    db.session.add(Expense(user_id=user.id, expense_name="Laptop bag", category="Shopping", amount=8000, date=date.today()))
    db.session.commit()
    found = find_unusual_expenses(expenses_dataframe(user.id))
    assert [f["amount"] for f in found] == [8000.0]


def test_adding_unusual_expense_shows_warning(alice, app):
    from app.models import User
    seed_shopping(User.query.one().id)
    response = alice.post("/expenses/add", follow_redirects=True, data={
        "expense_name": "Laptop bag", "category": "Shopping", "amount": "8000",
        "date": date.today().isoformat(), "payment_method": "Card",
    })
    assert "unusually high".encode() in response.data


def test_normal_variation_is_not_flagged_as_unusual(app):
    """Regression: the top of a normal spending range must not be reported."""
    user = make_user()
    rng = np.random.default_rng(7)
    for i in range(60):  # groceries between 700 and 1800, like real shopping trips
        db.session.add(Expense(user_id=user.id, expense_name="Groceries", category="Groceries",
                               amount=float(rng.uniform(700, 1800)), date=date.today() - timedelta(days=i)))
    db.session.commit()
    assert find_unusual_expenses(expenses_dataframe(user.id)) == []


def test_tiny_rise_in_fixed_expense_is_not_flagged(app):
    user = make_user()
    for i in range(12):
        db.session.add(Expense(user_id=user.id, expense_name="Rent", category="Rent", amount=6500,
                               date=date.today() - timedelta(days=30 * i)))
    bumped = Expense(user_id=user.id, expense_name="Rent", category="Rent", amount=6700, date=date.today())
    db.session.add(bumped)
    db.session.commit()
    assert check_new_expense(user.id, bumped)["unusual"] is False


# ---------------------------------------------------------------- real HTTP client vs. a fake provider
import json as _json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer


def _start_fake_llm(reject_response_format=False, status=200):
    seen = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = _json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            seen.append({"path": self.path, "auth": self.headers.get("Authorization"), "body": body})
            if reject_response_format and "response_format" in body:
                self.send_response(400); self.end_headers(); self.wfile.write(b'{"error":"unsupported"}'); return
            if status != 200:
                self.send_response(status); self.end_headers(); self.wfile.write(b'{"error":"nope"}'); return
            content = '{"category": "Food", "subcategory": "Restaurant"}'
            payload = _json.dumps({"choices": [{"message": {"content": content}}]}).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, seen


def test_http_client_speaks_openai_format_and_retries_without_response_format(app):
    server, seen = _start_fake_llm(reject_response_format=True)
    try:
        app.config.update(AI_API_KEY="secret-key", AI_MODEL="m1", AI_BASE_URL=f"http://127.0.0.1:{server.server_port}/v1")
        with app.test_request_context():
            result = ai_service.categorize_expense("Kacchi")
    finally:
        server.shutdown()
    assert result["source"] == "ai" and result["category"] == "Food"
    assert seen[0]["path"] == "/v1/chat/completions"
    assert seen[0]["auth"] == "Bearer secret-key"
    assert seen[0]["body"]["model"] == "m1"
    assert "response_format" in seen[0]["body"] and "response_format" not in seen[1]["body"]  # retried


def test_http_error_from_provider_falls_back(app):
    server, _ = _start_fake_llm(status=500)
    try:
        app.config.update(AI_API_KEY="k", AI_MODEL="m", AI_BASE_URL=f"http://127.0.0.1:{server.server_port}/v1")
        with app.test_request_context():
            result = ai_service.categorize_expense("Uber ride")
    finally:
        server.shutdown()
    assert result["source"] == "rules" and result["category"] == "Transport"
    assert "unavailable" in result["notice"]


def test_unreachable_provider_falls_back(app):
    app.config.update(AI_API_KEY="k", AI_MODEL="m", AI_BASE_URL="http://127.0.0.1:9/v1", AI_TIMEOUT=2)
    with app.test_request_context():
        result = ai_service.categorize_expense("Uber ride")
    assert result["source"] == "rules"
