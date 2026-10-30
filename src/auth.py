# © 2026 Bryan Gil — github.com/Bryanhackz — br4yangil006@gmail.com
"""API-key auth: scrypt hashing, constant-time verify, issue, revoke."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
import time

from src.config import Config
from src.validators import validate_label, validate_role

SALT_BYTES = 16
KEY_BYTES = 32
KEY_LEN = 43  # secrets.token_urlsafe(32) always returns 43 chars
PREFIX_LEN = 8


def _now() -> int:
    """Current epoch seconds as int."""
    return int(time.time())


def _extract_prefix(key: str) -> str:
    """Return the constant-length prefix used as a fast lookup key."""
    return key[:PREFIX_LEN]


def hash_key(cfg: Config, key: str, salt: bytes) -> bytes:
    """Derive a scrypt hash for an API key using the given salt."""
    return hashlib.scrypt(
        key.encode("utf-8"),
        salt=salt,
        n=cfg.scrypt_n,
        r=cfg.scrypt_r,
        p=cfg.scrypt_p,
        dklen=KEY_BYTES,
    )


def issue_key(conn: sqlite3.Connection, cfg: Config, label: str, role: str) -> str:
    """Create a new API key, persist its hash, return plaintext once."""
    label = validate_label(label)
    role = validate_role(role)
    plaintext = secrets.token_urlsafe(KEY_BYTES)
    prefix = _extract_prefix(plaintext)
    salt = secrets.token_bytes(SALT_BYTES)
    digest = hash_key(cfg, plaintext, salt)
    conn.execute(
        "INSERT INTO api_keys(role, label, key_prefix, key_hash, key_salt, created_at)"
        " VALUES(?,?,?,?,?,?)",
        (role, label, prefix, digest, salt, _now()),
    )
    return plaintext


def revoke_key(conn: sqlite3.Connection, label: str) -> bool:
    """Revoke a live API key by label. Returns True if a row was updated."""
    cur = conn.execute(
        "UPDATE api_keys SET revoked_at=? WHERE label=? AND revoked_at IS NULL",
        (_now(), label),
    )
    return cur.rowcount == 1


def verify_key(conn: sqlite3.Connection, cfg: Config, key: str) -> str | None:
    """Return the role of a valid API key, else None. One scrypt per call max."""
    if not isinstance(key, str) or len(key) != KEY_LEN:
        return None
    prefix = _extract_prefix(key)
    row = conn.execute(
        "SELECT role, key_hash, key_salt FROM api_keys"
        " WHERE key_prefix=? AND revoked_at IS NULL",
        (prefix,),
    ).fetchone()
    if row is None:
        return None
    candidate = hash_key(cfg, key, bytes(row["key_salt"]))
    if hmac.compare_digest(candidate, bytes(row["key_hash"])):
        return str(row["role"])
    return None