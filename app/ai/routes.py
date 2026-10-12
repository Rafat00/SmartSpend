"""AI pages: spending analysis and chatbot."""
from flask import Blueprint, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.ai import ai_service
from app.analytics.services import build_ai_summary
from app.constants import DISCLAIMER

bp = Blueprint("ai", __name__, url_prefix="/ai")

SUGGESTED_QUESTIONS = [
    "How much did I spend on food this month?",
    "Where did I spend the most money?",
    "How much did I spend last month?",
    "What category increased the most?",
    "Give me some suggestions to reduce my expenses.",
]


@bp.route("/")
@login_required
def index():
    return redirect(url_for("ai.chat"))


@bp.route("/analysis", methods=["GET", "POST"])
@login_required
def analysis():
    # The summary is built ONLY from the logged-in user's rows.
    summary = build_ai_summary(current_user.id)
    result = None
    if request.method == "POST":  # AI is only called when the user clicks the button
        result = ai_service.analyze_spending(summary)
    return render_template("ai/analysis.html", summary=summary, result=result, disclaimer=DISCLAIMER)


@bp.route("/chat")
@login_required
def chat():
    return render_template("ai/chat.html", suggestions=SUGGESTED_QUESTIONS, disclaimer=DISCLAIMER)


@bp.route("/chat/ask", methods=["POST"])
@login_required
def chat_ask():
    payload = request.get_json(silent=True) or {}
    message = str(payload.get("message", "")).strip()
    if not message:
        return jsonify(error="Please type a question."), 400
    if len(message) > 500:
        return jsonify(error="Please keep your question under 500 characters."), 400

    summary = build_ai_summary(current_user.id)  # only this user's data
    return jsonify(ai_service.answer_question(message, summary, payload.get("history")))
