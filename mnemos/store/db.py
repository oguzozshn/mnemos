"""SQLite storage. Single file, schema versioned with `PRAGMA user_version`."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from pathlib import Path

from mnemos.models import Message

DEFAULT_DB_PATH = Path("data") / "mnemos.db"

# Each entry migrates the schema from version i to i + 1. Append only, never edit.
MIGRATIONS: list[str] = [
    """
    CREATE TABLE conversations (
        id          TEXT PRIMARY KEY,           -- '<source>:<platform id>'
        source      TEXT NOT NULL,
        title       TEXT,
        started_at  TEXT,
        ended_at    TEXT
    );

    CREATE TABLE messages (
        id               TEXT PRIMARY KEY,      -- '<source>:<platform id>'
        source           TEXT NOT NULL,
        conversation_id  TEXT NOT NULL REFERENCES conversations(id),
        role             TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
        text             TEXT NOT NULL,
        created_at       TEXT NOT NULL,         -- ISO-8601 UTC
        position         INTEGER NOT NULL,
        lang             TEXT,                  -- phase 2
        is_noise         INTEGER                -- phase 2: NULL = not yet classified
    );

    CREATE INDEX idx_messages_conv ON messages(conversation_id, position);
    CREATE INDEX idx_messages_created ON messages(created_at);
    CREATE INDEX idx_messages_role ON messages(role);
    """,
]


def connect(path: Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    _migrate(conn)
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    for i in range(version, len(MIGRATIONS)):
        with conn:
            conn.executescript(MIGRATIONS[i])
            conn.execute(f"PRAGMA user_version = {i + 1}")


def insert_messages(conn: sqlite3.Connection, messages: Iterable[Message]) -> tuple[int, int]:
    """Insert messages, skipping ones already stored. Returns (added, skipped)."""
    added = skipped = 0
    with conn:
        for m in messages:
            conn.execute(
                """
                INSERT INTO conversations (id, source, title, started_at, ended_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    title      = COALESCE(excluded.title, conversations.title),
                    started_at = MIN(conversations.started_at, excluded.started_at),
                    ended_at   = MAX(conversations.ended_at, excluded.ended_at)
                """,
                (m.conversation_id, m.source, m.conversation_title, m.created_at, m.created_at),
            )
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO messages
                    (id, source, conversation_id, role, text, created_at, position)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (m.id, m.source, m.conversation_id, m.role, m.text, m.created_at, m.position),
            )
            if cur.rowcount:
                added += 1
            else:
                skipped += 1
    return added, skipped
