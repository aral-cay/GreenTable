"""Friendships: send requests, respond, list."""
import mysql.connector
from flask import Blueprint, jsonify, request

from auth import require_auth, get_current_user
from db import get_cursor
from helpers import log_action


friends_bp = Blueprint("friends", __name__)


@friends_bp.post("/friends/request")
@require_auth
def send_request():
    me = get_current_user()
    data = request.get_json(silent=True) or {}
    addressee_id = data.get("addressee_id")

    if not isinstance(addressee_id, int):
        return jsonify({"error": "addressee_id (int) is required"}), 400
    if addressee_id == me["user_id"]:
        return jsonify({"error": "cannot send a friend request to yourself"}), 400

    with get_cursor() as cur:
        cur.execute("SELECT user_id FROM Users WHERE user_id = %s", (addressee_id,))
        if not cur.fetchone():
            return jsonify({"error": "addressee not found"}), 404

        # Reject if a request already exists in either direction.
        cur.execute(
            """
            SELECT friendship_id, status, requester_id, addressee_id
            FROM Friendships
            WHERE (requester_id = %s AND addressee_id = %s)
               OR (requester_id = %s AND addressee_id = %s)
            LIMIT 1
            """,
            (me["user_id"], addressee_id, addressee_id, me["user_id"]),
        )
        existing = cur.fetchone()
        if existing:
            return jsonify({
                "error": "friendship already exists",
                "friendship": {
                    "friendship_id": existing["friendship_id"],
                    "status": existing["status"],
                },
            }), 409

    try:
        with get_cursor(commit=True) as cur:
            cur.execute(
                """
                INSERT INTO Friendships (requester_id, addressee_id, status)
                VALUES (%s, %s, 'pending')
                """,
                (me["user_id"], addressee_id),
            )
            friendship_id = cur.lastrowid
    except mysql.connector.IntegrityError as exc:
        if exc.errno == 1062:
            return jsonify({"error": "friendship already exists"}), 409
        return jsonify({"error": "could not create friend request"}), 400

    log_action(me["user_id"], None, "send_friend_request",
               f"to user_id={addressee_id} friendship_id={friendship_id}")

    return jsonify({"friendship_id": friendship_id, "status": "pending"}), 201


@friends_bp.put("/friends/respond")
@require_auth
def respond_request():
    me = get_current_user()
    data = request.get_json(silent=True) or {}
    friendship_id = data.get("friendship_id")
    status = (data.get("status") or "").strip().lower()

    if not isinstance(friendship_id, int) or status not in ("accepted", "declined"):
        return jsonify({"error": "friendship_id (int) and status (accepted|declined) required"}), 400

    with get_cursor(commit=True) as cur:
        cur.execute(
            "SELECT friendship_id, requester_id, addressee_id, status FROM Friendships WHERE friendship_id = %s",
            (friendship_id,),
        )
        row = cur.fetchone()
        if not row:
            return jsonify({"error": "friendship not found"}), 404
        if row["addressee_id"] != me["user_id"]:
            return jsonify({"error": "only the addressee may respond"}), 403
        if row["status"] != "pending":
            return jsonify({"error": f"already {row['status']}"}), 409

        cur.execute(
            "UPDATE Friendships SET status = %s WHERE friendship_id = %s",
            (status, friendship_id),
        )

    action = "accept_friend_request" if status == "accepted" else "decline_friend_request"
    log_action(me["user_id"], None, action, f"friendship_id={friendship_id}")

    return jsonify({"friendship_id": friendship_id, "status": status})


@friends_bp.get("/friends")
@require_auth
def list_friends():
    me = get_current_user()
    uid = me["user_id"]

    with get_cursor() as cur:
        # Accepted friends (either direction)
        cur.execute(
            """
            SELECT f.friendship_id, f.status, f.created_at,
                   f.requester_id, f.addressee_id,
                   u.user_id, u.name, u.email
            FROM Friendships f
            JOIN Users u ON u.user_id =
                CASE WHEN f.requester_id = %s THEN f.addressee_id ELSE f.requester_id END
            WHERE f.status = 'accepted'
              AND (f.requester_id = %s OR f.addressee_id = %s)
            ORDER BY u.name ASC
            """,
            (uid, uid, uid),
        )
        accepted = cur.fetchall()

        # Pending requests TO me
        cur.execute(
            """
            SELECT f.friendship_id, f.status, f.created_at,
                   f.requester_id, f.addressee_id,
                   u.user_id, u.name, u.email
            FROM Friendships f
            JOIN Users u ON u.user_id = f.requester_id
            WHERE f.status = 'pending' AND f.addressee_id = %s
            ORDER BY f.created_at DESC
            """,
            (uid,),
        )
        incoming = cur.fetchall()

        # Pending requests FROM me
        cur.execute(
            """
            SELECT f.friendship_id, f.status, f.created_at,
                   f.requester_id, f.addressee_id,
                   u.user_id, u.name, u.email
            FROM Friendships f
            JOIN Users u ON u.user_id = f.addressee_id
            WHERE f.status = 'pending' AND f.requester_id = %s
            ORDER BY f.created_at DESC
            """,
            (uid,),
        )
        outgoing = cur.fetchall()

    def _ser(rows):
        return [{
            "friendship_id": r["friendship_id"],
            "status": r["status"],
            "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
            "requester_id": r["requester_id"],
            "addressee_id": r["addressee_id"],
            "user": {"user_id": r["user_id"], "name": r["name"], "email": r["email"]},
        } for r in rows]

    return jsonify({
        "friends": _ser(accepted),
        "incoming_requests": _ser(incoming),
        "outgoing_requests": _ser(outgoing),
    })
