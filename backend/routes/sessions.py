"""Meal sessions: create, list, get, update, cancel, join."""
from datetime import datetime, timedelta

import mysql.connector
from flask import Blueprint, jsonify, request

from auth import require_auth, get_current_user
from db import get_cursor
from helpers import are_friends, log_action, parse_iso_datetime


sessions_bp = Blueprint("sessions", __name__)


VALID_MEAL_TYPES = {"breakfast", "lunch", "dinner"}
VALID_VISIBILITY = {"open", "invite_only"}
VALID_STATUSES = {"active", "cancelled"}

# Users may not create two active sessions whose scheduled times sit within
# this window of each other (prevents accidental duplicate-create).
DUPLICATE_WINDOW = timedelta(minutes=30)


# --------------------------------------------------------------------- helpers


def _serialize_session(row: dict) -> dict:
    return {
        "session_id": row["session_id"],
        "creator_id": row["creator_id"],
        "creator_name": row.get("creator_name"),
        "location_id": row["location_id"],
        "location_name": row.get("location_name"),
        "meal_type": row["meal_type"],
        "scheduled_time": row["scheduled_time"].isoformat() if row.get("scheduled_time") else None,
        "visibility": row["visibility"],
        "status": row["status"],
        "participant_count": int(row.get("participant_count") or 0),
        "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
        "viewer_role": row.get("viewer_role"),
        "invitation_id": row.get("invitation_id"),
        "invitation_status": row.get("invitation_status"),
    }


_BASE_SELECT = """
SELECT s.session_id, s.creator_id, s.location_id, s.meal_type,
       s.scheduled_time, s.visibility, s.status, s.created_at,
       u.name AS creator_name,
       l.name AS location_name,
       (SELECT COUNT(*) FROM SessionParticipants p WHERE p.session_id = s.session_id) AS participant_count
FROM MealSessions s
JOIN Users u ON u.user_id = s.creator_id
JOIN DiningLocations l ON l.location_id = s.location_id
"""


def _fetch_session(session_id: int) -> dict | None:
    with get_cursor() as cur:
        cur.execute(_BASE_SELECT + " WHERE s.session_id = %s", (session_id,))
        return cur.fetchone()


# --------------------------------------------------------------------- routes


@sessions_bp.get("/locations")
@require_auth
def list_locations():
    with get_cursor() as cur:
        cur.execute("SELECT location_id, name, address FROM DiningLocations ORDER BY name ASC")
        rows = cur.fetchall()
    return jsonify({"locations": rows})


