# © 2026 Bryan Gil — github.com/Bryanhackz — br4yangil006@gmail.com
"""Tests for src.ratelimit: allow under limit, block at limit, window isolation."""

from __future__ import annotations

import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest import mock

from src.config import Config
from src.db import connect, init_db, transaction
from src.ratelimit import check_and_increment


def _cfg(td: str) -> Config:
    return Config(
        host="127.0.0.1", port=8080, env="dev",
        db_path=Path(td) / "r.db",
        visibility_timeout_sec=30, max_attempts=3,
        backoff_base_sec=1, backoff_max_sec=10, retention_days=7,
        rl_producer_per_min=3, rl_consumer_per_min=10, rl_login_per_min=10,
        lockout_fails=5, lockout_window_sec=900,
        scrypt_n=1024, scrypt_r=8, scrypt_p=1, log_level="INFO",
    )


class TestRateLimit(unittest.TestCase):
    """Fixed-window counter; time frozen for determinism."""

    def test_under_limit(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            cfg = _cfg(td)
            init_db(cfg)
            with closing(connect(cfg.db_path)) as conn, mock.patch(
                "src.ratelimit._now", return_value=1000
            ):
                allowed = []
                for _ in range(3):
                    with transaction(conn):
                        allowed.append(check_and_increment(conn, "p", "1.1.1.1", 3))
            self.assertEqual(allowed, [True, True, True])

    def test_blocked_at_limit(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            cfg = _cfg(td)
            init_db(cfg)
            with closing(connect(cfg.db_path)) as conn, mock.patch(
                "src.ratelimit._now", return_value=1000
            ):
                results = []
                for _ in range(4):
                    with transaction(conn):
                        results.append(check_and_increment(conn, "p", "ip", 3))
            self.assertEqual(results, [True, True, True, False])

    def test_window_rollover_resets(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            cfg = _cfg(td)
            init_db(cfg)
            with closing(connect(cfg.db_path)) as conn:
                with mock.patch("src.ratelimit._now", return_value=1000):
                    for _ in range(3):
                        with transaction(conn):
                            check_and_increment(conn, "p", "ip", 3)
                with mock.patch("src.ratelimit._now", return_value=1060):
                    with transaction(conn):
                        ok = check_and_increment(conn, "p", "ip", 3)
            self.assertTrue(ok, "new window should allow again")


if __name__ == "__main__":
    unittest.main()