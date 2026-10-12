"""Rule-based fallbacks. These keep SmartSpend useful when the AI API is
missing, down, or out of quota. No network calls happen in this file."""
import re

from app import categories as category_service
from app.utils import format_money

# (category, subcategory, keywords). First match wins, so order matters.
KEYWORD_RULES = [
    ("Groceries", "Groceries", ["grocery", "groceries", "vegetable", "vegetables", "rice", "egg",
                                "eggs", "milk", "bazar", "bazaar", "supermarket", "shwapno",
                                "agora", "meena bazar", "fruits"]),
    ("Food", "Fast Food", ["burger", "pizza", "kfc", "fries", "sandwich", "shawarma", "fuchka"]),
    ("Food", "Cafe", ["coffee", "tea", "cafe", "juice", "bubble tea", "smoothie"]),
    ("Food", "Restaurant", ["kacchi", "biryani", "tehari", "khichuri", "lunch", "dinner",
                            "breakfast", "restaurant", "dine", "meal", "food", "foodpanda",
                            "snack", "snacks", "chicken", "iftar", "buffet"]),
    ("Transport", "Ride Sharing", ["uber", "pathao", "obhai", "ride", "taxi"]),
    ("Transport", "Public Transport", ["bus", "rickshaw", "cng", "train", "metro", "launch", "fare"]),
    ("Transport", "Fuel", ["fuel", "petrol", "octane", "diesel", "parking"]),
    ("Rent", "Housing", ["rent", "house rent", "hostel", "mess"]),
    ("Bills", "Utilities", ["electricity", "wifi", "internet", "broadband", "water bill", "gas bill",
                            "bill", "utility", "dish line"]),
    ("Bills", "Mobile", ["recharge", "mobile recharge", "top up", "topup", "data pack", "sim"]),
    ("Health", "Medical", ["doctor", "medicine", "pharmacy", "hospital", "clinic", "dental",
                           "medical", "checkup", "lab test", "diagnostic"]),
    ("Education", "Study", ["tuition", "course", "book", "books", "exam", "semester", "stationery",
                            "udemy", "coursera", "tution", "admission", "lab fee", "university fee"]),
    ("Entertainment", "Leisure", ["movie", "cinema", "netflix", "spotify", "game", "concert",
                                  "youtube", "party", "subscription", "gaming"]),
    ("Travel", "Trip", ["hotel", "flight", "trip", "tour", "resort", "booking", "ticket", "vacation"]),
    ("Shopping", "Clothing", ["shirt", "tshirt", "t-shirt", "shoes", "dress", "clothes", "jeans",
                              "panjabi", "saree", "jacket", "fashion"]),
    ("Shopping", "General", ["shopping", "mall", "amazon", "daraz", "gadget", "bag", "watch",
                             "headphone", "headphones", "phone", "charger", "bought"]),
]


def categorize_by_rules(text: str) -> tuple[str, str | None]:
    lowered = text.lower()
    for category, subcategory, words in KEYWORD_RULES:
        for word in words:
            if re.search(rf"(?<![a-z0-9]){re.escape(word)}(?![a-z0-9])", lowered):
                return category, subcategory
    return "Other", None


# ------------------------------------------------------------- analysis
def analysis_by_rules(summary: dict) -> dict:
    cur = summary["current_month"]
    prev = summary["previous_month"]
    cats = summary["category_current_month"]
    change = summary["category_change_percent_vs_previous_month"]

    if summary["total_transactions_all_time"] == 0 or (cur["total"] == 0 and prev["total"] == 0):
        return {
            "highest_category": "No spending recorded for this month or last month yet.",
            "rapidly_increasing": [],
            "possible_unnecessary": [],
            "saving_suggestions": ["Add a few expenses first, then come back for an analysis."],
            "month_comparison": "There is not enough data to compare months yet.",
        }

    if cats:
        top_cat, top_val = max(cats.items(), key=lambda kv: kv[1])
        share = top_val / cur["total"] * 100 if cur["total"] else 0
        highest = f"{top_cat} is your highest category this month at {format_money(top_val)} ({share:.0f}% of spending)."
    else:
        top_cat, highest = None, "No spending recorded yet this month."

    rising = []
    for cat, pct in change.items():
        now = cats.get(cat, 0.0)
        if pct is not None and pct >= 25 and now > 0:
            rising.append(f"{cat} is up {pct:.0f}% compared with last month ({format_money(now)} so far).")

    unnecessary = []
    discretionary = sum(cats.get(c, 0.0) for c in ("Shopping", "Entertainment"))
    if cur["total"] and discretionary / cur["total"] >= 0.25:
        unnecessary.append(
            f"Shopping and Entertainment add up to {format_money(discretionary)} "
            f"({discretionary / cur['total'] * 100:.0f}% of this month) - review whether all of it was planned."
        )
    big = summary["largest_expenses_current_month"]
    if big:
        b = big[0]
        unnecessary.append(f"Your largest expense this month was '{b['name']}' ({format_money(b['amount'])}). Check it was worth it.")

    tips = []
    if top_cat:
        tips.append(f"Set a small weekly limit for {top_cat}; it is where most of your money goes.")
    if "Food" in cats and cats["Food"] > 0:
        tips.append("Try cooking or packing meals a few days a week to cut restaurant spending.")
    tips.append("Record every expense the same day so your totals stay accurate.")
    budget = summary.get("budget_current_month")
    if budget and budget["exceeded"]:
        tips.append(f"You are {format_money(budget['over_by'])} over budget - pause non-essential purchases for the rest of the month.")
    elif not budget:
        tips.append("Set a monthly budget so SmartSpend can warn you before you overspend.")

    if prev["total"] > 0:
        diff = cur["total"] - prev["total"]
        pct = diff / prev["total"] * 100
        direction = "more" if diff > 0 else "less"
        comparison = (
            f"{cur['label']} so far: {format_money(cur['total'])} vs {prev['label']} total: "
            f"{format_money(prev['total'])} ({abs(pct):.0f}% {direction}; the month is only {cur['days_elapsed']} days in)."
        )
    else:
        comparison = "There is no spending recorded for last month to compare against."

    return {
        "highest_category": highest,
        "rapidly_increasing": rising,
        "possible_unnecessary": unnecessary,
        "saving_suggestions": tips,
        "month_comparison": comparison,
    }


