"""Shared constants used by forms, AI and analytics."""
from decimal import Decimal

CATEGORIES = [
    "Food",
    "Groceries",
    "Transport",
    "Shopping",
    "Bills",
    "Rent",
    "Health",
    "Education",
    "Entertainment",
    "Travel",
    "Other",
]

PAYMENT_METHODS = ["Cash", "Card", "bKash", "Nagad", "Rocket", "Bank Transfer", "Other"]

CATEGORY_COLORS = {
    "Food": "#f97316",
    "Groceries": "#84cc16",
    "Transport": "#0ea5e9",
    "Shopping": "#ec4899",
    "Bills": "#8b5cf6",
    "Rent": "#64748b",
    "Health": "#ef4444",
    "Education": "#14b8a6",
    "Entertainment": "#eab308",
    "Travel": "#6366f1",
    "Other": "#94a3b8",
}

MAX_AMOUNT = Decimal("10000000")  # 1 crore - guards against typos like 25000000000

DISCLAIMER = (
    "SmartSpend's AI insights and predictions are automatically generated estimates "
    "based only on the data you entered. They are not guaranteed and are not "
    "professional financial advice."
)
