"""Standalone durable AgroVision worker process.

Run alongside the API with AI_WORKER_MODE=external (recommended for production):

    cd apps/api
    uv run python -m app.worker            # poll forever
    uv run python -m app.worker --once     # drain queued jobs once and exit
    uv run python -m app.worker --healthcheck
"""

from __future__ import annotations

import argparse
import contextlib
import signal
import tempfile
import time
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.db.session import build_engine
from app.services.vision import recover_interrupted_jobs, run_pending_jobs_once

logger = get_logger("app.worker")
HEARTBEAT_FILE = Path(tempfile.gettempdir()) / "agrodrone_worker_heartbeat"


def _write_heartbeat() -> None:
    with contextlib.suppress(OSError):
        HEARTBEAT_FILE.write_text(str(time.time()), encoding="utf-8")


def _run_healthcheck() -> int:
    settings = get_settings()
    engine = build_engine(settings)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        if HEARTBEAT_FILE.exists():
            age = time.time() - float(HEARTBEAT_FILE.read_text(encoding="utf-8").strip())
            max_age = max(60.0, settings.ai_worker_poll_seconds * 10)
            if age > max_age:
                return 1
        return 0
    except Exception:  # noqa: BLE001
        return 1
    finally:
        engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(prog="agrovision-worker")
    parser.add_argument("--once", action="store_true", help="Process queued jobs once and exit.")
    parser.add_argument("--healthcheck", action="store_true", help="Verify DB & worker heartbeat.")
    args = parser.parse_args()

    if args.healthcheck:
        return _run_healthcheck()

    settings = get_settings()
    configure_logging(settings)
    engine = build_engine(settings)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

    recovered = recover_interrupted_jobs(factory, settings)
    logger.info(
        "worker_started",
        mode="once" if args.once else "poll",
        concurrency=settings.ai_worker_concurrency,
        ai_device=settings.ai_device,
        **recovered,
    )

    stopping = {"flag": False}

    def _stop(*_: object) -> None:
        stopping["flag"] = True

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    while not stopping["flag"]:
        _write_heartbeat()
        executed = run_pending_jobs_once(factory, settings)
        if args.once:
            logger.info("worker_drained", executed=executed)
            break
        if executed == 0:
            time.sleep(settings.ai_worker_poll_seconds)

    engine.dispose()
    logger.info("worker_stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
