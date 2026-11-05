"""Single persistent worker: heartbeat, lease sweeps, action expiry, and claims for registered task kinds.

Run: python -m services.worker.main   (requires DATABASE_URL, RUNTIME_ORGANIZATION_ID, WORKER_ID)
Refuses to start while another worker's heartbeat is fresh; P0 allows exactly one live worker.
"""

import logging
import signal
import socket
import time
from collections.abc import Callable

import psycopg
from psycopg.types.json import Jsonb

from services.core import db
from services.core.config import Settings, get_settings

from . import actions, queue

log = logging.getLogger("outcome.worker")

Handler = Callable[[psycopg.Connection, queue.Lease], None]

# Task kind -> handler. Handlers own their fenced state transition and queue.complete/fail.
# B2 registers none, so normalize_mission tasks stay ready until B3 instead of being consumed by a no-op.
HANDLERS: dict[str, Handler] = {}


class AnotherWorkerActive(RuntimeError):
    pass


def write_heartbeat(conn: psycopg.Connection, settings: Settings, worker_id: str) -> None:
    """Claim or refresh the single-worker heartbeat; fail if a different worker is still fresh."""
    with conn.transaction():
        cur = conn.execute(
            """
            update public.organizations
            set runtime_json = jsonb_set(runtime_json, '{worker}', %(worker)s::jsonb || jsonb_build_object('last_seen_at', now()))
            where id = %(org)s
              and (runtime_json -> 'worker' is null
                   or runtime_json -> 'worker' ->> 'worker_id' = %(worker_id)s
                   or (runtime_json -> 'worker' ->> 'last_seen_at')::timestamptz < now() - make_interval(secs => %(stale)s))
            """,
            {
                "org": settings.runtime_organization_id,
                "worker": Jsonb({"worker_id": worker_id, "release_sha": settings.release_sha}),
                "worker_id": worker_id,
                "stale": settings.worker_stale_seconds,
            },
        )
    if cur.rowcount != 1:
        raise AnotherWorkerActive("another worker heartbeat is fresh, or RUNTIME_ORGANIZATION_ID does not exist")


def run_once(conn: psycopg.Connection, settings: Settings, worker_id: str, handlers: dict[str, Handler]) -> bool:
    queue.sweep_exhausted(conn)
    actions.expire_executing(conn, timeout_seconds=settings.action_executing_timeout_seconds)
    lease = queue.claim(conn, owner=worker_id, kinds=handlers, lease_seconds=settings.task_lease_seconds)
    if lease is None:
        return False
    try:
        handlers[lease.kind](conn, lease)
    except queue.LeaseLost:
        log.warning("lease lost task=%s generation=%s; result abandoned", lease.task_id, lease.generation)
    except Exception as exc:  # noqa: BLE001 - a handler failure must be recorded, not crash the worker
        log.exception("handler failed task=%s kind=%s", lease.task_id, lease.kind)
        try:
            with queue.fenced(conn, lease):
                queue.fail(conn, lease, {"error_class": type(exc).__name__}, retry_after_seconds=None)
        except queue.LeaseLost:
            pass
    return True


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = get_settings()
    if settings.runtime_organization_id is None:
        raise SystemExit("RUNTIME_ORGANIZATION_ID is required for the worker heartbeat")
    worker_id = settings.worker_id or f"{socket.gethostname()}-{time.time_ns()}"
    stopping = False

    def stop(*_: object) -> None:
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    last_heartbeat = 0.0
    try:
        with db.connection(timeout=10) as conn:
            while not stopping:
                if time.monotonic() - last_heartbeat >= settings.worker_heartbeat_seconds:
                    write_heartbeat(conn, settings, worker_id)
                    last_heartbeat = time.monotonic()
                if not run_once(conn, settings, worker_id, HANDLERS):
                    time.sleep(1.0)
    finally:
        db.reset_pool()
    log.info("worker %s stopped", worker_id)


if __name__ == "__main__":
    main()
