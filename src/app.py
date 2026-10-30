# © 2026 Bryan Gil — github.com/Bryanhackz — br4yangil006@gmail.com
"""WSGI application: routing, security headers, JSON I/O, error model."""

from __future__ import annotations

import contextlib
import json
import logging
import mimetypes
import uuid
from pathlib import Path
from typing import Callable

from src.auth import issue_key, revoke_key, verify_key
from src.broker import ack, claim, enqueue, nack, reap_expired
from src.config import Config
from src.db import connect, transaction
from src.ratelimit import check_and_increment
from src.validators import (
    ValidationError,
    validate_body,
    validate_label,
    validate_queue_name,
    validate_role,
)

log = logging.getLogger("smb.app")

StartResponse = Callable[[str, list[tuple[str, str]]], None]
Environ = dict

# Resolve the project root to serve files from templates/ and static/
PROJECT_ROOT = Path(__file__).resolve().parent.parent

SECURITY_HEADERS = [
    ("Content-Security-Policy",
     "default-src 'self'; script-src 'self'; style-src 'self'; "
     "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; "
     "base-uri 'self'; form-action 'self'; object-src 'none'; "
     "upgrade-insecure-requests"),
    ("Cross-Origin-Opener-Policy", "same-origin"),
    ("Cross-Origin-Resource-Policy", "same-origin"),
    ("Permissions-Policy",
     "geolocation=(), camera=(), microphone=(), payment=(), usb=()"),
    ("X-Content-Type-Options", "nosniff"),
    ("X-Frame-Options", "DENY"),
    ("Referrer-Policy", "no-referrer"),
]


def _security_headers(cfg: Config, scheme: str) -> list[tuple[str, str]]:
    """Return the security header set; HSTS only in prod+https."""
    headers = list(SECURITY_HEADERS)
    if cfg.env == "prod" and scheme == "https":
        headers.append(("Strict-Transport-Security",
                        "max-age=31536000; includeSubDomains; preload"))
    return headers


def _json_response(start_response, cfg, environ, status, payload, extra=None):
    """Emit a JSON response with security headers and Cache-Control: no-store."""
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    headers = [
        ("Content-Type", "application/json; charset=utf-8"),
        ("Content-Length", str(len(body))),
        ("Cache-Control", "no-store"),
    ]
    headers += _security_headers(cfg, environ.get("wsgi.url_scheme", "http"))
    if extra:
        headers += extra
    start_response(status, headers)
    return [body]


def _error(start_response, cfg, environ, status, code, msg):
    """Uniform error envelope; never leaks stacktrace to client."""
    log_id = uuid.uuid4().hex[:12]
    log.warning("err id=%s code=%s status=%s msg=%s", log_id, code, status, msg)
    return _json_response(
        start_response, cfg, environ, status,
        {"code": code, "message": msg, "log_id": log_id},
    )


def _read_json(environ: Environ) -> dict:
    """Parse a bounded JSON object from the WSGI input stream."""
    try:
        length = int(environ.get("CONTENT_LENGTH") or 0)
    except ValueError:
        raise ValidationError("invalid Content-Length") from None
    if length <= 0:
        raise ValidationError("empty body")
    if length > 128 * 1024:
        raise ValidationError("body too large")
    raw = environ["wsgi.input"].read(length)
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ValidationError("invalid JSON") from None
    if not isinstance(data, dict):
        raise ValidationError("payload must be object")
    return data


def _auth_role(conn, cfg: Config, environ: Environ) -> str | None:
    """Resolve the caller role from X-API-Key, or None."""
    key = environ.get("HTTP_X_API_KEY")
    if not key:
        return None
    return verify_key(conn, cfg, key)


