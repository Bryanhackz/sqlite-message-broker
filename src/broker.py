# © 2026 Bryan Gil — github.com/Bryanhackz — br4yangil006@gmail.com
"""Broker core: claim, ack, nack, retry with exponential backoff, reap."""

from __future__ import annotations

import secrets
import sqlite3
import time
from dataclasses import dataclass

from src.config import Config

REAP_BATCH_LIMIT = 100


@dataclass
class Message:
    """A message claimed by a consumer under a lease."""

    id: int
    queue: str
    body: str
    attempts: int
    lease_token: str
    lease_expiry: int


def _now() -> int:
    """Current epoch seconds as int."""
    return int(time.time())


def _backoff(cfg: Config, attempts: int) -> int:
    """Exponential backoff: base * 2**(attempts-1), capped at max."""
    delay = cfg.backoff_base_sec * (2 ** max(0, attempts - 1))
    return min(delay, cfg.backoff_max_sec)


def ensure_queue(conn: sqlite3.Connection, name: str) -> int:
    """Return queue id, creating it if absent. Must run inside a transaction."""
    row = conn.execute("SELECT id FROM queues WHERE name=?", (name,)).fetchone()
    if row:
        return int(row["id"])
    cur = conn.execute(
        "INSERT INTO queues(name, created_at) VALUES(?,?)", (name, _now())
    )
    return int(cur.lastrowid)


def enqueue(conn: sqlite3.Connection, queue: str, body: str) -> int:
    """Enqueue a message and return its id. Requires a transaction wrapper."""
    qid = ensure_queue(conn, queue)
    now = _now()
    cur = conn.execute(
        "INSERT INTO messages(queue_id, body, state, attempts, visible_at,"
        " created_at, updated_at) VALUES(?,?,'pending',0,?,?,?)",
        (qid, body, now, now, now),
    )
    return int(cur.lastrowid)


def claim(conn: sqlite3.Connection, queue: str, cfg: Config) -> Message | None:
    """Claim one visible pending message under a fresh lease. Transaction required."""
    now = _now()
    row = conn.execute(
        "SELECT m.id, m.body, m.attempts FROM messages m"
        " JOIN queues q ON q.id = m.queue_id"
        " WHERE q.name=? AND m.state='pending' AND m.visible_at<=?"
        " ORDER BY m.id ASC LIMIT 1",
        (queue, now),
    ).fetchone()
    if row is None:
        return None
    token = secrets.token_urlsafe(24)
    expiry = now + cfg.visibility_timeout_sec
    conn.execute(
        "UPDATE messages SET state='processing', lease_token=?,"
        " lease_expiry=?, attempts=attempts+1, updated_at=? WHERE id=?",
        (token, expiry, now, row["id"]),
    )
    return Message(
        id=int(row["id"]),
        queue=queue,
        body=str(row["body"]),
        attempts=int(row["attempts"]) + 1,
        lease_token=token,
        lease_expiry=expiry,
    )


def ack(conn: sqlite3.Connection, msg_id: int, token: str) -> bool:
    """Mark a message done if the lease token matches. Returns success."""
    cur = conn.execute(
        "UPDATE messages SET state='done', lease_token=NULL, lease_expiry=NULL,"
        " updated_at=? WHERE id=? AND lease_token=? AND state='processing'",
        (_now(), msg_id, token),
    )
    return cur.rowcount == 1


def nack(conn: sqlite3.Connection, msg_id: int, token: str, cfg: Config) -> str:
    """Return 'retry' or 'dlq' or 'noop' and update state accordingly."""
    now = _now()
    row = conn.execute(
        "SELECT attempts FROM messages"
        " WHERE id=? AND lease_token=? AND state='processing'",
        (msg_id, token),
    ).fetchone()
    if row is None:
        return "noop"
    attempts = int(row["attempts"])
    if attempts >= cfg.max_attempts:
        conn.execute(
            "UPDATE messages SET state='dead', lease_token=NULL, lease_expiry=NULL,"
            " updated_at=? WHERE id=?",
            (now, msg_id),
        )
        return "dlq"
    delay = _backoff(cfg, attempts)
    conn.execute(
        "UPDATE messages SET state='pending', lease_token=NULL, lease_expiry=NULL,"
        " visible_at=?, updated_at=? WHERE id=?",
        (now + delay, now, msg_id),
    )
    return "retry"


def reap_expired(conn: sqlite3.Connection, cfg: Config) -> int:
    """Reset expired processing leases. Batched to keep DB locks short."""
    now = _now()
    rows = conn.execute(
        "SELECT id, attempts FROM messages"
        " WHERE state='processing' AND lease_expiry<? LIMIT ?",
        (now, REAP_BATCH_LIMIT),
    ).fetchall()
    if not rows:
        return 0
    dead_ids = [int(r["id"]) for r in rows if int(r["attempts"]) >= cfg.max_attempts]
    retry_ids = [int(r["id"]) for r in rows if int(r["attempts"]) < cfg.max_attempts]
    if dead_ids:
        placeholders = ",".join("?" * len(dead_ids))
        conn.execute(
            f"UPDATE messages SET state='dead', lease_token=NULL, lease_expiry=NULL,"
            f" updated_at=? WHERE id IN ({placeholders})",
            (now, *dead_ids),
        )
    if retry_ids:
        placeholders = ",".join("?" * len(retry_ids))
        conn.execute(
            f"UPDATE messages SET state='pending', lease_token=NULL, lease_expiry=NULL,"
            f" visible_at=?, updated_at=? WHERE id IN ({placeholders})",
            (now, now, *retry_ids),
        )
    return len(rows)