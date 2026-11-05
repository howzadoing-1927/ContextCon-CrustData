from concurrent.futures import ThreadPoolExecutor

import pytest

from conftest import launch
from services.core import db
from services.worker import queue

KINDS = ["normalize_mission"]


def _claim(database_url, org, owner, lease_seconds=30):
    with db.connect(database_url) as c:
        return queue.claim(c, owner=owner, kinds=KINDS, lease_seconds=lease_seconds, organization_id=org)


def _task(conn, lease):
    return conn.execute("select * from tasks where id = %s", (lease.task_id,)).fetchone()


def _expire(conn, lease):
    """Simulate the lease running out (the worker stopped heartbeating) without racing network latency."""
    conn.execute("update tasks set lease_until = now() - interval '1 second' where id = %s", (lease.task_id,))


def test_concurrent_claims_never_share_a_task(make_tenant, database_url):
    tenant = make_tenant()
    for _ in range(5):
        launch(database_url, tenant)

    with ThreadPoolExecutor(max_workers=8) as pool:
        leases = list(pool.map(lambda i: _claim(database_url, tenant.organization_id, f"w{i}"), range(8)))

    claimed = [lease.task_id for lease in leases if lease is not None]
    assert len(claimed) == 5
    assert len(set(claimed)) == 5


def test_worker_crash_reclaim_and_stale_completion_rejected(make_tenant, database_url, conn):
    tenant = make_tenant()
    launch(database_url, tenant)

    lease_a = _claim(database_url, tenant.organization_id, "worker-a")
    assert lease_a is not None and lease_a.generation == 1 and lease_a.attempt == 1
    assert _claim(database_url, tenant.organization_id, "worker-b") is None  # lease still held

    _expire(conn, lease_a)  # worker-a "crashes": no heartbeat, no completion
    lease_b = _claim(database_url, tenant.organization_id, "worker-b")
    assert lease_b.task_id == lease_a.task_id
    assert (lease_b.generation, lease_b.attempt) == (2, 2)

    with pytest.raises(queue.LeaseLost), queue.fenced(conn, lease_a):
        queue.complete(conn, lease_a)
    with pytest.raises(queue.LeaseLost):
        queue.heartbeat(conn, lease_a, 30)
    row = _task(conn, lease_b)
    assert (row["status"], row["lease_owner"], row["lease_generation"]) == ("leased", "worker-b", 2)

    with queue.fenced(conn, lease_b):
        queue.complete(conn, lease_b)
    assert _task(conn, lease_b)["status"] == "succeeded"


def test_restarted_worker_with_same_id_cannot_commit_its_old_generation(make_tenant, database_url, conn):
    tenant = make_tenant()
    launch(database_url, tenant)
    before_crash = _claim(database_url, tenant.organization_id, "worker-1")

    _expire(conn, before_crash)
    after_restart = _claim(database_url, tenant.organization_id, "worker-1")

    assert after_restart.task_id == before_crash.task_id and after_restart.generation == before_crash.generation + 1
    with pytest.raises(queue.LeaseLost), queue.fenced(conn, before_crash):
        queue.complete(conn, before_crash)
    with queue.fenced(conn, after_restart):
        queue.complete(conn, after_restart)


def test_expired_lease_cannot_commit_even_before_reclaim(make_tenant, database_url, conn):
    tenant = make_tenant()
    launch(database_url, tenant)
    lease = _claim(database_url, tenant.organization_id, "slow-worker")

    _expire(conn, lease)

    with pytest.raises(queue.LeaseLost), queue.fenced(conn, lease):
        queue.complete(conn, lease)
    assert _task(conn, lease)["status"] == "leased"


def test_heartbeat_extends_lease(make_tenant, database_url, conn):
    tenant = make_tenant()
    launch(database_url, tenant)
    lease = _claim(database_url, tenant.organization_id, "w")
    conn.execute("update tasks set lease_until = now() + interval '2 seconds' where id = %s", (lease.task_id,))

    queue.heartbeat(conn, lease, 60)

    remaining = conn.execute(
        "select extract(epoch from lease_until - now()) as s from tasks where id = %s", (lease.task_id,)
    ).fetchone()["s"]
    assert remaining > 50
    with queue.fenced(conn, lease):
        queue.complete(conn, lease)
    assert _task(conn, lease)["status"] == "succeeded"


def test_failure_retries_then_exhausted_task_is_failed(make_tenant, database_url, conn):
    tenant = make_tenant()
    launched = launch(database_url, tenant)
    conn.execute("update tasks set max_attempts = 2 where id = %s", (launched.task_id,))

    first = _claim(database_url, tenant.organization_id, "w1")
    with queue.fenced(conn, first):
        assert queue.fail(conn, first, {"error_class": "Timeout"}, retry_after_seconds=0) == "ready"

    second = _claim(database_url, tenant.organization_id, "w2")
    assert second.attempt == 2
    _expire(conn, second)  # second worker dies; no attempts remain

    assert launched.task_id in queue.sweep_exhausted(conn)
    assert _task(conn, second)["status"] == "failed"
    assert _claim(database_url, tenant.organization_id, "w3") is None
