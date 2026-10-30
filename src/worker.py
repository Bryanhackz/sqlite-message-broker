# © 2026 Bryan Gil — github.com/Bryanhackz — br4yangil006@gmail.com
"""Worker CLI: claim → process → ack loop against the broker."""

from __future__ import annotations

import argparse
import logging
import sys
import time

from src.broker import ack, claim, nack, reap_expired
from src.config import load_config
from src.db import connect, transaction

log = logging.getLogger("smb.worker")


def process(body: str) -> bool:
    """Default processor: log and return True. Replace in your worker subclass."""
    log.info("processing body=%r", body[:120])
    return True


def run_once(queue: str, dry_run: bool = False) -> str:
    """Claim one message, process, ack/nack. Return a result label."""
    cfg = load_config()
    with connect(cfg.db_path) as conn:
        with transaction(conn):
            reap_expired(conn, cfg)
            msg = claim(conn, queue, cfg)
        if msg is None:
            return "empty"
        if dry_run:
            return "dry_run"
        try:
            ok = process(msg.body)
        except Exception:
            log.exception("process failed for msg=%s", msg.id)
            ok = False
        with transaction(conn):
            if ok:
                ack(conn, msg.id, msg.lease_token)
                return "acked"
            return nack(conn, msg.id, msg.lease_token, cfg)


def main(argv: list[str] | None = None) -> int:
    """CLI entry: --queue, --once, --dry-run, --interval."""
    parser = argparse.ArgumentParser(description="sqlite-message-broker worker")
    parser.add_argument("--queue", required=True)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--interval", type=int, default=2)
    args = parser.parse_args(argv)
    cfg = load_config()
    logging.basicConfig(
        level=getattr(logging, cfg.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stderr,
    )
    if args.once:
        print(run_once(args.queue, args.dry_run))
        return 0
    while True:
        try:
            res = run_once(args.queue, args.dry_run)
            if res != "empty":
                print(res, flush=True)
        except KeyboardInterrupt:
            return 0
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())