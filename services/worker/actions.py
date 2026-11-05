"""Durable action outbox: intent is committed before any provider call; prepared->executing is gated by
the current lease, campaign status and suppressions; executing that outlives its timeout becomes unknown
and is reconciled, never blindly re-executed."""

from typing import Any
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from services.core.contracts.base import normalize_email

from .queue import Lease, fenced

EXECUTABLE_CAMPAIGN_STATUSES = ("running", "waiting_reply")

_ALLOWED_RESULTS = {
    "executing": {"succeeded", "failed", "unknown"},
    "unknown": {"succeeded"},
}


class ActionConflict(Exception):
    """Same idempotency key with a different request hash."""


class ActionNotExecutable(Exception):
    pass


def prepare(
    conn: psycopg.Connection,
    *,
    organization_id: UUID,
    campaign_id: UUID,
    conversation_id: UUID | None,
    decision_id: UUID,
    kind: str,
    idempotency_key: str,
    request_hash: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    row = conn.execute(
        """
        insert into actions
          (organization_id, campaign_id, conversation_id, decision_id, kind, idempotency_key, request_hash,
           state, payload_json)
        values (%s, %s, %s, %s, %s, %s, %s, 'prepared', %s)
        on conflict (organization_id, idempotency_key) do nothing
        returning *
        """,
        (organization_id, campaign_id, conversation_id, decision_id, kind, idempotency_key, request_hash, Jsonb(payload)),
    ).fetchone()
    if row is not None:
        return row
    existing = conn.execute(
        "select * from actions where organization_id = %s and idempotency_key = %s",
        (organization_id, idempotency_key),
    ).fetchone()
    if existing["request_hash"] != request_hash:
        raise ActionConflict(idempotency_key)
    return existing


def _suppression_identities(payload: dict[str, Any]) -> list[tuple[str, str]]:
    identities = [(item["kind"], item["value"]) for item in payload.get("suppression_identities", [])]
    for field in ("to_email",):
        if payload.get(field):
            identities.append(("email", normalize_email(payload[field])))
    for email in payload.get("attendees", []):
        identities.append(("email", normalize_email(email)))
    return identities


def begin_execute(conn: psycopg.Connection, lease: Lease, action_id: UUID) -> dict[str, Any]:
    """Atomically move prepared->executing while the lease is current. Commit this before the provider call."""
    with fenced(conn, lease):
        action = conn.execute(
            "select * from actions where organization_id = %s and id = %s for update",
            (lease.organization_id, action_id),
        ).fetchone()
        if action is None:
            raise ActionNotExecutable("action not found for this tenant")
        if action["state"] != "prepared":
            raise ActionNotExecutable(f"action state is {action['state']}")
        campaign = conn.execute(
            "select status from campaigns where organization_id = %s and id = %s for share",
            (lease.organization_id, action["campaign_id"]),
        ).fetchone()
        if campaign["status"] not in EXECUTABLE_CAMPAIGN_STATUSES:
            raise ActionNotExecutable(f"campaign status is {campaign['status']}")
        identities = _suppression_identities(action["payload_json"])
        if identities:
            hit = conn.execute(
                """
                select 1 from suppressions
                where organization_id = %s
                  and (identity_kind, identity_value) in (select * from unnest(%s::text[], %s::text[]))
                limit 1
                """,
                (lease.organization_id, [k for k, _ in identities], [v for _, v in identities]),
            ).fetchone()
            if hit:
                raise ActionNotExecutable("recipient or prospect is suppressed")
        return conn.execute(
            """
            update actions
            set state = 'executing', started_at = now(), attempt = attempt + 1
            where organization_id = %s and id = %s
            returning *
            """,
            (lease.organization_id, action_id),
        ).fetchone()


def record_result(
    conn: psycopg.Connection,
    *,
    organization_id: UUID,
    action_id: UUID,
    state: str,
    provider_ref: str | None,
    result: dict[str, Any],
) -> dict[str, Any]:
    """Persist a provider outcome. Not lease-fenced: a provider receipt is fact even if the lease was lost."""
    with conn.transaction():
        action = conn.execute(
            "select state from actions where organization_id = %s and id = %s for update",
            (organization_id, action_id),
        ).fetchone()
        if action is None or state not in _ALLOWED_RESULTS.get(action["state"], set()):
            raise ActionNotExecutable(f"cannot record {state} for action in state {action and action['state']}")
        return conn.execute(
            """
            update actions
            set state = %s, provider_ref = coalesce(%s, provider_ref), result_json = %s,
                completed_at = case when %s in ('succeeded', 'failed') then now() else completed_at end
            where organization_id = %s and id = %s
            returning *
            """,
            (state, provider_ref, Jsonb(result), state, organization_id, action_id),
        ).fetchone()


def expire_executing(
    conn: psycopg.Connection, *, timeout_seconds: int, organization_id: UUID | None = None
) -> list[UUID]:
    """Executing actions past the timeout become unknown and get exactly one reconcile task each."""
    with conn.transaction():
        rows = conn.execute(
            """
            update actions
            set state = 'unknown',
                result_json = coalesce(result_json, '{}'::jsonb) || jsonb_build_object('unknown_reason', 'executing_timeout')
            where state = 'executing' and started_at < now() - make_interval(secs => %s)
              and (%s::uuid is null or organization_id = %s::uuid)
            returning id, organization_id, campaign_id, conversation_id, decision_id
            """,
            (timeout_seconds, organization_id, organization_id),
        ).fetchall()
        for row in rows:
            conn.execute(
                """
                insert into tasks (organization_id, campaign_id, conversation_id, kind, dedupe_key, payload_json, status)
                values (%s, %s, %s, 'reconcile_action', %s, %s, 'ready')
                on conflict (organization_id, dedupe_key) do nothing
                """,
                (
                    row["organization_id"],
                    row["campaign_id"],
                    row["conversation_id"],
                    f"reconcile:{row['id']}",
                    Jsonb(
                        {
                            "schema_version": "outcome.v1",
                            "campaign_id": str(row["campaign_id"]),
                            "conversation_id": str(row["conversation_id"]) if row["conversation_id"] else None,
                            "expected_conversation_version": None,
                            "trigger_message_id": None,
                            "decision_id": str(row["decision_id"]),
                            "input_ref_ids": [str(row["id"])],
                        }
                    ),
                ),
            )
    return [row["id"] for row in rows]
