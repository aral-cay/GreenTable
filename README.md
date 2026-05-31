# GreenTable

A Dartmouth-specific dining coordination app built for a database class project.

- **Backend**: Flask + MySQL, JWT auth, bcrypt-hashed passwords, parameterized SQL.
- **Frontend**: SwiftUI iOS app talking to the REST API via `URLSession`.

> **New here? Read [`SETUP.md`](./SETUP.md) first** — it walks you from a clean
> Mac all the way to a running app, with troubleshooting. The rest of this file
> is reference documentation.

```
GreenTable/                       # repo root (also the Xcode project root)
├── backend/                      # Flask app + MySQL schema
│   ├── app.py
│   ├── auth.py
│   ├── config.py
│   ├── db.py
│   ├── helpers.py
│   ├── requirements.txt
│   ├── schema.sql                # tables + seed dining locations
│   ├── test_api.py               # end-to-end test runner
│   ├── .env.example              # copy to .env and fill in your own values
│   └── routes/
│       ├── users.py
│       ├── friends.py
│       ├── sessions.py
│       └── invitations.py
├── GreenTable.xcodeproj/         # Xcode project
└── GreenTable/                   # SwiftUI app source files
    ├── GreenTableApp.swift
    ├── ContentView.swift
    ├── APIClient.swift
    ├── AuthStore.swift
    ├── Models.swift
    ├── AuthView.swift
    ├── DashboardView.swift
    ├── FriendsView.swift
    └── CreateSessionView.swift
```

---

## What you need installed

Before running anything you need:

- **macOS + Xcode 15+** (only required if you want to run the iOS app)
- **Python 3.10+**
- **MySQL 8.0.16+** (older MySQL silently ignores the `CHECK` constraints we use)
- `git`

`.env` is **not** committed — every contributor creates their own from
`backend/.env.example`.

---

## 1. Create the MySQL database

Open the `mysql` client (or MySQL Workbench / TablePlus) and run:

```sql
CREATE DATABASE greentable
    CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

> MySQL 8.0.16+ is recommended so `CHECK` constraints (Dartmouth email, no
> self-friendship) are enforced. Older MySQL silently ignores `CHECK`.

## 2. Run the schema

From the repo root:

```bash
mysql -u root -p greentable < backend/schema.sql
```

This drops/recreates all 7 tables and seeds the four dining locations
(`Foco`, `Hop`, `Collis`, `Novack`).

## 3. Install Python dependencies

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 4. Configure environment

```bash
cp .env.example .env
```

Edit `.env`:

```
DB_USER=root
DB_PASSWORD=your-mysql-password
DB_NAME=greentable
JWT_SECRET=a-long-random-string
FLASK_PORT=5050
```

## 5. Start the Flask server

```bash
python app.py
```

You should see something like:

```
 * Running on http://0.0.0.0:5050
```

Quick sanity check:

```bash
curl http://127.0.0.1:5050/health
# {"status":"ok"}
```

## 6. Point the iOS app at your server

Open `GreenTable/APIClient.swift` and edit the `baseURL` if needed:

```swift
var baseURL = URL(string: "http://127.0.0.1:5050")!
```

- **iOS Simulator** can hit `127.0.0.1` directly.
- **Physical iPhone** — use your Mac's LAN IP (e.g. `http://192.168.1.42:5050`),
  and add an App Transport Security exception for the IP in Info.plist
  (`NSAppTransportSecurity` -> `NSAllowsArbitraryLoads` = true) since the demo
  uses plain HTTP.

### Running the iOS app

The Xcode project is checked in at the repo root. Just:

1. Open `GreenTable.xcodeproj` in Xcode.
2. Select an iPhone Simulator scheme.
3. Build & run (⌘R).

No manual file dragging required.

---

## Automated API test

With the Flask server already running (`python app.py`), open a second terminal
and run the full demo flow against the live API:

```bash
cd backend
source .venv/bin/activate
python test_api.py
```

The script:

- Registers Alice, Bob and Charlie (`@dartmouth.edu`); confirms `fake@gmail.com` is rejected.
- Logs in each user and stores their JWTs.
- Searches users, sends + accepts a friend request between Alice and Bob.
- Has Alice create an open session, verifies Bob can see and join it,
  then proves Bob cannot join the same session twice.
- Has Alice create an invite-only session, Bob accepts the invite, and
  Charlie (not invited) is rejected.
- Has Alice cancel a session.

Each step prints `[PASS]` or `[FAIL]`, and the script finishes with a summary
like `SUMMARY: 14 passed, 0 failed`. Re-running is safe — existing users,
friendships and prior responses are handled gracefully.

## Demo flow

