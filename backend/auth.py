"""JWT helpers and the ``@require_auth`` decorator."""
from datetime import datetime, timedelta, timezone
from functools import wraps

import jwt
from flask import g, jsonify, request

from config import Config
from db import get_cursor


def make_token(user_id: int) -> str:
    payload = {
        "sub": str(user_id),
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(hours=Config.JWT_EXP_HOURS),
    }
    return jwt.encode(payload, Config.JWT_SECRET, algorithm=Config.JWT_ALGORITHM)


def _decode(token: str) -> dict:
    return jwt.decode(token, Config.JWT_SECRET, algorithms=[Config.JWT_ALGORITHM])


def require_auth(fn):
    """Decorator: requires a valid Bearer token; populates ``g.user``."""

    @wraps(fn)
    def wrapper(*args, **kwargs):
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return jsonify({"error": "missing or invalid Authorization header"}), 401
        token = header[len("Bearer "):].strip()
        try:
            payload = _decode(token)
            user_id = int(payload["sub"])
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "token expired"}), 401
        except (jwt.InvalidTokenError, KeyError, ValueError):
            return jsonify({"error": "invalid token"}), 401

        with get_cursor() as cur:
            cur.execute(
                "SELECT user_id, name, email, created_at FROM Users WHERE user_id = %s",
                (user_id,),
            )
            user = cur.fetchone()
        if not user:
            return jsonify({"error": "user not found"}), 401

        g.user = user
        return fn(*args, **kwargs)

    return wrapper


def get_current_user() -> dict:
    """Return the user dict attached by ``@require_auth``."""
    return g.user
