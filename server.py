"""Pulse Gym Booking - dependency-free API and static web server."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import mimetypes
import os
import secrets
import sqlite3
import threading
from datetime import datetime, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).parent
DB_PATH = ROOT / "gym_booking.db"
STATIC = ROOT / "public"
LOCK = threading.Lock()
SECRET = os.environ.get("GYM_SECRET", "local-only-development-secret").encode()


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, fields: dict | None = None):
        self.status, self.code, self.message, self.fields = status, code, message, fields


def now() -> datetime:
    return datetime.now().replace(microsecond=0)


def dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def iso(value: datetime) -> str:
    return value.replace(microsecond=0).isoformat(timespec="seconds")


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 210_000)
    return "pbkdf2_sha256$210000$%s$%s" % (
        base64.b64encode(salt).decode(), base64.b64encode(digest).decode()
    )


def password_matches(password: str, stored: str) -> bool:
    try:
        _, rounds, encoded_salt, encoded_hash = stored.split("$")
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), base64.b64decode(encoded_salt), int(rounds)
        )
        return hmac.compare_digest(base64.b64encode(digest).decode(), encoded_hash)
    except (ValueError, TypeError):
        return False


def make_code() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(6))


def issue_token(conn: sqlite3.Connection, user_id: int) -> str:
    token = secrets.token_urlsafe(36)
    token_hash = hmac.new(SECRET, token.encode(), hashlib.sha256).hexdigest()
    conn.execute(
        "INSERT INTO tokens (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
        (token_hash, user_id, iso(now() + timedelta(days=7))),
    )
    return token


def session_dict(row: sqlite3.Row, conn: sqlite3.Connection) -> dict:
    confirmed = conn.execute(
        "SELECT COUNT(*) FROM bookings WHERE session_id = ? AND status = 'confirmed'", (row["id"],)
    ).fetchone()[0]
    waitlist = conn.execute("SELECT COUNT(*) FROM waitlist WHERE session_id = ?", (row["id"],)).fetchone()[0]
    return {
        "id": row["id"], "startsAt": row["starts_at"], "capacity": row["capacity"],
        "confirmed": confirmed, "seatsRemaining": max(0, row["capacity"] - confirmed),
        "waitlistCount": waitlist, "hasStarted": dt(row["starts_at"]) <= now(),
    }


def init_db() -> None:
    fresh = not DB_PATH.exists()
    conn = db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('member', 'admin')),
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS tokens (
            id INTEGER PRIMARY KEY, token_hash TEXT NOT NULL UNIQUE, user_id INTEGER NOT NULL,
            expires_at TEXT NOT NULL, FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY, starts_at TEXT NOT NULL UNIQUE, capacity INTEGER NOT NULL DEFAULT 20 CHECK(capacity = 20),
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY, session_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('confirmed', 'cancelled')),
            checkin_code TEXT NOT NULL UNIQUE, checked_in_at TEXT, created_at TEXT NOT NULL,
            FOREIGN KEY(session_id) REFERENCES sessions(id), FOREIGN KEY(user_id) REFERENCES users(id)
        );
        CREATE UNIQUE INDEX IF NOT EXISTS one_active_booking ON bookings(session_id, user_id) WHERE status = 'confirmed';
        CREATE INDEX IF NOT EXISTS booking_session_status ON bookings(session_id, status);
        CREATE TABLE IF NOT EXISTS waitlist (
            id INTEGER PRIMARY KEY, session_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
            joined_at TEXT NOT NULL, FOREIGN KEY(session_id) REFERENCES sessions(id),
            FOREIGN KEY(user_id) REFERENCES users(id), UNIQUE(session_id, user_id)
        );
    """)
    if fresh:
        seed(conn)
    conn.close()


