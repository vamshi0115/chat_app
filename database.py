"""
database.py — SQLite schema and helper functions for Oasis Chat.

Tables
------
users        : id, username (unique), password_hash, created_at
rooms        : id, name (NOT unique — duplicates allowed), description,
               created_by, created_at
room_members : room_id, user_id, joined_at   (tracks who is in which room)
messages     : id, room_id, user_id, content, created_at

Security note: passwords are stored as Werkzeug PBKDF2-SHA256 hashes.
Message content is stored as plain-text UTF-8 in SQLite — see README.
"""

import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "chat.db")


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """Create tables (idempotent). Seeds the default 'general' room."""
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                username      TEXT    NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT    NOT NULL,
                created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS rooms (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT    NOT NULL COLLATE NOCASE,
                description TEXT    NOT NULL DEFAULT '',
                created_by  INTEGER REFERENCES users(id),
                created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS room_members (
                room_id   INTEGER NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
                user_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                joined_at TEXT    NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (room_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS messages (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                room_id    INTEGER NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
                user_id    INTEGER NOT NULL REFERENCES users(id),
                content    TEXT    NOT NULL,
                created_at TEXT    NOT NULL DEFAULT (datetime('now'))
            );
            """
        )
        # Auto-migrate: add description column if the DB was created with old schema
        existing_cols = [
            r[1] for r in conn.execute("PRAGMA table_info(rooms)").fetchall()
        ]
        if "description" not in existing_cols:
            conn.execute(
                "ALTER TABLE rooms ADD COLUMN description TEXT NOT NULL DEFAULT ''"
            )

        # Seed default room if no rooms exist yet
        count = conn.execute("SELECT COUNT(*) FROM rooms").fetchone()[0]
        if count == 0:
            conn.execute(
                "INSERT INTO rooms (name, description, created_by) VALUES ('general', 'Default room', NULL)"
            )


# ── Users ──────────────────────────────────────────────────────────────────

def create_user(username: str, password_hash: str) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            (username, password_hash),
        )
        return cur.lastrowid


def get_user_by_username(username: str) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()


def get_user_by_id(user_id: int) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()


# ── Rooms ──────────────────────────────────────────────────────────────────

def _room_row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


def get_all_rooms() -> list[dict]:
    """Return all rooms with live member_count."""
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT r.*,
                   (SELECT COUNT(*) FROM room_members rm WHERE rm.room_id = r.id) AS member_count,
                   u.username AS creator_name
            FROM   rooms r
            LEFT JOIN users u ON u.id = r.created_by
            ORDER  BY r.created_at DESC
            """
        ).fetchall()
    return [dict(r) for r in rows]


def search_rooms(query: str) -> list[dict]:
    """Case-insensitive substring search on room name."""
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT r.*,
                   (SELECT COUNT(*) FROM room_members rm WHERE rm.room_id = r.id) AS member_count,
                   u.username AS creator_name
            FROM   rooms r
            LEFT JOIN users u ON u.id = r.created_by
            WHERE  LOWER(r.name) LIKE LOWER(?)
            ORDER  BY r.created_at DESC
            """,
            (f"%{query}%",),
        ).fetchall()
    return [dict(r) for r in rows]


def get_room_by_id(room_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT r.*,
                   (SELECT COUNT(*) FROM room_members rm WHERE rm.room_id = r.id) AS member_count,
                   u.username AS creator_name
            FROM   rooms r
            LEFT JOIN users u ON u.id = r.created_by
            WHERE  r.id = ?
            """,
            (room_id,),
        ).fetchone()
    return dict(row) if row else None


def create_room(name: str, description: str, created_by: int) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO rooms (name, description, created_by) VALUES (?, ?, ?)",
            (name, description, created_by),
        )
        return cur.lastrowid


def update_room(room_id: int, name: str, description: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE rooms SET name = ?, description = ? WHERE id = ?",
            (name, description, room_id),
        )


def delete_room(room_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM rooms WHERE id = ?", (room_id,))


# ── Room members ───────────────────────────────────────────────────────────

def add_member(room_id: int, user_id: int) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO room_members (room_id, user_id) VALUES (?, ?)",
            (room_id, user_id),
        )


def remove_member(room_id: int, user_id: int) -> None:
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM room_members WHERE room_id = ? AND user_id = ?",
            (room_id, user_id),
        )


def get_member_count(room_id: int) -> int:
    with get_conn() as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM room_members WHERE room_id = ?", (room_id,)
        ).fetchone()[0]


def get_user_rooms(user_id: int) -> list[dict]:
    """Return rooms the user has joined, with member_count."""
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT r.*,
                   (SELECT COUNT(*) FROM room_members rm2 WHERE rm2.room_id = r.id) AS member_count,
                   u.username AS creator_name
            FROM   room_members rm
            JOIN   rooms r  ON r.id  = rm.room_id
            LEFT JOIN users u ON u.id = r.created_by
            WHERE  rm.user_id = ?
            ORDER  BY rm.joined_at DESC
            """,
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


# ── Messages ───────────────────────────────────────────────────────────────

def save_message(room_id: int, user_id: int, content: str) -> dict:
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO messages (room_id, user_id, content, created_at) VALUES (?, ?, ?, ?)",
            (room_id, user_id, content, now),
        )
        return {"id": cur.lastrowid, "created_at": now}


def get_room_history(room_id: int, limit: int = 50) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT m.id, m.content, m.created_at,
                   u.username
            FROM   messages m
            JOIN   users u ON u.id = m.user_id
            WHERE  m.room_id = ?
            ORDER  BY m.created_at DESC
            LIMIT  ?
            """,
            (room_id, limit),
        ).fetchall()
    return [dict(r) for r in reversed(rows)]
