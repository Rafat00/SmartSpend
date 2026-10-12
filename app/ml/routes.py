"""Predictions page (ML forecast + unusual expense list)."""
from flask import Blueprint, render_template
from flask_login import current_user, login_required

from app.analytics.services import expenses_dataframe
from app.constants import DISCLAIMER
from app.ml.anomaly import find_unusual_expenses
from app.ml.prediction import predict_expenses

bp = Blueprint("ml", __name__, url_prefix="/predictions")


@bp.route("/")
@login_required
def predictions():
    df = expenses_dataframe(current_user.id)  # only this user's expenses
    prediction = predict_expenses(df)
    unusual = find_unusual_expenses(df)

    chart = None
    if prediction["status"] == "ok":
        labels = [h["label"] for h in prediction["history"]]
        values = [h["total"] for h in prediction["history"]]
        chart = {
            "labels": labels + [prediction["this_month"]["label"], prediction["next_month"]["label"]],
            "actual": values + [None, None],
            "estimate": [None] * len(values)
            + [prediction["this_month"]["estimate"], prediction["next_month"]["estimate"]],
        }
    return render_template(
        "predictions.html", prediction=prediction, unusual=unusual, chart=chart, disclaimer=DISCLAIMER
    )