# ------------------------------------------------------------- chat
def answer_by_rules(question: str, summary: dict) -> str:
    q = question.lower()
    cur, prev = summary["current_month"], summary["previous_month"]
    cur_cats, prev_cats = summary["category_current_month"], summary["category_previous_month"]

    if summary["total_transactions_all_time"] == 0:
        return "You have no expenses recorded yet. Add some expenses and then ask me again."

    asked_category = next((c for c in category_service.all_category_names() if re.search(rf"\b{re.escape(c.lower())}\b", q)), None)
    wants_last = any(w in q for w in ("last month", "previous month"))

    if asked_category and any(w in q for w in ("spend", "spent", "how much", "total")):
        if wants_last:
            return f"You spent {format_money(prev_cats.get(asked_category, 0))} on {asked_category} in {prev['label']}."
        return f"You have spent {format_money(cur_cats.get(asked_category, 0))} on {asked_category} so far in {cur['label']}."

    if any(w in q for w in ("increase", "increased", "rise", "rose", "grew", "growth", "up the most")):
        changes = {c: p for c, p in summary["category_change_percent_vs_previous_month"].items() if p is not None}
        if not changes:
            return "I need spending in both this month and last month to compare categories."
        cat, pct = max(changes.items(), key=lambda kv: kv[1])
        return f"{cat} increased the most: {pct:+.0f}% compared with {prev['label']} ({format_money(cur_cats.get(cat, 0))} vs {format_money(prev_cats.get(cat, 0))})."

    if any(w in q for w in ("where", "store", "place", "shop")) and any(w in q for w in ("most", "highest", "top")):
        stores = summary["top_stores_current_month"] or summary["top_stores_all_time"]
        if not stores:
            return "You have not recorded any store names yet."
        s = stores[0]
        scope = cur["label"] if summary["top_stores_current_month"] else "all time"
        noun = "purchase" if s["count"] == 1 else "purchases"
        return f"Your top store/place ({scope}) is {s['store']} with {format_money(s['total'])} across {s['count']} {noun}."

    if any(w in q for w in ("category", "categories")) and any(w in q for w in ("most", "highest", "top", "biggest")):
        if cur_cats:
            cat, val = max(cur_cats.items(), key=lambda kv: kv[1])
            return f"Your highest category in {cur['label']} is {cat} at {format_money(val)}."
        return "No spending recorded in the current month yet."

    if wants_last:
        return f"You spent {format_money(prev['total'])} in {prev['label']} across {prev['transactions']} transactions."

    if any(w in q for w in ("suggest", "reduce", "save", "saving", "tips", "cut", "advice")):
        analysis = analysis_by_rules(summary)
        lines = analysis["saving_suggestions"] + analysis["possible_unnecessary"]
        return "Here are some ideas based on your data:\n- " + "\n- ".join(lines)

    if any(w in q for w in ("this month", "so far", "total", "how much")):
        return f"You have spent {format_money(cur['total'])} in {cur['label']} across {cur['transactions']} transactions."

    return (
        "I can answer questions like: 'How much did I spend on food this month?', "
        "'Where did I spend the most money?', 'How much did I spend last month?', "
        "'What category increased the most?' or 'Give me suggestions to reduce my expenses.'"
    )
