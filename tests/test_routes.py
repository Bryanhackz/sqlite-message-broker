# © 2026 Bryan Gil — github.com/Bryanhackz — br4yangil006@gmail.com
"""Integration tests for src.app: routing, security headers, auth, rate limit."""

from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest import mock

from src.app import build_app
from src.auth import issue_key
from src.config import Config
from src.db import connect, init_db, transaction


def _cfg(td: str, **overrides) -> Config:
    base = dict(
        host="127.0.0.1", port=8080, env="dev",
        db_path=Path(td) / "routes.db",
        visibility_timeout_sec=30, max_attempts=3,
        backoff_base_sec=1, backoff_max_sec=10, retention_days=7,
        rl_producer_per_min=3, rl_consumer_per_min=10, rl_login_per_min=10,
        lockout_fails=5, lockout_window_sec=900,
        scrypt_n=1024, scrypt_r=8, scrypt_p=1, log_level="INFO",
    )
    base.update(overrides)
    return Config(**base)


def _call(app, method, path, headers=None, body=b""):
    """Invoke a WSGI app and collect status, headers, and body bytes."""
    env = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "wsgi.url_scheme": "http",
        "REMOTE_ADDR": "127.0.0.1",
        "wsgi.input": io.BytesIO(body),
        "CONTENT_LENGTH": str(len(body)),
    }
    for k, v in (headers or {}).items():
        env["HTTP_" + k.upper().replace("-", "_")] = v
    cap = {}
    def sr(status, hdrs):
        cap["status"] = status
        cap["headers"] = dict(hdrs)
    body_out = b"".join(app(env, sr))
    return cap["status"], cap["headers"], body_out


class TestRoutes(unittest.TestCase):
    """End-to-end behavior of the WSGI dispatcher."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.cfg = _cfg(self._tmp.name)
        init_db(self.cfg)
        self.app = build_app(self.cfg)
        with closing(connect(self.cfg.db_path)) as conn:
            with transaction(conn):
                self.producer_key = issue_key(conn, self.cfg, "prod1", "producer")
                self.consumer_key = issue_key(conn, self.cfg, "cons1", "consumer")
                self.admin_key = issue_key(conn, self.cfg, "admin1", "admin")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_health_200(self) -> None:
        status, headers, _ = _call(self.app, "GET", "/health")
        self.assertEqual(status, "200 OK")
        self.assertIn("Content-Security-Policy", headers)
        self.assertEqual(headers.get("Cache-Control"), "no-store")

    def test_404_has_security_headers(self) -> None:
        status, headers, _ = _call(self.app, "GET", "/none")
        self.assertEqual(status, "404 Not Found")
        self.assertIn("Content-Security-Policy", headers)

    def test_hsts_absent_in_dev(self) -> None:
        _, headers, _ = _call(self.app, "GET", "/health")
        self.assertNotIn("Strict-Transport-Security", headers)

    def test_producer_401_without_key(self) -> None:
        status, _, _ = _call(self.app, "POST", "/queues/q/messages",
                             body=b'{"body":"hi"}')
        self.assertEqual(status, "401 Unauthorized")

    def test_producer_201_with_key(self) -> None:
        status, _, _ = _call(self.app, "POST", "/queues/q/messages",
                             headers={"X-API-Key": self.producer_key},
                             body=b'{"body":"hi"}')
        self.assertEqual(status, "201 Created")

    def test_claim_204_when_empty(self) -> None:
        status, _, _ = _call(self.app, "POST", "/queues/empty/claim",
                             headers={"X-API-Key": self.consumer_key},
                             body=b"{}")
        self.assertEqual(status, "204 No Content")

    def test_admin_stats_401_without_key(self) -> None:
        status, _, _ = _call(self.app, "GET", "/admin/stats")
        self.assertEqual(status, "401 Unauthorized")

    def test_admin_stats_ok_with_admin_key(self) -> None:
        status, _, _ = _call(self.app, "GET", "/admin/stats",
                             headers={"X-API-Key": self.admin_key})
        self.assertEqual(status, "200 OK")

    def test_producer_rate_limit_429(self) -> None:
        body = b'{"body":"hi"}'
        headers = {"X-API-Key": self.producer_key}
        with mock.patch("src.ratelimit._now", return_value=1000):
            for _ in range(3):
                _call(self.app, "POST", "/queues/rl/messages",
                      headers=headers, body=body)
            status, _, _ = _call(self.app, "POST", "/queues/rl/messages",
                                 headers=headers, body=body)
        self.assertEqual(status, "429 Too Many Requests")


if __name__ == "__main__":
    unittest.main()