# © 2026 Bryan Gil — github.com/Bryanhackz — br4yangil006@gmail.com
"""Tests for src.db: schema idempotency, WAL, FK enforcement, transaction rollback."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from src.config import Config
from src.db import connect, init_db, transaction


def _cfg(td: str) -> Config:
    return Config(
        host="127.0.0.1", port=8080, env="dev",
        db_path=Path(td) / "t.db",
        visibility_timeout_sec=30, max_attempts=3,
        backoff_base_sec=1, backoff_max_sec=10, retention_days=7,
        rl_producer_per_min=10, rl_consumer_per_min=10, rl_login_per_min=10,
        lockout_fails=5, lockout_window_sec=900,
        scrypt_n=1024, scrypt_r=8, scrypt_p=1, log_level="INFO",
    )


class TestSchema(unittest.TestCase):
    """Schema creation must be idempotent and produce the expected tables."""

    def test_tables_present(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            cfg = _cfg(td)
            init_db(cfg)
            init_db(cfg)  # idempotent
            with closing(connect(cfg.db_path)) as conn:
                rows = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            names = {r["name"] for r in rows}
            for expected in ("queues", "messages", "api_keys",
                             "rate_limit_buckets", "audit_log"):
                self.assertIn(expected, names)

    def test_wal_mode(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            cfg = _cfg(td)
            init_db(cfg)
            with closing(connect(cfg.db_path)) as conn:
                mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            self.assertEqual(mode.lower(), "wal")

    def test_foreign_keys_enforced(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            cfg = _cfg(td)
            init_db(cfg)
            with closing(connect(cfg.db_path)) as conn:
                with self.assertRaises(sqlite3.IntegrityError):
                    conn.execute(
                        "INSERT INTO messages(queue_id, body, state, attempts,"
                        " visible_at, created_at, updated_at)"
                        " VALUES(9999,'x','pending',0,0,0,0)"
                    )

    def test_busy_timeout_applied(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            cfg = _cfg(td)
            init_db(cfg)
            with closing(connect(cfg.db_path)) as conn:
                val = conn.execute("PRAGMA busy_timeout").fetchone()[0]
            self.assertEqual(val, 5000)


class TestTransaction(unittest.TestCase):
    """BEGIN IMMEDIATE must roll back atomically on error."""

    def test_rollback_on_error(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            cfg = _cfg(td)
            init_db(cfg)
            with closing(connect(cfg.db_path)) as conn:
                try:
                    with transaction(conn):
                        conn.execute("INSERT INTO queues(name,created_at) VALUES('a',0)")
                        raise RuntimeError("boom")
                except RuntimeError:
                    pass
                rows = conn.execute("SELECT * FROM queues").fetchall()
            self.assertEqual(len(rows), 0, "rollback must undo insert")


if __name__ == "__main__":
    unittest.main()