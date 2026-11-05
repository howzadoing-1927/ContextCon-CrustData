from uuid import uuid4

from psycopg.types.json import Jsonb

from conftest import launch
from services.core import db
from services.core.campaigns import get_mission_detail
from services.core.testing.fixture_google_adapter import FixtureGoogleAdapter
from services.worker import actions, queue
from services.worker.qualify import handle_qualify_and_draft
from services.worker.send import handle_send_email
from test_qualify_draft import PLAN, MAPPING, FakeModel, full_evidence, good_draft, verdict


def _seed_qualify(database_url, conn, tenant, launched):
    conn.execute("update campaigns set stage = 'qualify', normalized_plan_json = %s where id = %s", (Jsonb(PLAN), launched.id))
    pid = uuid4()
    conn.execute(
        "insert into prospects (id, organization_id, campaign_id, canonical_company_ref, canonical_person_ref, identity_json, status) "
        "values (%s, %s, %s, 'crustdata:company:1', 'crustdata:person:2', '{}'::jsonb, 'researching')",
        (pid, tenant.organization_id, launched.id),
    )
    rel_ids = []
    for row in full_evidence():
        rid = uuid4()
        conn.execute(
            "insert into evidence (id, organization_id, campaign_id, prospect_id, entity_kind, entity_id, source_kind, provider_ref, "
            "field_path, excerpt, retrieved_at, content_sha256, fact_status) values (%s,%s,%s,%s,'company',%s,'crustdata',"
            "'crustdata:company:1',%s,%s,now(),%s,'observed')",
            (rid, tenant.organization_id, launched.id, pid, pid, row["field_path"], row["excerpt"], "f" * 64),
        )
        rel_ids.append(str(rid))
    identity = {
        "company": {"name": "Acme Labs"},
        "person": {"name": "Researched Person", "title": "VP Sales"},
        "relationship": {"status": "supported", "evidence_ids": rel_ids[:1], "reason": "matched"},
    }
    conn.execute("update prospects set identity_json = %s where id = %s", (Jsonb(identity), pid))
    conn.execute(
        "insert into decisions (organization_id, campaign_id, kind, status, reason, input_refs_json, policy_result_json) "
        "values (%s, %s, 'research', 'accepted', 'r', %s, %s)",
        (tenant.organization_id, launched.id, Jsonb({"mapping": MAPPING}), Jsonb({"pass": True, "checks": []})),
    )
    conn.execute(
        "insert into tasks (organization_id, campaign_id, kind, dedupe_key, payload_json, status) "
        "values (%s, %s, 'qualify_and_draft', %s, '{}'::jsonb, 'ready')",
        (tenant.organization_id, launched.id, f"campaign:{launched.id}:qualify_and_draft"),
    )
    with db.connect(database_url) as c:
        return queue.claim(
            c, owner="b6", kinds=["qualify_and_draft"], lease_seconds=120, organization_id=tenant.organization_id
        )


def _claim_send(database_url, tenant):
    with db.connect(database_url) as c:
        return queue.claim(c, owner="b6-send", kinds=["send_email"], lease_seconds=60, organization_id=tenant.organization_id)


def test_happy_send_records_message_waiting_reply_and_poll_task(make_tenant, database_url, conn):
    tenant = make_tenant()
    launched = launch(database_url, tenant)
    qualify_lease = _seed_qualify(database_url, conn, tenant, launched)
    handle_qualify_and_draft(conn, qualify_lease, client=FakeModel(good_draft, verdict("pass")))
    lease = _claim_send(database_url, tenant)

    handle_send_email(conn, lease, adapter=FixtureGoogleAdapter())

    action = conn.execute(
        "select state, provider_ref, result_json from actions where organization_id = %s and kind = 'email_send'",
        (tenant.organization_id,),
    ).fetchone()
    convo = conn.execute("select state, provider_thread_id from conversations where campaign_id = %s", (launched.id,)).fetchone()
    message = conn.execute("select status, direction, to_emails from messages where organization_id = %s", (tenant.organization_id,)).fetchone()
    poll = conn.execute("select status from tasks where campaign_id = %s and kind = 'poll_inbox'", (launched.id,)).fetchone()
    detail = get_mission_detail(conn, organization_id=tenant.organization_id, campaign_id=launched.id)

    assert action["state"] == "succeeded" and action["result_json"]["execution_label"] == "FIXTURE"
    assert convo["state"] == "waiting_reply" and convo["provider_thread_id"]
    assert message["status"] == "sent" and message["direction"] == "outbound"
    assert message["to_emails"] == [tenant.buyer_test_email]
    assert poll["status"] == "ready"
    assert detail.conversation.state == "waiting_reply"
    assert detail.conversation.messages[0].execution_label == "FIXTURE"
    assert detail.conversation_state == "waiting_reply"
    assert detail.conversation.offered_slots
    assert detail.conversation.booking is not None
    assert detail.conversation.booking.html_link.startswith("https://meet.google.com/")
    assert detail.conversation.booking.mode == "simulation"
    assert conn.execute("select count(*) as n from tasks where campaign_id = %s and kind = 'send_email' and status = 'succeeded'", (launched.id,)).fetchone()["n"] == 1


