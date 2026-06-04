"""Session invitations: respond (accept/decline)."""
import mysql.connector
from flask import Blueprint, jsonify, request

from auth import require_auth, get_current_user
from db import get_cursor
from helpers import log_action


invitations_bp = Blueprint("invitations", __name__)


@invitations_bp.get("/sessions/<int:session_id>/invitations")
@require_auth
def list_invitations(session_id: int):
    me = get_current_user()

    # Make sure the session exists
    with get_cursor() as cur:
        cur.execute(
            "SELECT creator_id FROM MealSessions WHERE session_id = %s",
            (session_id,),
        )
        session = cur.fetchone()

    if not session:
        return jsonify({"error": "session not found"}), 404

    # Only the creator can see the invitation list
    if session["creator_id"] != me["user_id"]:
        return jsonify({"error": "only the creator can view invitations"}), 403

    with get_cursor() as cur:
        cur.execute(
            """
            SELECT i.invitation_id, i.status,
                   u.user_id, u.name, u.email
            FROM SessionInvitations i
            JOIN Users u ON u.user_id = i.invitee_id
            WHERE i.session_id = %s
            ORDER BY u.name ASC
            """,
            (session_id,),
        )
        rows = cur.fetchall()

    invitations = [
        {
            "invitation_id": r["invitation_id"],
            "status": r["status"],
            "invitee": {
                "user_id": r["user_id"],
                "name": r["name"],
                "email": r["email"],
            },
        }
        for r in rows
    ]

    return jsonify({"invitations": invitations})


@invitations_bp.delete("/invitations/<int:invitation_id>")
@require_auth
def revoke_invitation(invitation_id: int):
    me = get_current_user()

    # Look up the invitation and its session's creator
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT i.invitation_id, i.session_id, i.invitee_id, i.status,
                   s.creator_id, s.status AS session_status
            FROM SessionInvitations i
            JOIN MealSessions s ON s.session_id = i.session_id
            WHERE i.invitation_id = %s
            """,
            (invitation_id,),
        )
        invite = cur.fetchone()

    if not invite:
        return jsonify({"error": "invitation not found"}), 404

    # Only the session creator can revoke an invitation
    if invite["creator_id"] != me["user_id"]:
        return jsonify({"error": "only the session creator can revoke invitations"}), 403

    # Can only revoke a pending invitation (accepted means they already joined)
    if invite["status"] != "pending":
        return jsonify({"error": f"cannot revoke an invitation that is already {invite['status']}"}), 409

    with get_cursor(commit=True) as cur:
        cur.execute(
            "DELETE FROM SessionInvitations WHERE invitation_id = %s",
            (invitation_id,),
        )

    log_action(me["user_id"], invite["session_id"], "revoke_invitation",
               f"invitation_id={invitation_id} invitee_id={invite['invitee_id']}")

    return jsonify({"deleted": True, "invitation_id": invitation_id})


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
