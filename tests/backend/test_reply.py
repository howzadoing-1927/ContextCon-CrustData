from uuid import uuid4

from conftest import launch
from services.core import db
from services.core.campaigns import get_mission_detail
from services.core.contracts.enums import ReplyIntent
from services.core.contracts.google_adapter import PolledMessage
from services.core.testing.fixture_google_adapter import FIXTURE_NOW, FixtureGoogleAdapter
from services.models.reply import classify_intent
from services.worker import queue
from services.worker.inbox import handle_poll_inbox
from services.worker.qualify import handle_qualify_and_draft
from services.worker.reply import handle_reply
from services.worker.send import handle_send_email
from test_qualify_draft import FakeModel, good_draft, verdict
from test_send import _claim_send, _seed_qualify


def test_classify_intent_accept_question_decline_and_ambiguous_range():
    assert classify_intent("Thursday 10:00 works for me. Let's do the 15-minute intro.") is ReplyIntent.ACCEPT_SLOT
    assert classify_intent("Yes, interested in a demo.") is ReplyIntent.INTERESTED
    assert classify_intent("How long is onboarding?") is ReplyIntent.QUESTION
    assert classify_intent("Not interested, thanks.") is ReplyIntent.DECLINE
    assert classify_intent("Please unsubscribe me.") is ReplyIntent.OPT_OUT
    assert classify_intent("Thursday or Friday afternoon?") is ReplyIntent.AMBIGUOUS
    assert classify_intent("Thursday or Friday afternoon") is ReplyIntent.SCHEDULE_PREFERENCE
    assert classify_intent("Out of office until Monday") is ReplyIntent.OUT_OF_OFFICE


def _send_initial(database_url, conn, tenant, launched):
    handle_qualify_and_draft(
        conn, _seed_qualify(database_url, conn, tenant, launched), client=FakeModel(good_draft, verdict("pass"))
    )
    lease = _claim_send(database_url, tenant)
    assert lease is not None, "send_email was not claimable"
    handle_send_email(conn, lease, adapter=FixtureGoogleAdapter())


def _claim(database_url, tenant, kind, owner):
    with db.connect(database_url) as c:
        lease = queue.claim(c, owner=owner, kinds=[kind], lease_seconds=60, organization_id=tenant.organization_id)
    assert lease is not None, f"{kind} was not claimable"
    return lease


def _inbound(tenant, thread_id, body, subject="Re: demo"):
    return PolledMessage(
        provider_message_id=f"buyer-{uuid4()}",
        provider_thread_id=thread_id,
        rfc_message_id=f"<buyer.{uuid4()}@example.invalid>",
        in_reply_to=None,
        from_email=tenant.buyer_test_email,
        to_emails=["seller@example.invalid"],
        subject=subject,
        body_text=body,
        received_at=FIXTURE_NOW,
    )


def test_fixture_poll_synthesizes_accept_then_books_and_writes_handoff(make_tenant, database_url, conn):
    tenant = make_tenant()
    launched = launch(database_url, tenant)
    _send_initial(database_url, conn, tenant, launched)

    handle_poll_inbox(conn, _claim(database_url, tenant, "poll_inbox", "poll-1"), adapter=FixtureGoogleAdapter())
    handle_reply(conn, _claim(database_url, tenant, "handle_reply", "reply-1"), adapter=FixtureGoogleAdapter())

    detail = get_mission_detail(conn, organization_id=tenant.organization_id, campaign_id=launched.id)
    inbound = [m for m in detail.conversation.messages if m.direction == "inbound"]
    outbound = [m for m in detail.conversation.messages if m.direction == "outbound"]
    campaign = conn.execute("select status, stage from campaigns where id = %s", (launched.id,)).fetchone()

    assert inbound and inbound[0].execution_label == "SIMULATED_BUYER"
    assert inbound[0].status == "received"
    assert len(outbound) == 2
    assert "locking that time" in outbound[1].body_text.lower()
    assert detail.conversation.state == "booked"
    assert detail.conversation.booking is not None
    assert detail.conversation.booking.html_link.startswith("https://meet.google.com/")
    assert detail.handoff is not None
    assert detail.handoff.booking.event_id == detail.conversation.booking.event_id
    assert detail.handoff.buyer_stated_needs
    assert campaign["status"] == "completed" and campaign["stage"] == "handoff_written"