@sessions_bp.post("/sessions")
@require_auth
def create_session():
    me = get_current_user()
    data = request.get_json(silent=True) or {}

    location_id = data.get("location_id")
    meal_type = (data.get("meal_type") or "").strip().lower()
    scheduled_time_raw = data.get("scheduled_time")
    visibility = (data.get("visibility") or "open").strip().lower()
    invitee_ids = data.get("invitee_ids") or []

    if not isinstance(location_id, int):
        return jsonify({"error": "location_id (int) is required"}), 400
    if meal_type not in VALID_MEAL_TYPES:
        return jsonify({"error": "meal_type must be breakfast, lunch or dinner"}), 400
    if visibility not in VALID_VISIBILITY:
        return jsonify({"error": "visibility must be open or invite_only"}), 400
    scheduled_time = parse_iso_datetime(scheduled_time_raw or "")
    if scheduled_time is None:
        return jsonify({"error": "scheduled_time must be an ISO-8601 datetime"}), 400
    if scheduled_time < datetime.now():
        return jsonify({"error": "scheduled_time cannot be in the past"}), 400
    if not isinstance(invitee_ids, list) or not all(isinstance(x, int) for x in invitee_ids):
        return jsonify({"error": "invitee_ids must be a list of integers"}), 400

    with get_cursor() as cur:
        cur.execute("SELECT location_id FROM DiningLocations WHERE location_id = %s", (location_id,))
        if not cur.fetchone():
            return jsonify({"error": "location not found"}), 404

        # Reject if the same user already has an active session whose scheduled
        # time is within DUPLICATE_WINDOW of the requested time.
        window_start = scheduled_time - DUPLICATE_WINDOW
        window_end = scheduled_time + DUPLICATE_WINDOW
        cur.execute(
            """
            SELECT session_id, scheduled_time
            FROM MealSessions
            WHERE creator_id = %s
              AND status = 'active'
              AND scheduled_time BETWEEN %s AND %s
            LIMIT 1
            """,
            (me["user_id"], window_start, window_end),
        )
        clash = cur.fetchone()
        if clash:
            return jsonify({
                "error": "you already have a session within 30 minutes of that time"
            }), 409

    try:
        with get_cursor(commit=True) as cur:
            cur.execute(
                """
                INSERT INTO MealSessions
                    (creator_id, location_id, meal_type, scheduled_time, visibility, status)
                VALUES (%s, %s, %s, %s, %s, 'active')
                """,
                (me["user_id"], location_id, meal_type, scheduled_time, visibility),
            )
            session_id = cur.lastrowid

            cur.execute(
                "INSERT INTO SessionParticipants (session_id, user_id) VALUES (%s, %s)",
                (session_id, me["user_id"]),
            )

            created_invitations: list[int] = []
            if visibility == "invite_only" and invitee_ids:
                unique_ids = [i for i in dict.fromkeys(invitee_ids) if i != me["user_id"]]
                for invitee_id in unique_ids:
                    try:
                        cur.execute(
                            """
                            INSERT INTO SessionInvitations (session_id, invitee_id, status)
                            VALUES (%s, %s, 'pending')
                            """,
                            (session_id, invitee_id),
                        )
                        created_invitations.append(invitee_id)
                    except mysql.connector.IntegrityError:
                        # invalid invitee or duplicate -- just skip for the demo.
                        continue
    except mysql.connector.Error as exc:
        return jsonify({"error": f"could not create session: {exc.msg}"}), 400

    log_action(me["user_id"], session_id, "create_session",
               f"location_id={location_id} meal_type={meal_type} visibility={visibility}")
    for invitee_id in created_invitations:
        log_action(me["user_id"], session_id, "send_invitation",
                   f"invitee_id={invitee_id}")

    return jsonify({"session": _serialize_session(_fetch_session(session_id))}), 201


@sessions_bp.get("/sessions")
@require_auth
def list_sessions():
    me = get_current_user()
    uid = me["user_id"]

    with get_cursor() as cur:
        # 1. Sessions created by me
        cur.execute(_BASE_SELECT + " WHERE s.creator_id = %s", (uid,))
        created_rows = cur.fetchall()

        # 2. Sessions I joined (excluding ones I created to avoid duplicates)
        cur.execute(
            _BASE_SELECT + """
            JOIN SessionParticipants p ON p.session_id = s.session_id
            WHERE p.user_id = %s AND s.creator_id <> %s
            """,
            (uid, uid),
        )
        joined_rows = cur.fetchall()

        # 3. Open sessions from accepted friends (that I haven't joined)
        cur.execute(
            _BASE_SELECT + """
            WHERE s.visibility = 'open'
              AND s.status = 'active'
              AND s.creator_id IN (
                    SELECT CASE WHEN requester_id = %s THEN addressee_id ELSE requester_id END
                    FROM Friendships
                    WHERE status = 'accepted' AND (requester_id = %s OR addressee_id = %s)
              )
              AND s.session_id NOT IN (
                    SELECT session_id FROM SessionParticipants WHERE user_id = %s
              )
            """,
            (uid, uid, uid, uid),
        )
        friends_open_rows = cur.fetchall()

        # 4. Pending invite-only invitations for me
        cur.execute(
            """
            SELECT s.session_id, s.creator_id, s.location_id, s.meal_type,
                   s.scheduled_time, s.visibility, s.status, s.created_at,
                   u.name AS creator_name,
                   l.name AS location_name,
                   (SELECT COUNT(*) FROM SessionParticipants p WHERE p.session_id = s.session_id) AS participant_count,
                   i.invitation_id, i.status AS invitation_status
            FROM SessionInvitations i
            JOIN MealSessions s ON s.session_id = i.session_id
            JOIN Users u ON u.user_id = s.creator_id
            JOIN DiningLocations l ON l.location_id = s.location_id
            WHERE i.invitee_id = %s AND i.status = 'pending' AND s.status = 'active'
            """,
            (uid,),
        )
        invitation_rows = cur.fetchall()

    for r in created_rows:
        r["viewer_role"] = "creator"
    for r in joined_rows:
        r["viewer_role"] = "participant"
    for r in friends_open_rows:
        r["viewer_role"] = "friend_open"
    for r in invitation_rows:
        r["viewer_role"] = "invited"

    all_rows = created_rows + joined_rows + friends_open_rows + invitation_rows

    return jsonify({
        "sessions": [_serialize_session(r) for r in all_rows],
        "created": [_serialize_session(r) for r in created_rows],
        "joined": [_serialize_session(r) for r in joined_rows],
        "friends_open": [_serialize_session(r) for r in friends_open_rows],
        "invitations": [_serialize_session(r) for r in invitation_rows],
    })


