# © 2026 Bryan Gil — github.com/Bryanhackz — br4yangil006@gmail.com
"""Fixed-window rate limiting persisted in SQLite."""

from __future__ import annotations

import sqlite3
import time

WINDOW_SEC = 60


def _now() -> int:
    """Current epoch seconds as int."""
    return int(time.time())


def check_and_increment(
    conn: sqlite3.Connection, scope: str, identity: str, limit_per_min: int
) -> bool:
    """Return True if allowed (and increment), False if limited. Transaction required."""
    now = _now()
    window_start = now - (now % WINDOW_SEC)
    row = conn.execute(
        "SELECT count FROM rate_limit_buckets"
        " WHERE scope=? AND identity=? AND window_start=?",
        (scope, identity, window_start),
    ).fetchone()
    current = int(row["count"]) if row else 0
    if current >= limit_per_min:
        return False
    if row:
        conn.execute(
            "UPDATE rate_limit_buckets SET count=count+1"
            " WHERE scope=? AND identity=? AND window_start=?",
            (scope, identity, window_start),
        )
    else:
        conn.execute(
            "INSERT INTO rate_limit_buckets(scope, identity, window_start, count)"
            " VALUES(?,?,?,1)",
            (scope, identity, window_start),
        )
    return True