1. Launch the iOS app — you'll see the **Login / Register** screen.
2. Tap **Register**, enter `alice@dartmouth.edu`, a name, and a password.
3. The app auto-logs you in and shows the **Sessions** tab.
4. Open a second simulator (or run on another device) and register `bob@dartmouth.edu`.
5. Bob taps **Friends → Search**, finds Alice, taps **Add**.
6. Alice opens **Friends**, sees the incoming request, taps **Accept**.
7. Alice taps **New**, picks `Foco`, lunch, an upcoming time, **Open to friends**, **Create session**.
8. Bob refreshes **Sessions** — the session appears under
   *Open sessions from friends*. Bob taps **Join**.
9. Alice creates another session set to **Invite only** and selects Bob.
10. Bob sees it under **Pending Invitations** and taps **Accept**.

---

## Implemented endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET    | `/health` | – | Health check |
| POST   | `/users/register` | – | Register (`@dartmouth.edu` only) |
| POST   | `/users/login` | – | Login → JWT |
| GET    | `/users/me` | JWT | Current user |
| GET    | `/users/search?q=` | JWT | Search Dartmouth users |
| POST   | `/friends/request` | JWT | Send friend request |
| PUT    | `/friends/respond` | JWT | Accept / decline |
| GET    | `/friends` | JWT | Friends, incoming + outgoing requests |
| GET    | `/locations` | JWT | Seeded dining locations |
| POST   | `/sessions` | JWT | Create meal session (rejected if you already have an active one within ±30 min) |
| GET    | `/sessions` | JWT | Created / joined / friend-open / pending invitations |
| GET    | `/sessions/{id}` | JWT | Session + participants |
| POST   | `/sessions/{id}/join` | JWT | Join open or invited session |
| POST   | `/sessions/{id}/leave` | JWT | Participant (non-creator) leaves an active session |
| PUT    | `/sessions/{id}` | JWT | Creator-only update |
| DELETE | `/sessions/{id}` | JWT | Creator-only cancel (sets `status='cancelled'`) |
| DELETE | `/sessions/{id}/permanent` | JWT | Creator-only hard delete (only after cancel) |
| PUT    | `/invitations/respond` | JWT | Invitee accepts / declines |

### Error model

```json
{ "error": "human-readable message" }
```

Status codes used:

- `400` bad input
- `401` missing / invalid / expired token
- `403` not allowed (wrong user)
- `404` resource not found
- `409` duplicate or conflict (already joined, already responded, etc.)

---

## Test checklist for the demo

Run through these in order — each should produce the expected result and a
matching row in `AuditLog` where applicable.

- [ ] **Register Dartmouth user** — `POST /users/register` with
  `alice@dartmouth.edu` → `201` with user info, no `password_hash`.
- [ ] **Reject non-Dartmouth email** — register with `alice@gmail.com` →
  `400 email must end with @dartmouth.edu`.
- [ ] **Login** — `POST /users/login` returns a JWT.
- [ ] **Send friend request** — Bob → Alice via `POST /friends/request`,
  inserts row in `Friendships` (status `pending`) + audit `send_friend_request`.
- [ ] **Accept friend request** — Alice `PUT /friends/respond` with
  `accepted` → row updated, audit `accept_friend_request`.
- [ ] **Create open session** — Alice `POST /sessions` (visibility `open`).
  Audit `create_session`. Alice auto-added to `SessionParticipants`.
- [ ] **Friend sees + joins open session** — `GET /sessions` for Bob lists it
  under `friends_open`; `POST /sessions/{id}/join` succeeds, audit `join_session`.
- [ ] **Create invite-only session** — Alice creates one with `invitee_ids: [bob_id]`.
  Row appears in `SessionInvitations` (pending), audit `create_session` +
  `send_invitation`.
- [ ] **Invited user accepts** — Bob `PUT /invitations/respond` with `accepted` →
  invitation flips to `accepted`, Bob added to `SessionParticipants`,
  audit `accept_invitation`.
- [ ] **Non-invited user blocked** — register `carol@dartmouth.edu` and try
  `POST /sessions/{id}/join` on Alice's invite-only session → `403 you are not invited`.
- [ ] **Creator cancels session** — Alice `DELETE /sessions/{id}` → `status='cancelled'`,
  audit `cancel_session`.
- [ ] **Audit log populated** — `SELECT * FROM AuditLog ORDER BY created_at;`
  shows rows for every action above.

Handy SQL to inspect the audit trail:

```sql
SELECT a.audit_id, u.email, a.session_id, a.action, a.details, a.created_at
FROM AuditLog a
JOIN Users u ON u.user_id = a.user_id
ORDER BY a.created_at DESC
LIMIT 50;
```

---

## Implementation notes

- All SQL uses `%s` parameter placeholders — never string interpolation.
- `password_hash` is never returned by any endpoint.
- JWT tokens are signed `HS256` and expire after `JWT_EXP_HOURS` (default 24).
- `scheduled_time` validation against "now" is done in Python (MySQL `CHECK`
  cannot reference `NOW()`).
- Cancel uses a soft delete (`status='cancelled'`) so audit history and
  invitations remain intact.
- The `AuditLog.session_id` foreign key uses `ON DELETE SET NULL` so audit
  rows survive even if a session is hard-deleted.
