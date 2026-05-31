"""End-to-end demo test for the GreenTable backend.

Usage:
    cd backend
    source .venv/bin/activate
    python test_api.py

Assumes the Flask server is running at http://127.0.0.1:5050.
Re-running is safe: existing users / friendships are reused instead of
crashing the test run.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from typing import Any

import requests


BASE_URL = "http://127.0.0.1:5050"

ALICE   = {"name": "Alice Green",   "email": "alice@dartmouth.edu",   "password": "alicepass1"}
BOB     = {"name": "Bob Stone",     "email": "bob@dartmouth.edu",     "password": "bobpass1"}
CHARLIE = {"name": "Charlie River", "email": "charlie@dartmouth.edu", "password": "charliepass1"}


# ---------------------------------------------------------------- result tracking

results: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    tag = "PASS" if ok else "FAIL"
    line = f"[{tag}] {name}"
    if detail:
        line += f"  -- {detail}"
    print(line)
    results.append((name, ok, detail))


# ---------------------------------------------------------------- HTTP helpers


def _do(method: str, path: str, *,
        token: str | None = None,
        json_body: dict | None = None,
        params: dict | None = None) -> tuple[int, Any]:
    url = f"{BASE_URL}{path}"
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        resp = requests.request(method, url, headers=headers, json=json_body, params=params, timeout=10)
    except requests.RequestException as exc:
        return 0, {"error": f"network error: {exc}"}
    try:
        body = resp.json()
    except ValueError:
        body = {"raw": resp.text}
    return resp.status_code, body


def post(path: str, *, token=None, json_body=None):
    return _do("POST", path, token=token, json_body=json_body)


def get(path: str, *, token=None, params=None):
    return _do("GET", path, token=token, params=params)


def put(path: str, *, token=None, json_body=None):
    return _do("PUT", path, token=token, json_body=json_body)


def delete(path: str, *, token=None):
    return _do("DELETE", path, token=token)


def show_failure(status: int, body: Any) -> str:
    try:
        body_str = json.dumps(body, indent=2)
    except (TypeError, ValueError):
        body_str = str(body)
    return f"status={status} body={body_str}"


# ---------------------------------------------------------------- domain helpers


def register_or_existing(user: dict, label: str) -> bool:
    """Try to register; treat 409 (already exists) as success for re-runs."""
    status, body = post("/users/register", json_body=user)
    if status == 201:
        record(f"register {label}", True)
        return True
    if status == 409:
        record(f"register {label} (already exists)", True, "treating 409 as OK for re-runs")
        return True
    record(f"register {label}", False, show_failure(status, body))
    return False


def login(user: dict, label: str) -> str | None:
    status, body = post("/users/login", json_body={"email": user["email"], "password": user["password"]})
    if status == 200 and isinstance(body, dict) and body.get("token"):
        record(f"login {label}", True, f"user_id={body['user']['user_id']}")
        return body["token"]
    record(f"login {label}", False, show_failure(status, body))
    return None


def user_id_from_search(token: str, query: str) -> int | None:
    status, body = get("/users/search", token=token, params={"q": query})
    if status != 200:
        return None
    for u in body.get("users", []):
        if u["email"].lower() == query.lower():
            return u["user_id"]
    return None


# Possible names for "pending requests sent TO the viewer" across server versions.
_INCOMING_BUCKETS = (
    "incoming_requests", "incoming", "pending_incoming", "pending", "requests",
)
# Possible names for "pending requests sent BY the viewer".
_OUTGOING_BUCKETS = (
    "outgoing_requests", "outgoing", "pending_outgoing", "sent_requests",
)
# Possible names for accepted friend rows.
_ACCEPTED_BUCKETS = ("friends", "accepted", "accepted_friends")
_ALL_BUCKETS = _ACCEPTED_BUCKETS + _INCOMING_BUCKETS + _OUTGOING_BUCKETS


def _friendship_matches(row: dict, requester_id: int, addressee_id: int) -> bool:
    """True if a friendship dict matches the (requester, addressee) pair.

    Prefers the explicit flat fields; falls back to nested ``user`` (since
    the API returns the *other* party as ``user``)."""
    if "requester_id" in row and "addressee_id" in row:
        return (row["requester_id"] == requester_id
                and row["addressee_id"] == addressee_id)
    other = (row.get("user") or {}).get("user_id")
    return other in (requester_id, addressee_id)


def find_friendship(viewer_token: str, requester_id: int, addressee_id: int
                    ) -> tuple[int | None, str | None, dict | None]:
    """Locate the friendship_id from any response bucket.

    Returns ``(friendship_id, status, raw_body)``. ``raw_body`` is returned
    so the caller can dump it on failure."""
    status, body = get("/friends", token=viewer_token)
    if status != 200 or not isinstance(body, dict):
        return None, None, body
    for bucket in _ALL_BUCKETS:
        for row in body.get(bucket, []) or []:
            if _friendship_matches(row, requester_id, addressee_id):
                return row.get("friendship_id"), row.get("status"), body
    return None, None, body


def future_iso(hours: int) -> str:
    return (datetime.now() + timedelta(hours=hours)).replace(microsecond=0).isoformat()


# ---------------------------------------------------------------- the flow


def main() -> int:
    # Sanity: server reachable
    status, body = get("/health")
    if status != 200:
        record("server reachable", False, show_failure(status, body))
        return 1
    record("server reachable", True)

    # 1-3. Register the three Dartmouth users (idempotent)
    register_or_existing(ALICE,   "alice")
    register_or_existing(BOB,     "bob")
    register_or_existing(CHARLIE, "charlie")

    # 4. Non-Dartmouth email must be rejected
    status, body = post("/users/register", json_body={
        "name": "Fake User", "email": "fake@gmail.com", "password": "fakepass1",
    })
    if status == 400:
        record("reject non-Dartmouth email", True, f"server said: {body.get('error')!r}")
    else:
        record("reject non-Dartmouth email", False, show_failure(status, body))

    # 5. Login each user and store tokens
    alice_token   = login(ALICE,   "alice")
    bob_token     = login(BOB,     "bob")
    charlie_token = login(CHARLIE, "charlie")
    if not (alice_token and bob_token and charlie_token):
        print("\nCannot continue without all three logins.")
        return print_summary()

    # 6. Search users -- Alice looks for Bob by email
    bob_id = user_id_from_search(alice_token, BOB["email"])
    charlie_id = user_id_from_search(alice_token, CHARLIE["email"])
    if bob_id and charlie_id:
        record("search users (alice finds bob & charlie)", True,
               f"bob_id={bob_id} charlie_id={charlie_id}")
    else:
        record("search users", False, f"bob_id={bob_id} charlie_id={charlie_id}")
        return print_summary()

    # Resolve alice_id correctly: search must be done WITH a token belonging
    # to someone OTHER than Alice, because /users/search excludes the caller.
    alice_id = user_id_from_search(bob_token, ALICE["email"])
    if not alice_id:
        record("resolve alice user_id (via bob's search)", False,
               "could not find alice via /users/search")
        return print_summary()

    # 7. Alice sends Bob a friend request -- capture friendship_id directly.
    friendship_id: int | None = None
    request_body: dict | None = None
    request_status: int | None = None

    status, body = post("/friends/request",
                        token=alice_token,
                        json_body={"addressee_id": bob_id})
    request_status, request_body = status, body if isinstance(body, dict) else None

    if status == 201 and isinstance(body, dict):
        friendship_id = body.get("friendship_id")
        record("alice sends friend request to bob", True,
               f"friendship_id={friendship_id}")
    elif status == 409 and isinstance(body, dict):
        # Re-run case: server returns the existing friendship in the body.
        nested = body.get("friendship") or {}
        friendship_id = nested.get("friendship_id") or body.get("friendship_id")
        record("alice sends friend request to bob (already exists)", True,
               f"friendship_id={friendship_id} status={nested.get('status')}")
    else:
        record("alice sends friend request to bob", False, show_failure(status, body))

    # 8. Bob accepts the friend request.
    # Prefer the friendship_id we just captured; otherwise fall back to GET /friends
    # and search every plausible bucket.
    current_status: str | None = None
    list_body: dict | None = None
    if friendship_id is None:
        friendship_id, current_status, list_body = find_friendship(
            bob_token, requester_id=alice_id, addressee_id=bob_id,
        )
        if friendship_id is None:
            print("\n--- Diagnostic dump ---")
            print(f"POST /friends/request -> status={request_status}")
            print(json.dumps(request_body, indent=2, default=str))
            print("GET /friends (as bob) ->")
            print(json.dumps(list_body, indent=2, default=str))
            print("--- end dump ---\n")
            record("bob accepts friend request", False,
                   "could not locate friendship_id in any bucket")
        # else: fall through to accept

    friendship_ok = False
    if friendship_id is not None:
        # If we don't know the status yet, peek at it so we can short-circuit
        # the "already accepted" re-run case.
        if current_status is None:
            _, st_existing, _ = find_friendship(
                bob_token, requester_id=alice_id, addressee_id=bob_id,
            )
            current_status = st_existing

        if current_status == "accepted":
            record("bob accepts friend request (already accepted)", True,
                   f"friendship_id={friendship_id}")
            friendship_ok = True
        else:
            status, body = put("/friends/respond",
                               token=bob_token,
                               json_body={
                                   "friendship_id": friendship_id,
                                   "status": "accepted",
                               })
            if status == 200 and isinstance(body, dict) and body.get("status") == "accepted":
                record("bob accepts friend request", True,
                       f"friendship_id={friendship_id}")
                friendship_ok = True
            elif status == 409 and "accepted" in str(body).lower():
                record("bob accepts friend request (already accepted)", True,
                       f"friendship_id={friendship_id}")
                friendship_ok = True
            else:
                record("bob accepts friend request", False, show_failure(status, body))

    # 8b. Verify the friendship is now accepted from BOTH sides.
    if friendship_ok:
        _, bob_view_status, _ = find_friendship(
            bob_token, requester_id=alice_id, addressee_id=bob_id,
        )
        _, alice_view_status, _ = find_friendship(
            alice_token, requester_id=alice_id, addressee_id=bob_id,
        )
        if bob_view_status == "accepted" and alice_view_status == "accepted":
            record("friendship visible as 'accepted' to both users", True)
        else:
            record("friendship visible as 'accepted' to both users", False,
                   f"bob_view={bob_view_status} alice_view={alice_view_status}")
            friendship_ok = False

    if not friendship_ok:
        print("\nSkipping remaining session tests because the friendship is not accepted.")
        return print_summary()

    # 9. Alice creates an OPEN session
    status, body = post("/sessions",
                        token=alice_token,
                        json_body={
                            "location_id":    1,
                            "meal_type":      "lunch",
                            "scheduled_time": future_iso(2),
                            "visibility":     "open",
                        })
    open_session_id = None
    if status == 201 and isinstance(body, dict):
        open_session_id = body["session"]["session_id"]
        record("alice creates open session", True, f"session_id={open_session_id}")
    else:
        record("alice creates open session", False, show_failure(status, body))

    # 10. Bob lists sessions and must see Alice's open session
    status, body = get("/sessions", token=bob_token)
    if status == 200 and isinstance(body, dict):
        ids = {s["session_id"] for s in body.get("friends_open", [])}
        if open_session_id in ids:
            record("bob sees alice's open session", True)
        else:
            record("bob sees alice's open session", False,
                   f"friends_open ids={sorted(ids)} expected={open_session_id}")
    else:
        record("bob sees alice's open session", False, show_failure(status, body))

    # 11. Bob joins Alice's open session
    if open_session_id is not None:
        status, body = post(f"/sessions/{open_session_id}/join", token=bob_token)
        if status == 200:
            record("bob joins alice's open session", True)
        elif status == 409 and "already joined" in str(body).lower():
            record("bob joins alice's open session (already joined)", True,
                   "treating 409 as OK for re-runs")
        else:
            record("bob joins alice's open session", False, show_failure(status, body))

    # 12. Bob tries to join again -- must fail with 409
    if open_session_id is not None:
        status, body = post(f"/sessions/{open_session_id}/join", token=bob_token)
        if status == 409:
            record("bob cannot join the same session twice", True,
                   f"server said: {body.get('error')!r}")
        else:
            record("bob cannot join the same session twice", False, show_failure(status, body))

    # 13. Alice creates an INVITE-ONLY session and invites Bob
    status, body = post("/sessions",
                        token=alice_token,
                        json_body={
                            "location_id":    2,
                            "meal_type":      "dinner",
                            "scheduled_time": future_iso(3),
                            "visibility":     "invite_only",
                            "invitee_ids":    [bob_id],
                        })
    invite_session_id = None
    if status == 201 and isinstance(body, dict):
        invite_session_id = body["session"]["session_id"]
        record("alice creates invite-only session", True, f"session_id={invite_session_id}")
    else:
        record("alice creates invite-only session", False, show_failure(status, body))

    # 14. Bob accepts the invitation
    invitation_id = None
    if invite_session_id is not None:
        status, body = get("/sessions", token=bob_token)
        if status == 200 and isinstance(body, dict):
            for inv in body.get("invitations", []):
                if inv["session_id"] == invite_session_id:
                    invitation_id = inv.get("invitation_id")
                    break
        if invitation_id is not None:
            status, body = put("/invitations/respond",
                               token=bob_token,
                               json_body={"invitation_id": invitation_id, "status": "accepted"})
            if status == 200:
                record("bob accepts invitation", True, f"invitation_id={invitation_id}")
            else:
                record("bob accepts invitation", False, show_failure(status, body))
        else:
            # Maybe Bob already accepted on a previous run -- check participation directly
            status, body = get(f"/sessions/{invite_session_id}", token=bob_token)
            bob_uid = get_user_id(alice_token, BOB["email"])
            if status == 200 and bob_uid and any(
                p["user_id"] == bob_uid for p in body.get("participants", [])
            ):
                record("bob accepts invitation (already accepted)", True,
                       "bob already a participant from previous run")
            else:
                record("bob accepts invitation", False,
                       "no pending invitation found for bob")

    # 15. Charlie (NOT invited, NOT a friend) tries to join the invite-only session
    if invite_session_id is not None:
        status, body = post(f"/sessions/{invite_session_id}/join", token=charlie_token)
        if status == 403:
            record("charlie cannot join invite-only session", True,
                   f"server said: {body.get('error')!r}")
        else:
            record("charlie cannot join invite-only session", False, show_failure(status, body))

    # 16. Alice cancels the open session
    if open_session_id is not None:
        status, body = delete(f"/sessions/{open_session_id}", token=alice_token)
        if status == 200 and isinstance(body, dict) and body.get("session", {}).get("status") == "cancelled":
            record("alice cancels session", True, f"session_id={open_session_id}")
        elif status == 409 and "cancelled" in str(body).lower():
            record("alice cancels session (already cancelled)", True,
                   "treating 409 as OK for re-runs")
        else:
            record("alice cancels session", False, show_failure(status, body))

    return print_summary()


def get_user_id(viewer_token: str, target_email: str) -> int | None:
    """Resolve a user_id by searching their email while authenticated."""
    status, body = get("/users/search", token=viewer_token, params={"q": target_email})
    if status != 200:
        return None
    for u in body.get("users", []):
        if u["email"].lower() == target_email.lower():
            return u["user_id"]
    return None


def print_summary() -> int:
    passed = sum(1 for _, ok, _ in results if ok)
    failed = sum(1 for _, ok, _ in results if not ok)
    print()
    print("=" * 60)
    print(f"SUMMARY: {passed} passed, {failed} failed")
    print("=" * 60)
    if failed:
        print("Failed steps:")
        for name, ok, detail in results:
            if not ok:
                print(f"  - {name}: {detail}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
