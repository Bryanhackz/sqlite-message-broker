# © 2026 Bryan Gil — github.com/Bryanhackz — br4yangil006@gmail.com
"""WSGI server entry point. Boots a threaded wsgiref server."""

from __future__ import annotations

import logging
import sys
from socketserver import ThreadingMixIn
from wsgiref.simple_server import WSGIServer, make_server

from src.app import build_app
from src.config import load_config
from src.db import init_db


class ThreadingWSGIServer(ThreadingMixIn, WSGIServer):
    """Threaded WSGI server; each request runs in its own thread."""

    daemon_threads = True
    allow_reuse_address = True


def _configure_logging(level: str) -> None:
    """Configure the root logger with a standard format to stderr."""
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stderr,
    )


def main() -> int:
    """Initialize DB, build the WSGI app, and serve until interrupted."""
    cfg = load_config()
    _configure_logging(cfg.log_level)
    log = logging.getLogger("smb.run")
    init_db(cfg)
    app = build_app(cfg)
    with make_server(cfg.host, cfg.port, app, server_class=ThreadingWSGIServer) as srv:
        log.info("serving http://%s:%s env=%s db=%s", cfg.host, cfg.port, cfg.env, cfg.db_path)
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            log.info("shutdown requested")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())