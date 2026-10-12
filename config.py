"""Application configuration.

All secrets (database password, SECRET_KEY, AI API key) are read from
environment variables / the .env file. Nothing sensitive is hard-coded here.
"""
import os

from dotenv import load_dotenv

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))


def _normalize_db_url(url: str) -> str:
    """Make sure SQLAlchemy uses the psycopg (v3) driver we install."""
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY") or "dev-only-change-me"

    SQLALCHEMY_DATABASE_URI = _normalize_db_url(
        os.environ.get("DATABASE_URL")
        or "postgresql+psycopg://postgres:YOUR_PASSWORD@localhost:5432/smartspend_db"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # pool_pre_ping drops dead connections instead of crashing after PostgreSQL restarts
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    # --- AI service (any OpenAI-compatible chat-completions API) ---
    AI_API_KEY = os.environ.get("AI_API_KEY", "").strip()
    AI_MODEL = os.environ.get("AI_MODEL", "").strip()
    AI_BASE_URL = os.environ.get("AI_BASE_URL", "https://api.groq.com/openai/v1").strip()
    AI_TIMEOUT = int(os.environ.get("AI_TIMEOUT", "30"))

    CURRENCY_SYMBOL = "৳"

    # Cookies / CSRF
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    WTF_CSRF_TIME_LIMIT = 60 * 60 * 8  # CSRF token valid for 8 hours


class TestConfig(Config):
    """Used by pytest only.

    Set TEST_DATABASE_URL to a *separate* PostgreSQL database (e.g. smartspend_test)
    to run the tests on PostgreSQL. If it is not set, an in-memory database is used
    so the tests run with zero setup. The real application always uses PostgreSQL.
    """

    TESTING = True
    SECRET_KEY = "test-secret-key"
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = _normalize_db_url(os.environ.get("TEST_DATABASE_URL") or "sqlite://")
    SQLALCHEMY_ENGINE_OPTIONS = {}
    AI_API_KEY = ""
    AI_MODEL = ""
