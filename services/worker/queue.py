"""Coarse persistent Postgres tasks with leases and lease_generation fencing.

Claim happens in its own short transaction. Network/model work runs outside any DB lock. Any state
write that depends on the task must run inside `fenced(conn, lease)`, which re-locks the task row and
proves this worker still holds the current, unexpired lease generation.
"""

from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb


class LeaseLost(Exception):
    """The lease expired or another worker reclaimed the task; abandon results and start no new effect."""


@dataclass(frozen=True)
class Lease:
    task_id: UUID
    organization_id: UUID
    campaign_id: UUID
    conversation_id: UUID | None
    kind: str
    payload: dict[str, Any]
    owner: str
    generation: int
    attempt: int
    max_attempts: int


_CLAIM_SQL = """
update tasks t
set status = 'leased',
    attempt = t.attempt + 1,
    lease_generation = t.lease_generation + 1,
    lease_owner = %(owner)s,
    lease_until = now() + make_interval(secs => %(lease_seconds)s)
from (
    select id
    from tasks
    where kind = any(%(kinds)s)
      and (%(org)s::uuid is null or organization_id = %(org)s::uuid)
      and attempt < max_attempts
      and ((status = 'ready' and run_after <= now())
           or (status = 'leased' and lease_until < now()))
    order by run_after, created_at, id
    for update skip locked
    limit 1
) next_task
where t.id = next_task.id
returning t.id, t.organization_id, t.campaign_id, t.conversation_id, t.kind, t.payload_json,
          t.lease_owner, t.lease_generation, t.attempt, t.max_attempts
"""

_FENCE_PREDICATE = """
id = %(task_id)s and organization_id = %(org)s and lease_owner = %(owner)s
and lease_generation = %(generation)s and status = 'leased' and lease_until > now()
"""


def _fence_params(lease: Lease) -> dict[str, Any]:
    return {"task_id": lease.task_id, "org": lease.organization_id, "owner": lease.owner, "generation": lease.generation}


def claim(
    conn: psycopg.Connection,
    *,
    owner: str,
    kinds: Iterable[str],
    lease_seconds: int,
    organization_id: UUID | None = None,
) -> Lease | None:
    """Claim one due task. `organization_id` restricts the claim to one tenant (isolated test tenants)."""
    kinds = list(kinds)
    if not kinds:
        return None
    with conn.transaction():
        row = conn.execute(
            _CLAIM_SQL, {"owner": owner, "kinds": kinds, "lease_seconds": lease_seconds, "org": organization_id}
        ).fetchone()
    if row is None:
        return None
    return Lease(
        task_id=row["id"],
        organization_id=row["organization_id"],
        campaign_id=row["campaign_id"],
        conversation_id=row["conversation_id"],
        kind=row["kind"],
        payload=row["payload_json"],
        owner=row["lease_owner"],
        generation=row["lease_generation"],
        attempt=row["attempt"],
        max_attempts=row["max_attempts"],
    )


def heartbeat(conn: psycopg.Connection, lease: Lease, lease_seconds: int) -> None:
    with conn.transaction():
        cur = conn.execute(
            f"update tasks set lease_until = now() + make_interval(secs => %(lease_seconds)s) where {_FENCE_PREDICATE}",
            {**_fence_params(lease), "lease_seconds": lease_seconds},
        )
    if cur.rowcount != 1:
        raise LeaseLost(f"task {lease.task_id} generation {lease.generation}")


@contextmanager
def fenced(conn: psycopg.Connection, lease: Lease) -> Iterator[psycopg.Connection]:
    """Transaction in which the task row is locked and the lease proven current. Raises LeaseLost otherwise."""
    with conn.transaction():
        row = conn.execute(f"select id from tasks where {_FENCE_PREDICATE} for update", _fence_params(lease)).fetchone()
        if row is None:
            raise LeaseLost(f"task {lease.task_id} generation {lease.generation}")
        yield conn


def complete(conn: psycopg.Connection, lease: Lease) -> None:
    """Mark succeeded. Must be called inside `fenced` so it commits atomically with the caller's state writes."""
    conn.execute(
        "update tasks set status = 'succeeded', lease_until = null, last_error_json = null "
        "where id = %(task_id)s and organization_id = %(org)s and lease_generation = %(generation)s",
        _fence_params(lease),
    )


def fail(conn: psycopg.Connection, lease: Lease, error: dict[str, Any], *, retry_after_seconds: int | None) -> str:
    """Record a failure inside `fenced`. Retries only while attempts remain and the caller says retry is safe."""
    retry = retry_after_seconds is not None and lease.attempt < lease.max_attempts
    status = "ready" if retry else "failed"
    conn.execute(
        """
        update tasks
        set status = %(status)s, lease_until = null, last_error_json = %(error)s,
            run_after = case when %(retry)s then now() + make_interval(secs => %(delay)s) else run_after end
        where id = %(task_id)s and organization_id = %(org)s and lease_generation = %(generation)s
        """,
        {**_fence_params(lease), "status": status, "error": Jsonb(error), "retry": retry, "delay": retry_after_seconds or 0},
    )
    return status


def sweep_exhausted(conn: psycopg.Connection) -> list[UUID]:
    """Expired leases with no attempts left become failed instead of silently sitting leased forever."""
    with conn.transaction():
        rows = conn.execute(
            """
            update tasks
            set status = 'failed', lease_until = null,
                last_error_json = jsonb_build_object('reason', 'lease_expired_attempts_exhausted', 'attempt', attempt)
            where status = 'leased' and lease_until < now() and attempt >= max_attempts
            returning id
            """
        ).fetchall()
    return [row["id"] for row in rows]