def test_ambiguous_send_is_unknown_reconcile_and_never_resent(make_tenant, database_url, conn):
    tenant = make_tenant()
    launched = launch(database_url, tenant)
    handle_qualify_and_draft(conn, _seed_qualify(database_url, conn, tenant, launched), client=FakeModel(good_draft, verdict("pass")))
    lease = _claim_send(database_url, tenant)

    handle_send_email(conn, lease, adapter=FixtureGoogleAdapter(mode="send_unknown"))

    action = conn.execute("select state from actions where organization_id = %s and kind = 'email_send'", (tenant.organization_id,)).fetchone()
    convo = conn.execute("select state from conversations where campaign_id = %s", (launched.id,)).fetchone()
    tasks = [
        (r["kind"], r["status"])
        for r in conn.execute("select kind, status from tasks where campaign_id = %s order by created_at, id", (launched.id,)).fetchall()
    ]

    assert action["state"] == "unknown"
    assert convo["state"] == "send_unknown"
    assert ("reconcile_action", "ready") in tasks
    assert ("poll_inbox", "ready") not in tasks
    assert conn.execute("select count(*) as n from messages where organization_id = %s", (tenant.organization_id,)).fetchone()["n"] == 0
    # Claiming send again must not create a second action or another send attempt.
    again = queue.claim(conn, owner="b6-retry", kinds=["send_email"], lease_seconds=60, organization_id=tenant.organization_id)
    assert again is None
    assert conn.execute("select count(*) as n from actions where organization_id = %s and kind = 'email_send'", (tenant.organization_id,)).fetchone()["n"] == 1


def test_suppressed_recipient_blocked_at_lock_time(make_tenant, database_url, conn, monkeypatch):
    tenant = make_tenant()
    launched = launch(database_url, tenant)
    handle_qualify_and_draft(conn, _seed_qualify(database_url, conn, tenant, launched), client=FakeModel(good_draft, verdict("pass")))
    original = actions.prepare

    def prepare_then_suppress(*args, **kwargs):
        row = original(*args, **kwargs)
        conn.execute(
            "insert into suppressions (organization_id, identity_kind, identity_value, reason) "
            "values (%s, 'email', %s, 'opt_out') on conflict (organization_id, identity_kind, identity_value) do nothing",
            (tenant.organization_id, tenant.buyer_test_email),
        )
        return row

    monkeypatch.setattr("services.worker.send.actions.prepare", prepare_then_suppress)
    lease = _claim_send(database_url, tenant)

    handle_send_email(conn, lease, adapter=FixtureGoogleAdapter())

    action = conn.execute("select state from actions where organization_id = %s and kind = 'email_send'", (tenant.organization_id,)).fetchone()
    messages = conn.execute("select count(*) as n from messages where organization_id = %s", (tenant.organization_id,)).fetchone()["n"]
    send = conn.execute(
        "select status, reason from decisions where campaign_id = %s and kind = 'send'", (launched.id,)
    ).fetchone()

    assert action["state"] == "prepared"
    assert messages == 0
    assert send["status"] == "blocked" and "lock-time" in send["reason"]


def test_stopped_campaign_does_not_send(make_tenant, database_url, conn):
    tenant = make_tenant()
    launched = launch(database_url, tenant)
    handle_qualify_and_draft(conn, _seed_qualify(database_url, conn, tenant, launched), client=FakeModel(good_draft, verdict("pass")))
    conn.execute("update campaigns set status = 'stopped' where id = %s", (launched.id,))
    lease = _claim_send(database_url, tenant)

    handle_send_email(conn, lease, adapter=FixtureGoogleAdapter())

    assert conn.execute("select count(*) as n from actions where organization_id = %s", (tenant.organization_id,)).fetchone()["n"] == 0
    assert conn.execute("select count(*) as n from messages where organization_id = %s", (tenant.organization_id,)).fetchone()["n"] == 0
    assert conn.execute("select status from tasks where id = %s", (lease.task_id,)).fetchone()["status"] == "succeeded"
