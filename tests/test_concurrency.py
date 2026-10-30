# © 2026 Bryan Gil — github.com/Bryanhackz — br4yangil006@gmail.com
"""Concurrency test: N threads claiming simultaneously must not double-process."""

from __future__ import annotations

import tempfile
import threading
import unittest
from contextlib import closing
from pathlib import Path

from src.broker import claim, enqueue
from src.config import Config
from src.db import connect, init_db, transaction

THREADS = 10
MESSAGES = 5


def _cfg(td: str) -> Config:
    return Config(
        host="127.0.0.1", port=8080, env="dev",
        db_path=Path(td) / "c.db",
        visibility_timeout_sec=30, max_attempts=3,
        backoff_base_sec=1, backoff_max_sec=10, retention_days=7,
        rl_producer_per_min=10, rl_consumer_per_min=10, rl_login_per_min=10,
        lockout_fails=5, lockout_window_sec=900,
        scrypt_n=1024, scrypt_r=8, scrypt_p=1, log_level="INFO",
    )


class TestConcurrency(unittest.TestCase):
    """SQLite BEGIN IMMEDIATE is the only serializer; verify it holds."""

    def test_simultaneous_claims_no_double_processing(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            cfg = _cfg(td)
            init_db(cfg)
            with closing(connect(cfg.db_path)) as conn:
                with transaction(conn):
                    for i in range(MESSAGES):
                        enqueue(conn, "q", f"m{i}")
            claimed: list[int] = []
            lock = threading.Lock()
            barrier = threading.Barrier(THREADS, timeout=10)

            def worker() -> None:
                barrier.wait()
                with closing(connect(cfg.db_path)) as c:
                    with transaction(c):
                        msg = claim(c, "q", cfg)
                if msg is not None:
                    with lock:
                        claimed.append(msg.id)

            threads = [threading.Thread(target=worker) for _ in range(THREADS)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=15)
            self.assertEqual(len(claimed), MESSAGES, "exactly MESSAGES claimed")
            self.assertEqual(len(set(claimed)), MESSAGES, "no id claimed twice")


if __name__ == "__main__":
    unittest.main()