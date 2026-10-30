# © 2026 Bryan Gil — github.com/Bryanhackz — br4yangil006@gmail.com
"""Tests for src.broker: enqueue, claim, ack, nack retry/dlq, reap_expired."""

from __future__ import annotations

import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from src.broker import ack, claim, enqueue, nack, reap_expired
from src.config import Config
from src.db import connect, init_db, transaction


def _cfg(td: str, **overrides) -> Config:
    base = dict(
        host="127.0.0.1", port=8080, env="dev",
        db_path=Path(td) / "b.db",
        visibility_timeout_sec=30, max_attempts=2,
        backoff_base_sec=1, backoff_max_sec=10, retention_days=7,
        rl_producer_per_min=10, rl_consumer_per_min=10, rl_login_per_min=10,
        lockout_fails=5, lockout_window_sec=900,
        scrypt_n=1024, scrypt_r=8, scrypt_p=1, log_level="INFO",
    )
    base.update(overrides)
    return Config(**base)


class TestEnqueueClaim(unittest.TestCase):
    """Happy path: enqueue → claim returns a leased message."""

    def test_enqueue_then_claim(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            cfg = _cfg(td)
            init_db(cfg)
            with closing(connect(cfg.db_path)) as conn:
                with transaction(conn):
                    enqueue(conn, "q", "hello")
                with transaction(conn):
                    msg = claim(conn, "q", cfg)
            self.assertIsNotNone(msg, "should claim one message")
            self.assertEqual(msg.body, "hello")
            self.assertEqual(msg.attempts, 1)

    def test_claim_empty_returns_none(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            cfg = _cfg(td)
            init_db(cfg)
            with closing(connect(cfg.db_path)) as conn:
                with transaction(conn):
                    msg = claim(conn, "empty", cfg)
            self.assertIsNone(msg)


class TestAckNack(unittest.TestCase):
    """ack transitions to done; nack retries or escalates to dlq."""

    def test_ack_marks_done(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            cfg = _cfg(td)
            init_db(cfg)
            with closing(connect(cfg.db_path)) as conn:
                with transaction(conn):
                    enqueue(conn, "q", "x")
                with transaction(conn):
                    msg = claim(conn, "q", cfg)
                with transaction(conn):
                    ok = ack(conn, msg.id, msg.lease_token)
                state = conn.execute(
                    "SELECT state FROM messages WHERE id=?", (msg.id,)
                ).fetchone()["state"]
            self.assertTrue(ok)
            self.assertEqual(state, "done")

    def test_ack_wrong_token_rejected(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            cfg = _cfg(td)
            init_db(cfg)
            with closing(connect(cfg.db_path)) as conn:
                with transaction(conn):
                    enqueue(conn, "q", "x")
                with transaction(conn):
                    msg = claim(conn, "q", cfg)
                with transaction(conn):
                    ok = ack(conn, msg.id, "wrong-token")
            self.assertFalse(ok)

    def test_nack_retries_below_max(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            cfg = _cfg(td, max_attempts=2)
            init_db(cfg)
            with closing(connect(cfg.db_path)) as conn:
                with transaction(conn):
                    enqueue(conn, "q", "x")
                with transaction(conn):
                    msg = claim(conn, "q", cfg)
                with transaction(conn):
                    result = nack(conn, msg.id, msg.lease_token, cfg)
            self.assertEqual(result, "retry")

    def test_nack_escalates_to_dlq(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            cfg = _cfg(td, max_attempts=1)
            init_db(cfg)
            with closing(connect(cfg.db_path)) as conn:
                with transaction(conn):
                    enqueue(conn, "q", "x")
                with transaction(conn):
                    msg = claim(conn, "q", cfg)
                with transaction(conn):
                    result = nack(conn, msg.id, msg.lease_token, cfg)
                state = conn.execute(
                    "SELECT state FROM messages WHERE id=?", (msg.id,)
                ).fetchone()["state"]
            self.assertEqual(result, "dlq")
            self.assertEqual(state, "dead")


class TestReap(unittest.TestCase):
    """Expired leases must be reset so crashed workers do not block the queue."""

    def test_reap_resets_expired_lease(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            cfg = _cfg(td, max_attempts=5)
            init_db(cfg)
            with closing(connect(cfg.db_path)) as conn:
                with transaction(conn):
                    enqueue(conn, "q", "x")
                with transaction(conn):
                    msg = claim(conn, "q", cfg)
                # Force the lease into the past; reaping must not depend on wall clock.
                conn.execute(
                    "UPDATE messages SET lease_expiry=0 WHERE id=?", (msg.id,)
                )
                with transaction(conn):
                    count = reap_expired(conn, cfg)
                state = conn.execute(
                    "SELECT state FROM messages WHERE id=?", (msg.id,)
                ).fetchone()["state"]
            self.assertEqual(count, 1)
            self.assertEqual(state, "pending")


if __name__ == "__main__":
    unittest.main()