def seed(conn: sqlite3.Connection) -> None:
    stamp = iso(now())
    people = [
        ("Pulse Admin", "admin@pulsegym.test", "admin"),
        ("Alex Morgan", "alex@pulsegym.test", "member"),
        ("Sam Rivera", "sam@pulsegym.test", "member"),
    ] + [(f"Demo Member {n:02d}", f"demo{n:02d}@pulsegym.test", "member") for n in range(1, 22)]
    for name, email, role in people:
        conn.execute(
            "INSERT INTO users (name, email, password_hash, role, created_at) VALUES (?, ?, ?, ?, ?)",
            (name, email, hash_password("MoveStrong2026!"), role, stamp),
        )
    base = now().replace(minute=0, second=0) + timedelta(days=1, hours=7)
    hours = [7, 12, 18, 7, 18, 12]
    ids = []
    for offset, hour in enumerate(hours):
        start = (base + timedelta(days=offset // 2)).replace(hour=hour)
        cur = conn.execute("INSERT INTO sessions (starts_at, capacity, created_at) VALUES (?, 20, ?)", (iso(start), stamp))
        ids.append(cur.lastrowid)
    # A deliberately full fixture session for waitlist behaviour.
    full_session = ids[3]
    member_ids = [r[0] for r in conn.execute("SELECT id FROM users WHERE role = 'member' ORDER BY id LIMIT 20")]
    for member_id in member_ids:
        conn.execute(
            "INSERT INTO bookings (session_id, user_id, status, checkin_code, created_at) VALUES (?, ?, 'confirmed', ?, ?)",
            (full_session, member_id, make_code(), stamp),
        )
    conn.commit()


def require_fields(payload: dict, required: list[str]) -> None:
    missing = {name: "Required" for name in required if not str(payload.get(name, "")).strip()}
    if missing:
        raise ApiError(422, "validation_error", "Please correct the highlighted fields.", missing)


class App(BaseHTTPRequestHandler):
    server_version = "PulseGym/1.0"

    def log_message(self, *_args):
        pass

    def send_json(self, status: int, data: dict | list) -> None:
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def error(self, status: int, code: str, message: str, fields: dict | None = None) -> None:
        detail = {"code": code, "message": message}
        if fields:
            detail["fields"] = fields
        self.send_json(status, {"error": detail})

    def payload(self) -> dict:
        size = int(self.headers.get("Content-Length", "0"))
        if not size:
            return {}
        try:
            value = json.loads(self.rfile.read(size))
            if not isinstance(value, dict):
                raise ValueError
            return value
        except (ValueError, UnicodeDecodeError):
            raise ApiError(400, "invalid_json", "Request body must be valid JSON.")

    def user(self, conn: sqlite3.Connection, roles: tuple[str, ...] | None = None) -> sqlite3.Row:
        auth = self.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            raise ApiError(401, "unauthenticated", "Sign in to continue.")
        token_hash = hmac.new(SECRET, auth[7:].encode(), hashlib.sha256).hexdigest()
        person = conn.execute("""
            SELECT users.* FROM tokens JOIN users ON users.id = tokens.user_id
            WHERE tokens.token_hash = ? AND tokens.expires_at > ?
        """, (token_hash, iso(now()))).fetchone()
        if not person:
            raise ApiError(401, "unauthenticated", "Your session has expired. Please sign in again.")
        if roles and person["role"] not in roles:
            raise ApiError(403, "forbidden", "You do not have permission to do that.")
        return person

    def route(self, method: str, path: str, query: dict, payload: dict, conn: sqlite3.Connection):
        if method == "GET" and path == "/api/health":
            return 200, {"ok": True}
        if method == "POST" and path == "/api/auth/register":
            require_fields(payload, ["name", "email", "password"])
            email = payload["email"].strip().lower()
            fields = {}
            if "@" not in email or len(email) > 254: fields["email"] = "Enter a valid email address."
            if len(payload["name"].strip()) < 2: fields["name"] = "Name must be at least 2 characters."
            if len(payload["password"]) < 10: fields["password"] = "Use at least 10 characters."
            if fields: raise ApiError(422, "validation_error", "Please correct the highlighted fields.", fields)
            try:
                cur = conn.execute("INSERT INTO users (name, email, password_hash, role, created_at) VALUES (?, ?, ?, 'member', ?)",
                    (payload["name"].strip(), email, hash_password(payload["password"]), iso(now())))
            except sqlite3.IntegrityError:
                raise ApiError(409, "email_taken", "An account already uses that email.", {"email": "This email is already registered."})
            person = conn.execute("SELECT * FROM users WHERE id = ?", (cur.lastrowid,)).fetchone()
            return 201, {"token": issue_token(conn, person["id"]), "user": self.public_user(person)}
        if method == "POST" and path == "/api/auth/login":
            require_fields(payload, ["email", "password"])
            person = conn.execute("SELECT * FROM users WHERE email = ?", (payload["email"].strip().lower(),)).fetchone()
            if not person or not password_matches(payload["password"], person["password_hash"]):
                raise ApiError(401, "invalid_credentials", "Email or password is incorrect.")
            return 200, {"token": issue_token(conn, person["id"]), "user": self.public_user(person)}
        if method == "GET" and path == "/api/me":
            return 200, {"user": self.public_user(self.user(conn))}
        if method == "GET" and path == "/api/sessions":
            person = self.user(conn)
            date_filter = (query.get("date") or [""])[0]
            args = [iso(now())]
            sql = "SELECT * FROM sessions WHERE starts_at > ?"
            if date_filter:
                try: datetime.strptime(date_filter, "%Y-%m-%d")
                except ValueError: raise ApiError(422, "validation_error", "Date must use YYYY-MM-DD.", {"date": "Choose a valid date."})
                sql += " AND starts_at LIKE ?"; args.append(f"{date_filter}%")
            sql += " ORDER BY starts_at"
            items = [session_dict(row, conn) for row in conn.execute(sql, args)]
            if person["role"] == "member":
                booked = {r[0] for r in conn.execute("SELECT session_id FROM bookings WHERE user_id=? AND status='confirmed'", (person["id"],))}
                waiting = {r[0] for r in conn.execute("SELECT session_id FROM waitlist WHERE user_id=?", (person["id"],))}
                for item in items:
                    item["myStatus"] = "booked" if item["id"] in booked else "waitlisted" if item["id"] in waiting else None
            return 200, {"sessions": items}
        if method == "POST" and path == "/api/sessions":
            self.user(conn, ("admin",))
            require_fields(payload, ["startsAt"])
            try:
                starts = dt(payload["startsAt"])
                if starts.minute or starts.second or starts <= now(): raise ValueError
            except (ValueError, TypeError):
                raise ApiError(422, "validation_error", "Sessions must start on a future hour.", {"startsAt": "Choose a future whole hour."})
            try:
                cur = conn.execute("INSERT INTO sessions (starts_at, capacity, created_at) VALUES (?, 20, ?)", (iso(starts), iso(now())))
            except sqlite3.IntegrityError:
                raise ApiError(409, "session_exists", "A session already starts at that time.", {"startsAt": "This hour is already in use."})
            row = conn.execute("SELECT * FROM sessions WHERE id = ?", (cur.lastrowid,)).fetchone()
            return 201, {"session": session_dict(row, conn)}
        if method == "GET" and path == "/api/bookings/me":
            person = self.user(conn, ("member",))
            rows = conn.execute("""
                SELECT b.*, s.starts_at, s.capacity FROM bookings b JOIN sessions s ON s.id = b.session_id
                WHERE b.user_id = ? AND b.status = 'confirmed' ORDER BY s.starts_at
            """, (person["id"],))
            return 200, {"bookings": [self.booking_dict(row, conn) for row in rows]}
        if path.startswith("/api/sessions/"):
            bits = path.strip("/").split("/")
            if len(bits) >= 3:
                try: session_id = int(bits[2])
                except ValueError: raise ApiError(404, "not_found", "Session not found.")
                if len(bits) == 4 and bits[3] == "book" and method == "POST":
                    person = self.user(conn, ("member",)); return self.book(conn, person, session_id)
                if len(bits) == 4 and bits[3] == "waitlist":
                    person = self.user(conn, ("member",))
                    return self.waitlist(conn, person, session_id, method)
        if path.startswith("/api/bookings/") and method == "DELETE":
            person = self.user(conn, ("member",))
            try: booking_id = int(path.rsplit("/", 1)[1])
            except ValueError: raise ApiError(404, "not_found", "Booking not found.")
            return self.cancel(conn, person, booking_id)
        if path.startswith("/api/admin/sessions/") and path.endswith("/bookings") and method == "GET":
            self.user(conn, ("admin",))
            try: session_id = int(path.split("/")[4])
            except ValueError: raise ApiError(404, "not_found", "Session not found.")
            row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
            if not row: raise ApiError(404, "not_found", "Session not found.")
            bookings = conn.execute("""
              SELECT b.*, u.name, u.email, s.starts_at, s.capacity FROM bookings b
              JOIN users u ON u.id = b.user_id JOIN sessions s ON s.id = b.session_id
              WHERE b.session_id = ? AND b.status = 'confirmed' ORDER BY b.created_at
            """, (session_id,))
            waiting = conn.execute("""
              SELECT w.id, w.joined_at, u.name, u.email FROM waitlist w JOIN users u ON u.id = w.user_id
              WHERE w.session_id = ? ORDER BY w.joined_at
            """, (session_id,))
            return 200, {"session": session_dict(row, conn), "bookings": [self.booking_dict(x, conn, admin=True) for x in bookings], "waitlist": [dict(x) for x in waiting]}
        if path == "/api/admin/check-in" and method == "POST":
            self.user(conn, ("admin",)); require_fields(payload, ["code"])
            code = payload["code"].strip().upper()
            row = conn.execute("""
              SELECT b.*, u.name, u.email, s.starts_at, s.capacity FROM bookings b
              JOIN users u ON u.id = b.user_id JOIN sessions s ON s.id = b.session_id
              WHERE b.checkin_code = ? AND b.status = 'confirmed'
            """, (code,)).fetchone()
            if not row: raise ApiError(404, "invalid_code", "No active booking uses that code.")
            starts, ends = dt(row["starts_at"]), dt(row["starts_at"]) + timedelta(hours=1)
            if not (starts <= now() < ends): raise ApiError(409, "checkin_window", "This code can only be used during its session hour.")
            if row["checked_in_at"]: raise ApiError(409, "already_checked_in", "This booking has already been checked in.")
            conn.execute("UPDATE bookings SET checked_in_at = ? WHERE id = ?", (iso(now()), row["id"]))
            return 200, {"booking": self.booking_dict(row, conn, admin=True), "message": f"{row['name']} is checked in."}
        raise ApiError(404, "not_found", "That route does not exist.")

    @staticmethod
    def public_user(row: sqlite3.Row) -> dict:
        return {"id": row["id"], "name": row["name"], "email": row["email"], "role": row["role"]}

    @staticmethod
    def booking_dict(row: sqlite3.Row, conn: sqlite3.Connection, admin: bool = False) -> dict:
        item = {"id": row["id"], "sessionId": row["session_id"], "startsAt": row["starts_at"], "code": row["checkin_code"], "checkedInAt": row["checked_in_at"]}
        if admin: item.update({"name": row["name"], "email": row["email"]})
        return item

    def book(self, conn: sqlite3.Connection, person: sqlite3.Row, session_id: int):
        with LOCK:
            conn.execute("BEGIN IMMEDIATE")
            try:
                session = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
                if not session: raise ApiError(404, "not_found", "Session not found.")
                if dt(session["starts_at"]) <= now(): raise ApiError(409, "session_started", "This session has already started.")
                existing = conn.execute("SELECT id FROM bookings WHERE session_id = ? AND user_id = ? AND status = 'confirmed'", (session_id, person["id"])).fetchone()
                if existing: raise ApiError(409, "already_booked", "You already have a booking for this session.")
                taken = conn.execute("SELECT COUNT(*) FROM bookings WHERE session_id = ? AND status = 'confirmed'", (session_id,)).fetchone()[0]
                if taken >= session["capacity"]: raise ApiError(409, "session_full", "This session is full. You can join the waitlist.")
                cur = conn.execute("INSERT INTO bookings (session_id, user_id, status, checkin_code, created_at) VALUES (?, ?, 'confirmed', ?, ?)", (session_id, person["id"], make_code(), iso(now())))
                conn.execute("DELETE FROM waitlist WHERE session_id = ? AND user_id = ?", (session_id, person["id"]))
                row = conn.execute("SELECT b.*, s.starts_at FROM bookings b JOIN sessions s ON s.id=b.session_id WHERE b.id=?", (cur.lastrowid,)).fetchone()
                conn.commit()
                return 201, {"booking": self.booking_dict(row, conn)}
            except Exception:
                conn.rollback(); raise

    def waitlist(self, conn: sqlite3.Connection, person: sqlite3.Row, session_id: int, method: str):
        if method == "DELETE":
            cur = conn.execute("DELETE FROM waitlist WHERE session_id = ? AND user_id = ?", (session_id, person["id"]))
            if not cur.rowcount: raise ApiError(404, "not_found", "You are not on this waitlist.")
            return 200, {"message": "You left the waitlist."}
        if method != "POST": raise ApiError(404, "not_found", "That route does not exist.")
        with LOCK:
            conn.execute("BEGIN IMMEDIATE")
            try:
                session = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
                if not session: raise ApiError(404, "not_found", "Session not found.")
                if dt(session["starts_at"]) <= now(): raise ApiError(409, "session_started", "This session has already started.")
                taken = conn.execute("SELECT COUNT(*) FROM bookings WHERE session_id = ? AND status = 'confirmed'", (session_id,)).fetchone()[0]
                if taken < session["capacity"]: raise ApiError(409, "seats_available", "A seat is available - book it instead.")
                try: conn.execute("INSERT INTO waitlist (session_id, user_id, joined_at) VALUES (?, ?, ?)", (session_id, person["id"], iso(now())))
                except sqlite3.IntegrityError: raise ApiError(409, "already_waitlisted", "You are already on the waitlist.")
                conn.commit(); return 201, {"message": "You are on the waitlist."}
            except Exception:
                conn.rollback(); raise

    def cancel(self, conn: sqlite3.Connection, person: sqlite3.Row, booking_id: int):
        with LOCK:
            conn.execute("BEGIN IMMEDIATE")
            try:
                booking = conn.execute("""
                  SELECT b.*, s.starts_at, s.capacity FROM bookings b JOIN sessions s ON s.id=b.session_id
                  WHERE b.id=? AND b.user_id=? AND b.status='confirmed'
                """, (booking_id, person["id"])).fetchone()
                if not booking: raise ApiError(404, "not_found", "Booking not found.")
                if dt(booking["starts_at"]) <= now(): raise ApiError(409, "session_started", "Bookings cannot be cancelled after a session starts.")
                conn.execute("UPDATE bookings SET status='cancelled' WHERE id=?", (booking_id,))
                next_member = conn.execute("SELECT * FROM waitlist WHERE session_id=? ORDER BY joined_at, id LIMIT 1", (booking["session_id"],)).fetchone()
                promoted = None
                if next_member and dt(booking["starts_at"]) > now():
                    cur = conn.execute("INSERT INTO bookings (session_id, user_id, status, checkin_code, created_at) VALUES (?, ?, 'confirmed', ?, ?)", (booking["session_id"], next_member["user_id"], make_code(), iso(now())))
                    conn.execute("DELETE FROM waitlist WHERE id=?", (next_member["id"],))
                    promoted = cur.lastrowid
                conn.commit(); return 200, {"message": "Your booking was cancelled.", "promotedBookingId": promoted}
            except Exception:
                conn.rollback(); raise

    def handle_api(self, method: str):
        parsed = urlparse(self.path)
        conn = db()
        try:
            status, data = self.route(method, parsed.path, parse_qs(parsed.query), self.payload() if method in ("POST", "PUT", "PATCH") else {}, conn)
            conn.commit(); self.send_json(status, data)
        except ApiError as error:
            conn.rollback(); self.error(error.status, error.code, error.message, error.fields)
        except Exception:
            conn.rollback(); self.error(500, "server_error", "Something went wrong. Please try again.")
        finally:
            conn.close()

    def do_GET(self):
        if self.path.startswith("/api/"):
            self.handle_api("GET"); return
        parsed = urlparse(self.path)
        name = "index.html" if parsed.path in ("/", "") else parsed.path.lstrip("/")
        target = (STATIC / name).resolve()
        if not str(target).startswith(str(STATIC.resolve())) or not target.is_file():
            target = STATIC / "index.html"
        raw = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(target.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers(); self.wfile.write(raw)

    def do_POST(self): self.handle_api("POST")
    def do_DELETE(self): self.handle_api("DELETE")


if __name__ == "__main__":
    init_db()
    print("Pulse Gym is running at http://localhost:8080")
    ThreadingHTTPServer(("", 8080), App).serve_forever()