def build_app(cfg: Config):
    """Return a WSGI callable wired with routes and security headers."""

    def app(environ, start_response):
        try:
            return _dispatch(environ, start_response)
        except Exception:
            log.exception("unhandled")
            return _error(start_response, cfg, environ, "500 Internal Server Error",
                          "internal", "internal error")

    def _dispatch(environ, start_response):
        method = environ.get("REQUEST_METHOD", "GET")
        path = environ.get("PATH_INFO", "/")

        # Serve static frontend files securely
        if path.startswith("/static/") or path.startswith("/templates/"):
            return _serve_static(path, start_response, cfg, environ)

        if path == "/health" and method == "GET":
            return _json_response(start_response, cfg, environ, "200 OK", {"status": "ok"})
        if path.startswith("/queues/") and path.endswith("/messages") and method == "POST":
            return _producer(environ, start_response, path)
        if path.startswith("/queues/") and path.endswith("/claim") and method == "POST":
            return _consumer_claim(environ, start_response, path)
        if path.startswith("/messages/") and path.endswith("/ack") and method == "POST":
            return _consumer_ack(environ, start_response, path, "ack")
        if path.startswith("/messages/") and path.endswith("/nack") and method == "POST":
            return _consumer_ack(environ, start_response, path, "nack")
        if path == "/admin/stats" and method == "GET":
            return _admin_stats(environ, start_response)
        if path == "/admin/keys" and method == "POST":
            return _admin_issue_key(environ, start_response)
        if path.startswith("/admin/keys/") and path.endswith("/revoke") and method == "POST":
            return _admin_revoke_key(environ, start_response, path)
        return _error(start_response, cfg, environ, "404 Not Found", "not_found", "not found")

    def _serve_static(path, start_response, cfg, environ):
        """Serve static files from static/ or templates/ with path traversal protection."""
        # Strip leading slash
        rel_path = path.lstrip("/")
        target_file = (PROJECT_ROOT / rel_path).resolve()

        # Ensure the resolved path is still within the allowed directories
        if not str(target_file).startswith(str(PROJECT_ROOT / "static")) and \
           not str(target_file).startswith(str(PROJECT_ROOT / "templates")):
            return _error(start_response, cfg, environ, "403 Forbidden", "forbidden", "forbidden")

        if not target_file.is_file():
            return _error(start_response, cfg, environ, "404 Not Found", "not_found", "file not found")

        mime_type, _ = mimetypes.guess_type(str(target_file))
        if not mime_type:
            mime_type = "application/octet-stream"

        body = target_file.read_bytes()
        headers = [
            ("Content-Type", mime_type),
            ("Content-Length", str(len(body))),
        ]
        headers += _security_headers(cfg, environ.get("wsgi.url_scheme", "http"))
        start_response("200 OK", headers)
        return [body]

    def _extract_queue(path):
        parts = path.strip("/").split("/")
        if len(parts) < 3 or parts[0] != "queues":
            raise ValidationError("bad path")
        return validate_queue_name(parts[1])

    def _producer(environ, start_response, path):
        try:
            queue = _extract_queue(path)
            payload = _read_json(environ)
            body = validate_body(payload.get("body", ""))
        except ValidationError as e:
            return _error(start_response, cfg, environ, "400 Bad Request", "invalid", str(e))
        ip = environ.get("REMOTE_ADDR", "unknown")
        with contextlib.closing(connect(cfg.db_path)) as conn:
            role = _auth_role(conn, cfg, environ)
            if role not in ("producer", "admin"):
                return _error(start_response, cfg, environ, "401 Unauthorized",
                              "unauthorized", "invalid api key")
            with transaction(conn):
                if not check_and_increment(conn, "producer", ip, cfg.rl_producer_per_min):
                    return _error(start_response, cfg, environ, "429 Too Many Requests",
                                  "rate_limited", "too many requests")
                msg_id = enqueue(conn, queue, body)
        return _json_response(start_response, cfg, environ, "201 Created",
                              {"id": msg_id, "queue": queue})

    def _consumer_claim(environ, start_response, path):
        try:
            queue = _extract_queue(path)
        except ValidationError as e:
            return _error(start_response, cfg, environ, "400 Bad Request", "invalid", str(e))
        ip = environ.get("REMOTE_ADDR", "unknown")
        with contextlib.closing(connect(cfg.db_path)) as conn:
            role = _auth_role(conn, cfg, environ)
            if role not in ("consumer", "admin"):
                return _error(start_response, cfg, environ, "401 Unauthorized",
                              "unauthorized", "invalid api key")
            with transaction(conn):
                if not check_and_increment(conn, "consumer", ip, cfg.rl_consumer_per_min):
                    return _error(start_response, cfg, environ, "429 Too Many Requests",
                                  "rate_limited", "too many requests")
                reap_expired(conn, cfg)
                msg = claim(conn, queue, cfg)
        if msg is None:
            return _json_response(start_response, cfg, environ, "204 No Content", {})
        return _json_response(start_response, cfg, environ, "200 OK", {
            "id": msg.id, "queue": msg.queue, "body": msg.body,
            "attempts": msg.attempts, "lease_token": msg.lease_token,
            "lease_expiry": msg.lease_expiry,
        })

    def _consumer_ack(environ, start_response, path, kind):
        parts = path.strip("/").split("/")
        if len(parts) < 3 or parts[0] != "messages":
            return _error(start_response, cfg, environ, "404 Not Found", "not_found", "not found")
        try:
            msg_id = int(parts[1])
        except ValueError:
            return _error(start_response, cfg, environ, "400 Bad Request", "invalid", "bad id")
        try:
            payload = _read_json(environ)
        except ValidationError as e:
            return _error(start_response, cfg, environ, "400 Bad Request", "invalid", str(e))
        token = payload.get("lease_token", "")
        if not isinstance(token, str) or not token:
            return _error(start_response, cfg, environ, "400 Bad Request",
                          "invalid", "lease_token required")
        with contextlib.closing(connect(cfg.db_path)) as conn:
            role = _auth_role(conn, cfg, environ)
            if role not in ("consumer", "admin"):
                return _error(start_response, cfg, environ, "401 Unauthorized",
                              "unauthorized", "invalid api key")
            with transaction(conn):
                if kind == "ack":
                    ok = ack(conn, msg_id, token)
                    return _json_response(start_response, cfg, environ,
                                          "200 OK" if ok else "409 Conflict", {"ok": ok})
                result = nack(conn, msg_id, token, cfg)
                return _json_response(start_response, cfg, environ, "200 OK",
                                      {"result": result})

    def _admin_stats(environ, start_response):
        with contextlib.closing(connect(cfg.db_path)) as conn:
            if _auth_role(conn, cfg, environ) != "admin":
                return _error(start_response, cfg, environ, "401 Unauthorized",
                              "unauthorized", "invalid api key")
            rows = conn.execute(
                "SELECT q.name, m.state, COUNT(*) AS n FROM messages m"
                " JOIN queues q ON q.id = m.queue_id GROUP BY q.name, m.state"
            ).fetchall()
        stats: dict[str, dict[str, int]] = {}
        for r in rows:
            stats.setdefault(r["name"], {})[r["state"]] = int(r["n"])
        return _json_response(start_response, cfg, environ, "200 OK", {"queues": stats})

    def _admin_issue_key(environ, start_response):
        try:
            payload = _read_json(environ)
            label = validate_label(payload.get("label", ""))
            role = validate_role(payload.get("role", ""))
        except ValidationError as e:
            return _error(start_response, cfg, environ, "400 Bad Request", "invalid", str(e))
        with contextlib.closing(connect(cfg.db_path)) as conn:
            if _auth_role(conn, cfg, environ) != "admin":
                return _error(start_response, cfg, environ, "401 Unauthorized",
                              "unauthorized", "invalid api key")
            try:
                with transaction(conn):
                    key = issue_key(conn, cfg, label, role)
            except ValidationError as e:
                return _error(start_response, cfg, environ, "400 Bad Request", "invalid", str(e))
        return _json_response(start_response, cfg, environ, "201 Created",
                              {"key": key, "label": label, "role": role})

    def _admin_revoke_key(environ, start_response, path):
        parts = path.strip("/").split("/")
        if len(parts) < 4:
            return _error(start_response, cfg, environ, "404 Not Found", "not_found", "not found")
        label = parts[2]
        with contextlib.closing(connect(cfg.db_path)) as conn:
            if _auth_role(conn, cfg, environ) != "admin":
                return _error(start_response, cfg, environ, "401 Unauthorized",
                              "unauthorized", "invalid api key")
            with transaction(conn):
                ok = revoke_key(conn, label)
        return _json_response(start_response, cfg, environ, "200 OK", {"revoked": ok})

    return app