@sessions_bp.get("/sessions/<int:session_id>")
@require_auth
def get_session(session_id: int):
    row = _fetch_session(session_id)
    if not row:
        return jsonify({"error": "session not found"}), 404

    with get_cursor() as cur:
        cur.execute(
            """
            SELECT u.user_id, u.name, u.email, p.joined_at
            FROM SessionParticipants p
            JOIN Users u ON u.user_id = p.user_id
            WHERE p.session_id = %s
            ORDER BY p.joined_at ASC
            """,
            (session_id,),
        )
        participants = cur.fetchall()

    return jsonify({
        "session": _serialize_session(row),
        "participants": [{
            "user_id": p["user_id"],
            "name": p["name"],
            "email": p["email"],
            "joined_at": p["joined_at"].isoformat() if p.get("joined_at") else None,
        } for p in participants],
    })


@sessions_bp.post("/sessions/<int:session_id>/join")
@require_auth
def join_session(session_id: int):
    me = get_current_user()
    uid = me["user_id"]

    session = _fetch_session(session_id)
    if not session:
        return jsonify({"error": "session not found"}), 404
    if session["status"] != "active":
        return jsonify({"error": "session is not active"}), 409

    with get_cursor() as cur:
        cur.execute(
            "SELECT 1 FROM SessionParticipants WHERE session_id = %s AND user_id = %s",
            (session_id, uid),
        )
        if cur.fetchone():
            return jsonify({"error": "you already joined this session"}), 409

        cur.execute(
            """
            SELECT invitation_id, status
            FROM SessionInvitations
            WHERE session_id = %s AND invitee_id = %s
            """,
            (session_id, uid),
        )
        invitation = cur.fetchone()

    if session["visibility"] == "invite_only":
        if not invitation or invitation["status"] not in ("pending", "accepted"):
            return jsonify({"error": "you are not invited to this session"}), 403
    else:  # open
        if uid != session["creator_id"] and not are_friends(uid, session["creator_id"]):
            return jsonify({"error": "you must be friends with the creator to join"}), 403

    try:
        with get_cursor(commit=True) as cur:
            cur.execute(
                "INSERT INTO SessionParticipants (session_id, user_id) VALUES (%s, %s)",
                (session_id, uid),
            )
            if invitation and invitation["status"] == "pending":
                cur.execute(
                    "UPDATE SessionInvitations SET status = 'accepted' WHERE invitation_id = %s",
                    (invitation["invitation_id"],),
                )
    except mysql.connector.IntegrityError as exc:
        if exc.errno == 1062:
            return jsonify({"error": "you already joined this session"}), 409
        return jsonify({"error": "could not join session"}), 400

    log_action(uid, session_id, "join_session", None)
    return jsonify({"session": _serialize_session(_fetch_session(session_id))})


@sessions_bp.put("/sessions/<int:session_id>")
@require_auth
def update_session(session_id: int):
    me = get_current_user()
    data = request.get_json(silent=True) or {}

    session = _fetch_session(session_id)
    if not session:
        return jsonify({"error": "session not found"}), 404
    if session["creator_id"] != me["user_id"]:
        return jsonify({"error": "only the creator may update this session"}), 403

    updates: list[str] = []
    params: list = []

    if "location_id" in data:
        loc = data["location_id"]
        if not isinstance(loc, int):
            return jsonify({"error": "location_id must be int"}), 400
        with get_cursor() as cur:
            cur.execute("SELECT 1 FROM DiningLocations WHERE location_id = %s", (loc,))
            if not cur.fetchone():
                return jsonify({"error": "location not found"}), 404
        updates.append("location_id = %s"); params.append(loc)

    if "meal_type" in data:
        mt = (data["meal_type"] or "").strip().lower()
        if mt not in VALID_MEAL_TYPES:
            return jsonify({"error": "invalid meal_type"}), 400
        updates.append("meal_type = %s"); params.append(mt)

    if "scheduled_time" in data:
        st = parse_iso_datetime(data["scheduled_time"] or "")
        if st is None:
            return jsonify({"error": "scheduled_time must be ISO-8601"}), 400
        if st < datetime.now():
            return jsonify({"error": "scheduled_time cannot be in the past"}), 400
        updates.append("scheduled_time = %s"); params.append(st)

    if "visibility" in data:
        vis = (data["visibility"] or "").strip().lower()
        if vis not in VALID_VISIBILITY:
            return jsonify({"error": "invalid visibility"}), 400
        updates.append("visibility = %s"); params.append(vis)

    if "status" in data:
        stt = (data["status"] or "").strip().lower()
        if stt not in VALID_STATUSES:
            return jsonify({"error": "invalid status"}), 400
        updates.append("status = %s"); params.append(stt)

    if not updates:
        return jsonify({"error": "no fields to update"}), 400

    params.append(session_id)
    with get_cursor(commit=True) as cur:
        cur.execute(
            f"UPDATE MealSessions SET {', '.join(updates)} WHERE session_id = %s",
            tuple(params),
        )

    log_action(me["user_id"], session_id, "update_session",
               ", ".join(updates).replace(" = %s", ""))
    return jsonify({"session": _serialize_session(_fetch_session(session_id))})


