"""Users: register, login, search."""
import bcrypt
import mysql.connector
from flask import Blueprint, jsonify, request

from auth import make_token, require_auth, get_current_user
from db import get_cursor
from helpers import validate_dartmouth_email


users_bp = Blueprint("users", __name__)


def _serialize_user(row: dict) -> dict:
    return {
        "user_id": row["user_id"],
        "name": row["name"],
        "email": row["email"],
        "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
    }


@users_bp.post("/users/register")
def register():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not name or not email or not password:
        return jsonify({"error": "name, email and password are required"}), 400
    if not validate_dartmouth_email(email):
        return jsonify({"error": "email must end with @dartmouth.edu"}), 400
    if len(password) < 6:
        return jsonify({"error": "password must be at least 6 characters"}), 400

    password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    try:
        with get_cursor(commit=True) as cur:
            cur.execute(
                """
                INSERT INTO Users (name, email, password_hash)
                VALUES (%s, %s, %s)
                """,
                (name, email, password_hash),
            )
            new_id = cur.lastrowid
            cur.execute(
                "SELECT user_id, name, email, created_at FROM Users WHERE user_id = %s",
                (new_id,),
            )
            user = cur.fetchone()
    except mysql.connector.IntegrityError as exc:
        # 1062 = duplicate; 3819 = check constraint violated.
        if exc.errno == 1062:
            return jsonify({"error": "email already registered"}), 409
        if exc.errno == 3819:
            return jsonify({"error": "email must end with @dartmouth.edu"}), 400
        return jsonify({"error": "could not register user"}), 400

    return jsonify({"user": _serialize_user(user)}), 201


@users_bp.post("/users/login")
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not email or not password:
        return jsonify({"error": "email and password are required"}), 400

    with get_cursor() as cur:
        cur.execute(
            """
            SELECT user_id, name, email, password_hash, created_at
            FROM Users WHERE email = %s
            """,
            (email,),
        )
        row = cur.fetchone()

    if not row or not bcrypt.checkpw(password.encode("utf-8"), row["password_hash"].encode("utf-8")):
        return jsonify({"error": "invalid email or password"}), 401

    token = make_token(row["user_id"])
    return jsonify({"token": token, "user": _serialize_user(row)})


@users_bp.get("/users/search")
@require_auth
def search_users():
    q = (request.args.get("q") or "").strip()
    me = get_current_user()
    if not q:
        return jsonify({"users": []})

    like = f"%{q}%"
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT user_id, name, email, created_at
            FROM Users
            WHERE user_id <> %s
              AND (name LIKE %s OR email LIKE %s)
            ORDER BY name ASC
            LIMIT 25
            """,
            (me["user_id"], like, like),
        )
        rows = cur.fetchall()

    return jsonify({"users": [_serialize_user(r) for r in rows]})


@users_bp.get("/users/me")
@require_auth
def me():
    return jsonify({"user": _serialize_user(get_current_user())})
