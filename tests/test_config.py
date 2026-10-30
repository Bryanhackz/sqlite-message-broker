# © 2026 Bryan Gil — github.com/Bryanhackz — br4yangil006@gmail.com
"""Unit tests for src.config: defaults, overrides, and validation."""

from __future__ import annotations

import os
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest import mock

from src.config import Config, load_config


class TestConfigDefaults(unittest.TestCase):
    """Defaults are applied when no environment variables are set."""

    def test_defaults(self) -> None:
        """With a clean env, config uses the documented defaults."""
        with mock.patch.dict(os.environ, {}, clear=True):
            cfg = load_config()
        self.assertEqual(cfg.host, "127.0.0.1", "default host")
        self.assertEqual(cfg.port, 8080, "default port")
        self.assertEqual(cfg.env, "dev", "default env")
        self.assertEqual(cfg.max_attempts, 5, "default max_attempts")
        self.assertEqual(cfg.scrypt_n, 16384, "default scrypt_n")

    def test_env_overrides(self) -> None:
        """Environment variables override the defaults."""
        overrides = {
            "SMB_PORT": "9090",
            "SMB_ENV": "prod",
            "SMB_MAX_ATTEMPTS": "10",
        }
        with mock.patch.dict(os.environ, overrides, clear=True):
            cfg = load_config()
        self.assertEqual(cfg.port, 9090, "port override")
        self.assertEqual(cfg.env, "prod", "env override")
        self.assertEqual(cfg.max_attempts, 10, "max_attempts override")


class TestConfigValidation(unittest.TestCase):
    """load_config rejects invalid values."""

    def test_invalid_int_raises(self) -> None:
        """A malformed integer raises ValueError."""
        with mock.patch.dict(os.environ, {"SMB_PORT": "not-a-number"}, clear=True):
            with self.assertRaises(ValueError):
                load_config()

    def test_negative_int_raises(self) -> None:
        """A value below the minimum raises ValueError."""
        with mock.patch.dict(os.environ, {"SMB_MAX_ATTEMPTS": "0"}, clear=True):
            with self.assertRaises(ValueError):
                load_config()

    def test_config_frozen(self) -> None:
        """Config is immutable (frozen dataclass)."""
        cfg = Config(
            host="h",
            port=1,
            env="e",
            db_path=Path("/tmp/x.db"),
            visibility_timeout_sec=1,
            max_attempts=1,
            backoff_base_sec=1,
            backoff_max_sec=1,
            retention_days=1,
            rl_producer_per_min=1,
            rl_consumer_per_min=1,
            rl_login_per_min=1,
            lockout_fails=1,
            lockout_window_sec=1,
            scrypt_n=16384,
            scrypt_r=8,
            scrypt_p=1,
            log_level="INFO",
        )
        with self.assertRaises(FrozenInstanceError):
            cfg.host = "other"  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()