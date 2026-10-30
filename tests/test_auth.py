# © 2026 Bryan Gil — github.com/Bryanhackz — br4yangil006@gmail.com
"""Tests for src.auth: issue/verify/revoke, deterministic scrypt, wrong-key rejection."""

from __future__ import annotations

import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from src.auth import hash_key, issue_key, revoke_key, verify_key
from src.config import Config
from src.db import connect, init_db, transaction


def _cfg(td: str) -> Config:
    return Config(
        host="127.0.0.1", port=8080, env="dev",
        db_path=Path(td) / "a.db",
        visibility_timeout_sec=30, max_attempts=3,
        backoff_base_sec=1, backoff_max_sec=10, retention_days=7,
        rl_producer_per_min=10, rl_consumer_per_min=10, rl_login_per_min=10,
        lockout_fails=5, lockout_window_sec=900,
        scrypt_n=1024, scrypt_r=8, scrypt_p=1, log_level="INFO",
    )


class TestScrypt(unittest.TestCase):
    """hash_key is deterministic per (key, salt) pair."""

    def test_deterministic(self) -> None:
        cfg = _cfg("/tmp")
        salt = b"0123456789abcdef"
        a = hash_key(cfg, "secret", salt)
        b = hash_key(cfg, "secret", salt)
        self.assertEqual(a, b)

    def test_different_salt_different_hash(self) -> None:
        cfg = _cfg("/tmp")
        a = hash_key(cfg, "secret", b"0123456789abcdef")
        b = hash_key(cfg, "secret", b"fedcba9876543210")
        self.assertNotEqual(a, b)


class TestIssueVerify(unittest.TestCase):
    """Issued keys verify; revoked keys and unknown keys do not."""

    def test_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            cfg = _cfg(td)
            init_db(cfg)
            with closing(connect(cfg.db_path)) as conn:
                with transaction(conn):
                    key = issue_key(conn, cfg, "p1", "producer")
                role = verify_key(conn, cfg, key)
            self.assertEqual(role, "producer")

    def test_unknown_key_returns_none(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            cfg = _cfg(td)
            init_db(cfg)
            with closing(connect(cfg.db_path)) as conn:
                role = verify_key(conn, cfg, "nope-nope-nope")
            self.assertIsNone(role)

    def test_revoked_key_returns_none(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            cfg = _cfg(td)
            init_db(cfg)
            with closing(connect(cfg.db_path)) as conn:
                with transaction(conn):
                    key = issue_key(conn, cfg, "p2", "producer")
                with transaction(conn):
                    ok = revoke_key(conn, "p2")
                role = verify_key(conn, cfg, key)
            self.assertTrue(ok)
            self.assertIsNone(role)


if __name__ == "__main__":
    unittest.main()