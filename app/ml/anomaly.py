"""Unusual (abnormally HIGH) expense detection with Isolation Forest.

Isolation Forest is an unsupervised model that isolates points which are far
from the rest. We train it on the log of past amounts (log makes ৳500 vs ৳8,000
comparable). On its own it would flag the top tail of ANY spending pattern, so an
amount is only reported when ALL of these are true:
  1. the Isolation Forest labels it an outlier, and
  2. it is above the IQR "fence"  (Q3 + 1.5 x IQR, the classic box-plot rule), and
  3. it is at least 50% above the 75th percentile (avoids flagging tiny rises,
     e.g. rent going from ৳6,500 to ৳6,600).
Cheap expenses are never reported as "unusual".

Scope: we compare against the same category when there are enough examples,
otherwise against all of the user's expenses.
"""
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from app.analytics.services import expenses_dataframe
from app.utils import format_money

MIN_CATEGORY_SAMPLES = 8
MIN_GLOBAL_SAMPLES = 10


def _high_outlier_mask(history: np.ndarray, candidates: np.ndarray) -> np.ndarray:
    """True for each candidate amount that looks unusually high compared with `history`."""
    model = IsolationForest(n_estimators=200, contamination="auto", random_state=42)
    model.fit(np.log1p(history).reshape(-1, 1))
    is_outlier = model.predict(np.log1p(candidates).reshape(-1, 1)) == -1

    q1, q3 = np.percentile(history, [25, 75])
    iqr_fence = q3 + 1.5 * (q3 - q1)
    threshold = max(iqr_fence, 1.5 * q3)
    return is_outlier & (candidates > threshold)


def _usual_range(history: np.ndarray) -> tuple[float, float]:
    return float(np.percentile(history, 10)), float(np.percentile(history, 90))


def check_new_expense(user_id: int, expense) -> dict:
    """Is this (just saved) expense unusually high compared with the user's PAST expenses?"""
    df = expenses_dataframe(user_id)
    df = df[df["id"] != expense.id]  # compare against everything except itself
    amount = float(expense.amount)

    same_cat = df[df["category"] == expense.category]["amount"].to_numpy(dtype=float)
    if len(same_cat) >= MIN_CATEGORY_SAMPLES:
        history, scope = same_cat, f"{expense.category} spending"
    elif len(df) >= MIN_GLOBAL_SAMPLES:
        history, scope = df["amount"].to_numpy(dtype=float), "spending"
    else:
        return {"checked": False, "unusual": False, "message": None}

    unusual = bool(_high_outlier_mask(history, np.array([amount]))[0])
    if not unusual:
        return {"checked": True, "unusual": False, "message": None}

    low, high = _usual_range(history)
    message = (
        f"⚠️ This expense ({format_money(amount)}) is unusually high compared with your previous "
        f"{scope} (usually {format_money(low)}–{format_money(high)})."
    )
    return {"checked": True, "unusual": True, "message": message, "usual_low": low, "usual_high": high}


def find_unusual_expenses(df: pd.DataFrame, limit: int = 10) -> list[dict]:
    """Scan ALL of a user's expenses and list the unusually high ones."""
    if len(df) < MIN_GLOBAL_SAMPLES:
        return []

    flagged = pd.Series(False, index=df.index)
    scope_range = {}
    handled = pd.Series(False, index=df.index)

    for category, group in df.groupby("category"):
        if len(group) >= MIN_CATEGORY_SAMPLES:
            amounts = group["amount"].to_numpy(dtype=float)
            flagged.loc[group.index] = _high_outlier_mask(amounts, amounts)
            handled.loc[group.index] = True
            lo, hi = _usual_range(amounts)
            for idx in group.index:
                scope_range[idx] = (lo, hi, category)

    rest = df[~handled]
    if not rest.empty:
        all_amounts = df["amount"].to_numpy(dtype=float)
        flagged.loc[rest.index] = _high_outlier_mask(all_amounts, rest["amount"].to_numpy(dtype=float))
        lo, hi = _usual_range(all_amounts)
        for idx in rest.index:
            scope_range[idx] = (lo, hi, "all expenses")

    result = []
    for idx, row in df[flagged].sort_values("date", ascending=False).iterrows():
        lo, hi, scope = scope_range[idx]
        result.append(
            {
                "id": int(row["id"]),
                "date": row["date"].date().isoformat(),
                "category": row["category"],
                "store": row["store"] or "",
                "amount": round(float(row["amount"]), 2),
                "usual_low": round(lo, 2),
                "usual_high": round(hi, 2),
                "scope": scope,
            }
        )
    return result[:limit]
