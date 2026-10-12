"""Expense prediction with scikit-learn.

How it works (simple version):
1. Group the user's expenses into COMPLETED calendar months (the current month is
   still incomplete, so it is not used for training).
2. Fit a regression model on the monthly totals:
     - 3-5 months of data : LinearRegression on the month number (a trend line)
     - 6+ months of data  : Ridge regression using month number, previous month's
                            total and previous month's number of transactions
3. Predict this month's full total and next month's total.
4. Compare with a naive baseline (average of the last 3 months).

These are ESTIMATES, not guarantees.
"""
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.metrics import mean_absolute_error
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from app.utils import add_months

MIN_MONTHS = 3
MIN_TRANSACTIONS = 10
INSUFFICIENT_MESSAGE = "Not enough data to make a reliable prediction."


def _completed_months(df: pd.DataFrame, today):
    """Monthly totals and transaction counts for completed months (zero-filled gaps)."""
    if df.empty:
        return None
    data = df.copy()
    data["month"] = data["date"].dt.to_period("M")
    current = pd.Period(today, freq="M")
    data = data[data["month"] < current]
    if data.empty:
        return None
    index = pd.period_range(data["month"].min(), current - 1, freq="M")
    totals = data.groupby("month")["amount"].sum().reindex(index, fill_value=0.0)
    counts = data.groupby("month")["amount"].count().reindex(index, fill_value=0)
    return data, totals, counts


def _forecast_totals(totals: pd.Series, counts: pd.Series, steps: int = 2):
    """Fit the model and forecast `steps` months ahead. Returns (predictions, mae, model_name)."""
    y = totals.to_numpy(dtype=float)
    c = counts.to_numpy(dtype=float)
    n = len(y)
    cap = max(2 * y.max(), 1.0)  # keep wild extrapolations under control

    def clamp(v):
        return float(min(max(v, 0.0), cap))

    if n >= 6:
        X = np.column_stack([np.arange(1, n), y[:-1], c[:-1]])  # month no., prev total, prev count
        target = y[1:]
        model = make_pipeline(StandardScaler(), Ridge(alpha=1.0)).fit(X, target)
        mae = mean_absolute_error(target, model.predict(X))
        prev_total, prev_count = y[-1], c[-1]
        preds = []
        for k in range(steps):
            p = clamp(model.predict(np.array([[n + k, prev_total, prev_count]]))[0])
            preds.append(p)
            prev_total = p  # next step uses the predicted total as its "previous month"
        name = "Ridge regression (month trend + previous month total + previous month transactions)"
    else:
        X = np.arange(n).reshape(-1, 1)
        model = LinearRegression().fit(X, y)
        mae = mean_absolute_error(y, model.predict(X))
        preds = [clamp(model.predict(np.array([[n + k]]))[0]) for k in range(steps)]
        name = "Linear regression (monthly trend line)"
    return preds, float(mae), name


def _category_estimates(data: pd.DataFrame, index: pd.PeriodIndex, steps_ahead: int = 1):
    """Estimate next month's spending per category."""
    result = []
    n = len(index)
    for category, group in data.groupby("category"):
        series = (
            group.groupby("month")["amount"].sum().reindex(index, fill_value=0.0).to_numpy(dtype=float)
        )
        nonzero = int((series > 0).sum())
        if nonzero >= 3:
            model = LinearRegression().fit(np.arange(n).reshape(-1, 1), series)
            estimate = float(model.predict(np.array([[n + steps_ahead]]))[0])
            method = "trend"
        else:
            estimate = float(series[-3:].mean())
            method = "3-month average"
        estimate = min(max(estimate, 0.0), max(2 * series.max(), 1.0))
        result.append(
            {
                "category": category,
                "estimate": round(estimate, 2),
                "last_month": round(float(series[-1]), 2),
                "method": method,
            }
        )
    result.sort(key=lambda r: -r["estimate"])
    return result


def _next_seven_days(df: pd.DataFrame, today):
    """Simple average-based estimate of spending over the next 7 days."""
    first = df["date"].min().date()
    if (today - first).days < 14:
        return None
    start = pd.Timestamp(today) - pd.Timedelta(days=27)
    window = df[(df["date"] >= start) & (df["date"] <= pd.Timestamp(today))]
    daily = window.groupby(window["date"].dt.date)["amount"].sum()
    average = float(daily.sum()) / 28.0
    return {"daily_average": round(average, 2), "estimate": round(average * 7, 2)}


def predict_expenses(df: pd.DataFrame, today=None) -> dict:
    """Main entry point. `df` comes from analytics.expenses_dataframe(user_id)."""
    from datetime import date as _date

    today = today or _date.today()
    transactions = len(df)
    prepared = _completed_months(df, today)
    months = 0 if prepared is None else len(prepared[1])

    if prepared is None or months < MIN_MONTHS or transactions < MIN_TRANSACTIONS:
        return {
            "status": "insufficient",
            "message": INSUFFICIENT_MESSAGE,
            "detail": (
                f"SmartSpend needs at least {MIN_MONTHS} completed months and {MIN_TRANSACTIONS} "
                f"expenses. You currently have {months} completed month(s) and {transactions} expense(s)."
            ),
        }

    data, totals, counts = prepared
    (this_month, next_month), mae, model_name = _forecast_totals(totals, counts, steps=2)
    baseline = float(totals.iloc[-3:].mean())
    this_label = today.strftime("%B %Y")
    next_label = add_months(today.replace(day=1), 1).strftime("%B %Y")

    history = [
        {"label": p.strftime("%b %Y"), "total": round(float(t), 2), "transactions": int(c)}
        for p, t, c in zip(totals.index[-12:], totals.to_numpy()[-12:], counts.to_numpy()[-12:])
    ]
    return {
        "status": "ok",
        "model": model_name,
        "months_used": months,
        "transactions_used": transactions,
        "this_month": {"label": this_label, "estimate": round(this_month, 2)},
        "next_month": {"label": next_label, "estimate": round(next_month, 2)},
        "baseline_3_month_avg": round(baseline, 2),
        "typical_error": round(mae, 2),
        "history": history,
        "categories": _category_estimates(data, totals.index)[:8],
        "next_7_days": _next_seven_days(df, today),
    }
