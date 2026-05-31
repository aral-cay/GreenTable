"""Shared helpers: email validation, friendship lookup, audit logging."""
import re
from datetime import datetime

from db import get_cursor


DARTMOUTH_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@dartmouth\.edu$")


def validate_dartmouth_email(email: str) -> bool:
    if not email or not isinstance(email, str):
        return False
    return bool(DARTMOUTH_EMAIL_RE.match(email.strip()))


def are_friends(user_id_1: int, user_id_2: int) -> bool:
    """True iff there is an accepted friendship between the two users."""
    if user_id_1 == user_id_2:
        return False
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT 1 FROM Friendships
            WHERE status = 'accepted'
              AND ((requester_id = %s AND addressee_id = %s)
                OR (requester_id = %s AND addressee_id = %s))
            LIMIT 1
            """,
            (user_id_1, user_id_2, user_id_2, user_id_1),
        )
        return cur.fetchone() is not None


def log_action(user_id: int, session_id: int | None, action: str, details: str | None = None) -> None:
    """Insert a row into AuditLog. Swallows errors so audit logging
    never breaks the main request flow."""
    try:
        with get_cursor(commit=True) as cur:
            cur.execute(
                """
                INSERT INTO AuditLog (user_id, session_id, action, details)
                VALUES (%s, %s, %s, %s)
                """,
                (user_id, session_id, action, details),
            )
    except Exception as exc:
        # Last-resort: print so the demo can still proceed.
        print(f"[audit] failed to log {action}: {exc}")


def parse_iso_datetime(value: str) -> datetime | None:
    """Accept ISO-8601 strings; return naive local datetime or None."""
    if not value or not isinstance(value, str):
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone().replace(tzinfo=None)
    return dt
