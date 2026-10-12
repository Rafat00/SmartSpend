"""Tiny in-memory health tracker for the admin "System Monitoring" page.

Only generic, already-sanitised messages are stored (never API keys, request bodies,
user data or stack traces). State is per server process and resets on restart.
"""
import threading
from collections import deque
from datetime import datetime, timezone

_lock = threading.Lock()
STARTED_AT = datetime.now(timezone.utc)

_state = {
    "ai_success": 0,
    "ai_failure": 0,
    "ai_last_success": None,
    "ai_last_failure": None,
    "server_errors": 0,
    "last_server_error": None,
}
_recent_ai_errors = deque(maxlen=10)


def _now():
    return datetime.now(timezone.utc)


def record_ai_success() -> None:
    with _lock:
        _state["ai_success"] += 1
        _state["ai_last_success"] = _now()


def record_ai_failure(message: str) -> None:
    with _lock:
        _state["ai_failure"] += 1
        _state["ai_last_failure"] = _now()
        _recent_ai_errors.appendleft((_now(), str(message)[:120]))


def record_server_error() -> None:
    with _lock:
        _state["server_errors"] += 1
        _state["last_server_error"] = _now()


def snapshot() -> dict:
    with _lock:
        return {**_state, "recent_ai_errors": list(_recent_ai_errors), "started_at": STARTED_AT}