@sessions_bp.delete("/sessions/<int:session_id>")
@require_auth
def cancel_session(session_id: int):
    me = get_current_user()

    session = _fetch_session(session_id)
    if not session:
        return jsonify({"error": "session not found"}), 404
    if session["creator_id"] != me["user_id"]:
        return jsonify({"error": "only the creator may cancel this session"}), 403
    if session["status"] == "cancelled":
        return jsonify({"error": "session already cancelled"}), 409

    with get_cursor(commit=True) as cur:
        cur.execute(
            "UPDATE MealSessions SET status = 'cancelled' WHERE session_id = %s",
            (session_id,),
        )

    log_action(me["user_id"], session_id, "cancel_session", None)
    return jsonify({"session": _serialize_session(_fetch_session(session_id))})


@sessions_bp.delete("/sessions/<int:session_id>/permanent")
@require_auth
def delete_session(session_id: int):
    """Permanently delete a session. Only the creator may do this, and only
    after the session has been cancelled."""
    me = get_current_user()

    session = _fetch_session(session_id)
    if not session:
        return jsonify({"error": "session not found"}), 404
    if session["creator_id"] != me["user_id"]:
        return jsonify({"error": "only the creator may delete this session"}), 403
    if session["status"] != "cancelled":
        return jsonify({"error": "cancel the session before deleting it"}), 409

    # Audit-log first while the session_id still references a real row;
    # AuditLog.session_id is ON DELETE SET NULL so we keep the audit trail.
    log_action(me["user_id"], session_id, "delete_session", None)

    with get_cursor(commit=True) as cur:
        # SessionParticipants and SessionInvitations cascade on delete.
        cur.execute("DELETE FROM MealSessions WHERE session_id = %s", (session_id,))

    return jsonify({"deleted": True, "session_id": session_id})


@sessions_bp.post("/sessions/<int:session_id>/leave")
@require_auth
def leave_session(session_id: int):
    """A non-creator participant leaves an active session."""
    me = get_current_user()
    uid = me["user_id"]

    session = _fetch_session(session_id)
    if not session:
        return jsonify({"error": "session not found"}), 404
    if session["creator_id"] == uid:
        return jsonify({"error": "creators cannot leave their own session; cancel it instead"}), 400
    if session["status"] != "active":
        return jsonify({"error": "session is not active"}), 409

    with get_cursor() as cur:
        cur.execute(
            "SELECT 1 FROM SessionParticipants WHERE session_id = %s AND user_id = %s",
            (session_id, uid),
        )
        if not cur.fetchone():
            return jsonify({"error": "you are not part of this session"}), 404

    with get_cursor(commit=True) as cur:
        cur.execute(
            "DELETE FROM SessionParticipants WHERE session_id = %s AND user_id = %s",
            (session_id, uid),
        )
        # If the user had an accepted invitation, revert it to declined so the
        # session no longer shows as one they're attending.
        cur.execute(
            """
            UPDATE SessionInvitations
            SET status = 'declined'
            WHERE session_id = %s AND invitee_id = %s AND status = 'accepted'
            """,
            (session_id, uid),
        )

    log_action(uid, session_id, "leave_session", None)
    return jsonify({"session": _serialize_session(_fetch_session(session_id))})
