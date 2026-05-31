"""Session invitations: respond (accept/decline)."""
import mysql.connector
from flask import Blueprint, jsonify, request

from auth import require_auth, get_current_user
from db import get_cursor
from helpers import log_action


invitations_bp = Blueprint("invitations", __name__)


@invitations_bp.put("/invitations/respond")
@require_auth
def respond_invitation():
    me = get_current_user()
    data = request.get_json(silent=True) or {}
    invitation_id = data.get("invitation_id")
    status = (data.get("status") or "").strip().lower()

    if not isinstance(invitation_id, int) or status not in ("accepted", "declined"):
        return jsonify({"error": "invitation_id (int) and status (accepted|declined) required"}), 400

    with get_cursor() as cur:
        cur.execute(
            """
            SELECT i.invitation_id, i.session_id, i.invitee_id, i.status,
                   s.status AS session_status
            FROM SessionInvitations i
            JOIN MealSessions s ON s.session_id = i.session_id
            WHERE i.invitation_id = %s
            """,
            (invitation_id,),
        )
        invite = cur.fetchone()

    if not invite:
        return jsonify({"error": "invitation not found"}), 404
    if invite["invitee_id"] != me["user_id"]:
        return jsonify({"error": "only the invitee may respond"}), 403
    if invite["status"] != "pending":
        return jsonify({"error": f"invitation already {invite['status']}"}), 409
    if invite["session_status"] != "active":
        return jsonify({"error": "session is no longer active"}), 409

    try:
        with get_cursor(commit=True) as cur:
            cur.execute(
                "UPDATE SessionInvitations SET status = %s WHERE invitation_id = %s",
                (status, invitation_id),
            )
            if status == "accepted":
                cur.execute(
                    """
                    INSERT IGNORE INTO SessionParticipants (session_id, user_id)
                    VALUES (%s, %s)
                    """,
                    (invite["session_id"], me["user_id"]),
                )
    except mysql.connector.Error as exc:
        return jsonify({"error": f"could not respond: {exc.msg}"}), 400

    action = "accept_invitation" if status == "accepted" else "decline_invitation"
    log_action(me["user_id"], invite["session_id"], action,
               f"invitation_id={invitation_id}")

    return jsonify({"invitation_id": invitation_id, "status": status})
