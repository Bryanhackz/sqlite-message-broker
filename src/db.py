# © 2026 Bryan Gil — github.com/Bryanhackz — br4yangil006@gmail.com
"""SQLite persistence layer: schema, connection, transactions, bootstrap."""

from __future__ import annotations

import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Iterator

from src.config import Config

SCHEMA = """
CREATE TABLE IF NOT EXISTS queues (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL UNIQUE,
    created_at  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    queue_id      INTEGER NOT NULL REFERENCES queues(id) ON DELETE CASCADE,
    body          TEXT    NOT NULL,
    state         TEXT    NOT NULL CHECK (state IN ('pending','processing','done','dead')),
    attempts      INTEGER NOT NULL DEFAULT 0,
    visible_at    INTEGER NOT NULL,
    lease_token   TEXT,
    lease_expiry  INTEGER,
    created_at    INTEGER NOT NULL,
    updated_at    INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_claim
    ON messages(queue_id, state, visible_at);
CREATE INDEX IF NOT EXISTS idx_messages_lease
    ON messages(lease_token);
CREATE INDEX IF NOT EXISTS idx_messages_state
    ON messages(state);

CREATE TABLE IF NOT EXISTS api_keys (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    role        TEXT    NOT NULL CHECK (role IN ('producer','consumer','admin')),
    label       TEXT    NOT NULL,
    key_prefix  TEXT    NOT NULL,
    key_hash    BLOB    NOT NULL,
    key_salt    BLOB    NOT NULL,
    created_at  INTEGER NOT NULL,
    revoked_at  INTEGER
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_api_keys_label ON api_keys(label);
CREATE UNIQUE INDEX IF NOT EXISTS idx_api_keys_prefix ON api_keys(key_prefix);

CREATE TABLE IF NOT EXISTS rate_limit_buckets (
    scope        TEXT    NOT NULL,
    identity     TEXT    NOT NULL,
    window_start INTEGER NOT NULL,
    count        INTEGER NOT NULL,
    PRIMARY KEY (scope, identity, window_start)
);

CREATE TABLE IF NOT EXISTS audit_log (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      INTEGER NOT NULL,
    event   TEXT    NOT NULL,
    actor   TEXT,
    detail  TEXT,
    ip      TEXT
);
CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log(ts);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    """Open a SQLite connection configured for WAL, FK, and concurrent access."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(
        str(db_path),
        timeout=5.0,
        isolation_level=None,
        check_same_thread=False,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_db(cfg: Config) -> None:
    """Create schema if absent. Idempotent. Closes the connection explicitly."""
    with closing(connect(cfg.db_path)) as conn:
        conn.executescript(SCHEMA)


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """BEGIN IMMEDIATE transaction; rollback on exception, commit on success."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise