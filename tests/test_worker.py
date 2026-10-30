# © 2026 Bryan Gil — github.com/Bryanhackz — br4yangil006@gmail.com
"""Tests for src.worker: dry-run, empty queue, ack path, nack path, CLI exit code."""

from __future__ import annotations

import io
import os
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest import mock

from src.broker import enqueue
from src.config import load_config
from src.db import connect, init_db, transaction
from src.worker import main, run_once


def _with_env(td: str):
    """Context manager that points SMB_DB_PATH at a fresh temp DB."""
    path = str(Path(td) / "w.db")
    return mock.patch.dict(os.environ, {"SMB_DB_PATH": path}, clear=False)


class TestRunOnce(unittest.TestCase):
    """Behavior of a single claim→process→ack iteration."""

    def test_empty_queue(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td, _with_env(td):
            cfg = load_config()
            init_db(cfg)
            self.assertEqual(run_once("empty"), "empty")

    def test_dry_run_does_not_ack(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td, _with_env(td):
            cfg = load_config()
            init_db(cfg)
            with closing(connect(cfg.db_path)) as conn:
                with transaction(conn):
                    enqueue(conn, "q", "x")
            self.assertEqual(run_once("q", dry_run=True), "dry_run")

    def test_acked_path(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td, _with_env(td):
            cfg = load_config()
            init_db(cfg)
            with closing(connect(cfg.db_path)) as conn:
                with transaction(conn):
                    enqueue(conn, "q", "x")
            with mock.patch("src.worker.process", return_value=True):
                self.assertEqual(run_once("q"), "acked")

    def test_retry_path(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td, _with_env(td):
            cfg = load_config()
            init_db(cfg)
            with closing(connect(cfg.db_path)) as conn:
                with transaction(conn):
                    enqueue(conn, "q", "x")
            with mock.patch("src.worker.process", return_value=False):
                self.assertEqual(run_once("q"), "retry")


class TestMain(unittest.TestCase):
    """CLI exit code must be 0 on the --once path."""

    def test_main_once_returns_0(self) -> None:
        with mock.patch("src.worker.run_once", return_value="acked"), \
             mock.patch("sys.stdout", new=io.StringIO()):
            rc = main(["--queue", "q", "--once"])
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()