def test_question_is_answered_and_does_not_book(make_tenant, database_url, conn):
    tenant = make_tenant()
    launched = launch(database_url, tenant)
    _send_initial(database_url, conn, tenant, launched)
    thread = conn.execute(
        "select provider_thread_id from conversations where campaign_id = %s", (launched.id,)
    ).fetchone()["provider_thread_id"]
    adapter = FixtureGoogleAdapter(inbox=[_inbound(tenant, thread, "How long is onboarding?")])

    handle_poll_inbox(conn, _claim(database_url, tenant, "poll_inbox", "poll-q"), adapter=adapter)
    handle_reply(conn, _claim(database_url, tenant, "handle_reply", "reply-q"), adapter=adapter)

    detail = get_mission_detail(conn, organization_id=tenant.organization_id, campaign_id=launched.id)
    outbound = [m for m in detail.conversation.messages if m.direction == "outbound"]
    campaign = conn.execute("select status from campaigns where id = %s", (launched.id,)).fetchone()

    assert detail.conversation.state == "waiting_reply"
    assert detail.handoff is None
    assert "don't want to guess" in outbound[-1].body_text.lower()
    assert campaign["status"] == "running"
    assert conn.execute(
        "select 1 from tasks where campaign_id = %s and kind = 'poll_inbox' and status = 'ready'",
        (launched.id,),
    ).fetchone()


def test_decline_ends_without_follow_up_send(make_tenant, database_url, conn):
    tenant = make_tenant()
    launched = launch(database_url, tenant)
    _send_initial(database_url, conn, tenant, launched)
    thread = conn.execute(
        "select provider_thread_id from conversations where campaign_id = %s", (launched.id,)
    ).fetchone()["provider_thread_id"]
    adapter = FixtureGoogleAdapter(inbox=[_inbound(tenant, thread, "Not interested, thanks.")])

    handle_poll_inbox(conn, _claim(database_url, tenant, "poll_inbox", "poll-d"), adapter=adapter)
    handle_reply(conn, _claim(database_url, tenant, "handle_reply", "reply-d"), adapter=adapter)

    detail = get_mission_detail(conn, organization_id=tenant.organization_id, campaign_id=launched.id)
    outbound = [m for m in detail.conversation.messages if m.direction == "outbound"]
    campaign = conn.execute("select status, stage from campaigns where id = %s", (launched.id,)).fetchone()

    assert detail.conversation.state == "declined"
    assert detail.handoff is None
    assert len(outbound) == 1
    assert campaign["status"] == "completed" and campaign["stage"] == "declined"


def test_schedule_range_clarifies_and_does_not_book(make_tenant, database_url, conn):
    tenant = make_tenant()
    launched = launch(database_url, tenant)
    _send_initial(database_url, conn, tenant, launched)
    thread = conn.execute(
        "select provider_thread_id from conversations where campaign_id = %s", (launched.id,)
    ).fetchone()["provider_thread_id"]
    adapter = FixtureGoogleAdapter(inbox=[_inbound(tenant, thread, "Thursday or Friday afternoon")])

    handle_poll_inbox(conn, _claim(database_url, tenant, "poll_inbox", "poll-s"), adapter=adapter)
    handle_reply(conn, _claim(database_url, tenant, "handle_reply", "reply-s"), adapter=adapter)

    detail = get_mission_detail(conn, organization_id=tenant.organization_id, campaign_id=launched.id)
    assert detail.conversation.state == "waiting_reply"
    assert detail.handoff is None
    assert "offered times" in detail.conversation.messages[-1].body_text.lower()
