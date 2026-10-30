# © 2026 Bryan Gil — github.com/Bryanhackz — br4yangil006@gmail.com
"""Central configuration for the broker. Reads environment variables with safe defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _int_env(name: str, default: int, minimum: int = 0) -> int:
    """Read an integer environment variable and enforce a lower bound.

    Parsing is strict on purpose: a misconfigured env var must fail fast at
    boot, not surface as a runtime error deep inside a request handler.
    """
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(f"{name} must be an integer, got: {raw!r}") from None
    if value < minimum:
        raise ValueError(f"{name} must be >= {minimum}, got: {value}")
    return value


def _str_env(name: str, default: str) -> str:
    """Read a string environment variable or fall back to the default."""
    raw = os.environ.get(name)
    return raw if raw not in (None, "") else default


def _path_env(name: str, default: str) -> Path:
    """Read an environment variable that represents a filesystem path."""
    return Path(_str_env(name, default))


@dataclass(frozen=True)
class Config:
    """Immutable broker configuration, built from os.environ.

    Frozen because every consumer passes Config by reference across threads;
    a mutation mid-run would silently change invariants (timeouts, scrypt
    parameters) without re-validation.
    """

    host: str
    port: int
    env: str
    db_path: Path
    visibility_timeout_sec: int
    max_attempts: int
    backoff_base_sec: int
    backoff_max_sec: int
    retention_days: int
    rl_producer_per_min: int
    rl_consumer_per_min: int
    rl_login_per_min: int
    lockout_fails: int
    lockout_window_sec: int
    scrypt_n: int
    scrypt_r: int
    scrypt_p: int
    log_level: str


def load_config() -> Config:
    """Build Config by reading os.environ with safe defaults."""
    return Config(
        host=_str_env("SMB_HOST", "127.0.0.1"),
        port=_int_env("SMB_PORT", 8080, minimum=1),
        env=_str_env("SMB_ENV", "dev"),
        db_path=_path_env("SMB_DB_PATH", "./data/broker.db"),
        visibility_timeout_sec=_int_env("SMB_VISIBILITY_TIMEOUT_SEC", 30, minimum=1),
        max_attempts=_int_env("SMB_MAX_ATTEMPTS", 5, minimum=1),
        backoff_base_sec=_int_env("SMB_BACKOFF_BASE_SEC", 5, minimum=1),
        backoff_max_sec=_int_env("SMB_BACKOFF_MAX_SEC", 300, minimum=1),
        retention_days=_int_env("SMB_RETENTION_DAYS", 7, minimum=1),
        rl_producer_per_min=_int_env("SMB_RATE_LIMIT_PRODUCER_PER_MIN", 120, minimum=1),
        rl_consumer_per_min=_int_env("SMB_RATE_LIMIT_CONSUMER_PER_MIN", 240, minimum=1),
        rl_login_per_min=_int_env("SMB_RATE_LIMIT_LOGIN_PER_MIN", 10, minimum=1),
        lockout_fails=_int_env("SMB_LOCKOUT_FAILS", 5, minimum=1),
        lockout_window_sec=_int_env("SMB_LOCKOUT_WINDOW_SEC", 900, minimum=1),
        scrypt_n=_int_env("SMB_SCRYPT_N", 16384, minimum=1024),
        scrypt_r=_int_env("SMB_SCRYPT_R", 8, minimum=1),
        scrypt_p=_int_env("SMB_SCRYPT_P", 1, minimum=1),
        log_level=_str_env("SMB_LOG_LEVEL", "INFO").upper(),
    )