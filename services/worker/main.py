"""Single persistent worker: heartbeat, lease sweeps, action expiry, and claims for registered task kinds.

Run: python -m services.worker.main   (requires DATABASE_URL, RUNTIME_ORGANIZATION_ID, WORKER_ID)
Refuses to start while another worker's heartbeat is fresh; P0 allows exactly one live worker.
"""

import logging
import signal
import socket
import time
from collections.abc import Callable
from functools import partial

import psycopg
from psycopg.types.json import Jsonb

from services.core import db
from services.core.config import Settings, get_settings

from services.adapters.crustdata.adapter import CrustdataResearch
from services.adapters.crustdata.client import CrustdataClient
from services.models.client import AzureModelClient

from . import actions, queue
from .handlers import handle_normalize_mission
from .qualify import handle_qualify_and_draft
from .research import handle_research

log = logging.getLogger("outcome.worker")

Handler = Callable[[psycopg.Connection, queue.Lease], None]

class AnotherWorkerActive(RuntimeError):
    pass


def build_handlers(settings: Settings) -> dict[str, Handler]:
    """Task kind -> handler. A kind is only claimed when its dependencies are configured, so unconfigured
    providers leave tasks ready instead of failing them."""
    handlers: dict[str, Handler] = {}
    if settings.azure_configured:
        client = AzureModelClient(settings)
        log.info("model client: %s", client.api_path)
        handlers["normalize_mission"] = partial(handle_normalize_mission, client=client)
        handlers["qualify_and_draft"] = partial(handle_qualify_and_draft, client=client)
    else:
        log.warning("Azure OpenAI not configured; normalize_mission tasks will stay ready")
    if settings.crustdata_api_key:

        def research_factory() -> CrustdataResearch:
            return CrustdataResearch(
                CrustdataClient(
                    api_key=settings.crustdata_api_key,
                    base_url=settings.crustdata_base_url,
                    timeout=float(settings.provider_timeout_seconds),
                )
            )

        handlers["research"] = partial(handle_research, research_factory=research_factory)
    else:
        log.warning("CRUSTDATA_API_KEY not configured; research tasks will stay ready")
    return handlers


def write_heartbeat(conn: psycopg.Connection, settings: Settings, worker_id: str) -> None:
    """Claim or refresh the single-worker heartbeat; fail if a different worker is still fresh."""
    with conn.transaction():
        cur = conn.execute(
            """
            update organizations
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

    handlers = build_handlers(settings)
    log.info("worker %s claiming task kinds: %s", worker_id, sorted(handlers) or "none")

    last_heartbeat = 0.0
    try:
        with db.connection(timeout=10) as conn:
            while not stopping:
                if time.monotonic() - last_heartbeat >= settings.worker_heartbeat_seconds:
                    write_heartbeat(conn, settings, worker_id)
                    last_heartbeat = time.monotonic()
                if not run_once(conn, settings, worker_id, handlers):
                    time.sleep(1.0)
    finally:
        db.reset_pool()
    log.info("worker %s stopped", worker_id)


if __name__ == "__main__":
    main()
