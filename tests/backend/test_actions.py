import time

import psycopg
import pytest

from conftest import launch
from services.core import db
from services.worker import actions, queue

HASH_A = "a" * 64
HASH_B = "b" * 64


@pytest.fixture
def setup(make_tenant, database_url, conn):
    tenant = make_tenant()
    launched = launch(database_url, tenant)
    with psycopg.connect(database_url, **db.connect_kwargs()) as c:
        lease = queue.claim(
            c, owner="action-worker", kinds=["normalize_mission"], lease_seconds=30, organization_id=tenant.organization_id
        )
    return tenant, launched, lease


def _prepare(conn, tenant, launched, key="email:conv:initial:initial", request_hash=HASH_A, payload=None):
    return actions.prepare(
        conn,
        organization_id=tenant.organization_id,
        campaign_id=launched.id,
        conversation_id=None,
        decision_id=launched.last_decision_id,
        kind="email_send",
        idempotency_key=key,
        request_hash=request_hash,
        payload=payload or {"to_email": tenant.buyer_test_email},
    )


def test_prepare_is_idempotent_and_conflicts_on_different_hash(setup, conn):
    tenant, launched, _ = setup

    first = _prepare(conn, tenant, launched)
    again = _prepare(conn, tenant, launched)

    assert first["id"] == again["id"] and first["state"] == "prepared"
    with pytest.raises(actions.ActionConflict):
        _prepare(conn, tenant, launched, request_hash=HASH_B)


def test_begin_execute_moves_prepared_to_executing_once(setup, conn):
    tenant, launched, lease = setup
    action = _prepare(conn, tenant, launched)

    executing = actions.begin_execute(conn, lease, action["id"])

    assert executing["state"] == "executing" and executing["attempt"] == 1 and executing["started_at"] is not None
    with pytest.raises(actions.ActionNotExecutable):
        actions.begin_execute(conn, lease, action["id"])


def test_stopped_campaign_blocks_execution(setup, conn):
    tenant, launched, lease = setup
    action = _prepare(conn, tenant, launched)
    conn.execute("update public.campaigns set status = 'stopped' where id = %s", (launched.id,))

    with pytest.raises(actions.ActionNotExecutable, match="stopped"):
        actions.begin_execute(conn, lease, action["id"])
    assert conn.execute("select state from public.actions where id = %s", (action["id"],)).fetchone()["state"] == "prepared"


def test_suppressed_recipient_blocks_execution(setup, conn):
    tenant, launched, lease = setup
    action = _prepare(conn, tenant, launched)
    conn.execute(
        "insert into public.suppressions (organization_id, identity_kind, identity_value, reason) "
        "values (%s, 'email', %s, 'opt_out')",
        (tenant.organization_id, tenant.buyer_test_email),
    )

    with pytest.raises(actions.ActionNotExecutable, match="suppressed"):
        actions.begin_execute(conn, lease, action["id"])


def test_stale_lease_cannot_begin_execution(make_tenant, database_url, conn):
    tenant = make_tenant()
    launched = launch(database_url, tenant)
    with psycopg.connect(database_url, **db.connect_kwargs()) as c:
        lease = queue.claim(c, owner="w", kinds=["normalize_mission"], lease_seconds=1, organization_id=tenant.organization_id)
    action = _prepare(conn, tenant, launched)

    time.sleep(1.3)

    with pytest.raises(queue.LeaseLost):
        actions.begin_execute(conn, lease, action["id"])


def test_expired_executing_becomes_unknown_with_one_reconcile_task_and_no_reexecution(setup, conn):
    tenant, launched, lease = setup
    action = _prepare(conn, tenant, launched)
    actions.begin_execute(conn, lease, action["id"])
    conn.execute("update public.actions set started_at = now() - interval '1 hour' where id = %s", (action["id"],))

    expired = actions.expire_executing(conn, timeout_seconds=60, organization_id=tenant.organization_id)
    again = actions.expire_executing(conn, timeout_seconds=60, organization_id=tenant.organization_id)

    assert expired == [action["id"]] and again == []
    row = conn.execute("select state, result_json from public.actions where id = %s", (action["id"],)).fetchone()
    assert row["state"] == "unknown" and row["result_json"]["unknown_reason"] == "executing_timeout"
    reconcile = conn.execute(
        "select kind, status from public.tasks where organization_id = %s and dedupe_key = %s",
        (tenant.organization_id, f"reconcile:{action['id']}"),
    ).fetchall()
    assert [(r["kind"], r["status"]) for r in reconcile] == [("reconcile_action", "ready")]
    with pytest.raises(actions.ActionNotExecutable, match="unknown"):
        actions.begin_execute(conn, lease, action["id"])


def test_record_result_allows_reconciled_success_but_not_resurrecting_failure(setup, conn):
    tenant, launched, lease = setup
    action = _prepare(conn, tenant, launched)
    actions.begin_execute(conn, lease, action["id"])
    actions.record_result(
        conn, organization_id=tenant.organization_id, action_id=action["id"], state="unknown", provider_ref=None, result={}
    )

    done = actions.record_result(
        conn,
        organization_id=tenant.organization_id,
        action_id=action["id"],
        state="succeeded",
        provider_ref="fixture-msg-1",
        result={"execution_label": "FIXTURE"},
    )

    assert done["state"] == "succeeded" and done["provider_ref"] == "fixture-msg-1"
    with pytest.raises(actions.ActionNotExecutable):
        actions.record_result(
            conn, organization_id=tenant.organization_id, action_id=action["id"], state="failed", provider_ref=None, result={}
        )
