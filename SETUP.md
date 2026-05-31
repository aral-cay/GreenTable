# Setup — running GreenTable on your Mac

Step-by-step from a clean Mac to a running app. Everything runs locally; you
don't need any credentials from anyone else.

If you get stuck, see [Troubleshooting](#troubleshooting).

---

## 0. Install prereqs

Open **Terminal** and install [Homebrew](https://brew.sh) if you don't have it:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

Then:

```bash
brew install python git mysql
brew services start mysql
```

Install **Xcode 15+** from the Mac App Store (only needed for the iOS app),
open it once, then run `xcode-select --install`.

---

## 1. Clone

```bash
git clone https://github.com/aral-cay/GreenTable.git GreenTable
cd GreenTable
```

---

## 2. MySQL (one time)

Set a root password and create the database:

```bash
mysql_secure_installation        # set a root password; defaults are fine
mysql -u root -p -e "CREATE DATABASE greentable CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
mysql -u root -p greentable < backend/schema.sql
```

Verify (should list 7 tables and 4 dining halls):

```bash
mysql -u root -p -e "USE greentable; SHOW TABLES; SELECT * FROM DiningLocations;"
```

---

## 3. Backend

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Open `.env` and fill in two values:

- `DB_PASSWORD=` your MySQL root password from step 2
- `JWT_SECRET=` a long random string — generate one with:
  ```bash
  python3 -c "import secrets; print(secrets.token_urlsafe(48))"
  ```

> `.env` is gitignored — never committed.

Start the server (leave this terminal running):

```bash
python app.py
```

In a **new** terminal tab, smoke-test:

```bash
curl http://127.0.0.1:5050/health   # → {"status":"ok"}
```

Optional full API test:

```bash
cd ~/Code/GreenTable/backend && source .venv/bin/activate && python test_api.py
```

---

## 4. iOS app

1. Open `GreenTable.xcodeproj` in Xcode.
2. Pick an iPhone Simulator at the top of the window.
3. Press **⌘R**.

Register with any name and any `*@dartmouth.edu` email (password ≥ 8 chars).
The Simulator can hit `127.0.0.1` so the default `baseURL` works.

**Real iPhone instead?** Find your Mac's LAN IP (System Settings → Network)
and edit `GreenTable/APIClient.swift`:

```swift
var baseURL = URL(string: "http://192.168.1.42:5050")!
```

Mac + iPhone on the same Wi-Fi. Allow Python through the macOS firewall when
prompted.

### Demo flow

1. Register `alice@dartmouth.edu`.
2. (Second simulator) register `bob@dartmouth.edu`.
3. Bob: **Friends → Search**, find Alice, **Add**.
4. Alice: **Friends** → **Accept**.
5. Alice: **New** → Foco / lunch / upcoming time / open → **Create session**.
6. Bob: pull-to-refresh **Sessions** → tap **Join**.

---

## Troubleshooting


| Symptom                                                    | Fix                                                                                                     |
| ---------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| `mysql: command not found`                                 | `brew link --force mysql`, or add `/opt/homebrew/opt/mysql/bin` to `PATH`                               |
| `Can't connect to MySQL server`                            | `brew services start mysql`                                                                             |
| `Access denied for user 'root'`                            | `DB_PASSWORD` in `.env` doesn't match what you set in step 2                                            |
| `ModuleNotFoundError: flask` (or `mysql`, `jwt`, `bcrypt`) | Forgot to `source .venv/bin/activate`; then `pip install -r requirements.txt`                           |
| `Address already in use` (port 5050)                       | Change `FLASK_PORT` in `.env` AND `baseURL` in `APIClient.swift` to match                               |
| Xcode "Failed to register bundle identifier"               | Project settings → **Signing & Capabilities** → change Bundle Identifier to `com.<yourname>.GreenTable` |
| Xcode "No account for team"                                | Switch run target to a Simulator (top of Xcode window) — physical devices need an Apple ID              |
| iOS app: "Could not connect"                               | Is Flask still running? `curl http://127.0.0.1:5050/health` — if that fails, backend is the issue       |
| No dining halls in the app                                 | You skipped step 2 schema load: `mysql -u root -p greentable < backend/schema.sql`                      |


Forgot the MySQL root password? `brew services stop mysql && mysqld_safe --skip-grant-tables &`, then `mysql -u root` and `ALTER USER 'root'@'localhost' IDENTIFIED BY 'newpass'; FLUSH PRIVILEGES;`. Restart MySQL.

---

## Daily workflow

Two terminals + Xcode:

```bash
# Terminal 1 — backend (keep running)
cd ~/Code/GreenTable/backend && source .venv/bin/activate && python app.py

# Terminal 2 — git, tests, etc.
cd ~/Code/GreenTable
```

Stop everything with Ctrl+C in the Flask terminal and (optionally)
`brew services stop mysql`.

---

For endpoints, schema details, and audit-log notes see
`[README.md](./README.md)`.