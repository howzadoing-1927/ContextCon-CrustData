"""poll_inbox: read the thread, persist new inbound from the consented buyer, queue handle_reply.

Fixture Gmail does not invent mail. The founder types a test-buyer reply in the mission UI.
"""

from hashlib import sha256
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from services.core.contracts.base import normalize_email
from services.core.contracts.google_adapter import GoogleAdapter, GoogleConnectionRef
from services.core.contracts.version import CONTRACT_VERSION

from . import queue

_POLLABLE = ("waiting_reply", "waiting_slot_acceptance", "offering_slots")


def _connection(conn: psycopg.Connection, organization_id: UUID) -> dict | None:
    return conn.execute(
        """
        select id, status, account_email, granted_scopes from connections
        where organization_id = %s and provider = 'google' and purpose = 'seller'
        """,
        (organization_id,),
    ).fetchone()


def handle_poll_inbox(conn: psycopg.Connection, lease: queue.Lease, *, adapter: GoogleAdapter) -> None:
    if lease.conversation_id is None:
        with queue.fenced(conn, lease):
            queue.complete(conn, lease)
        return

    conversation = conn.execute(
        "select * from conversations where organization_id = %s and id = %s",
        (lease.organization_id, lease.conversation_id),
    ).fetchone()
    campaign = conn.execute(
        "select status, buyer_test_email from campaigns where organization_id = %s and id = %s",
        (lease.organization_id, lease.campaign_id),
    ).fetchone()
    if (
        conversation is None
        or campaign is None
        or campaign["status"] not in {"running", "waiting_reply"}
        or conversation["state"] not in _POLLABLE
        or not conversation.get("provider_thread_id")
    ):
        with queue.fenced(conn, lease):
            queue.complete(conn, lease)
        return

    connection = _connection(conn, lease.organization_id)
    if connection is None or connection["status"] != "connected" or not connection.get("account_email"):
        with queue.fenced(conn, lease):
            queue.complete(conn, lease)
        return

    after = conn.execute(
        """
        select max(received_at) as after from messages
        where organization_id = %s and conversation_id = %s and direction = 'inbound'
        """,
        (lease.organization_id, lease.conversation_id),
    ).fetchone()["after"]
    known = {
        row["provider_message_id"]
        for row in conn.execute(
            """
            select provider_message_id from messages
            where organization_id = %s and conversation_id = %s and provider_message_id is not null
            """,
            (lease.organization_id, lease.conversation_id),
        ).fetchall()
    }

    poll = adapter.gmail_poll_thread(
        GoogleConnectionRef(
            organization_id=lease.organization_id,
            connection_id=connection["id"],
            account_email=connection["account_email"],
        ),
        conversation["provider_thread_id"],
        after,
    )
    buyer = normalize_email(conversation["buyer_test_email"])
    inbound = [
        m
        for m in poll.messages
        if m.provider_message_id not in known and normalize_email(m.from_email) == buyer
    ]
    label = str(poll.execution_label)

    with queue.fenced(conn, lease):
        inserted: list[UUID] = []
        labels = dict((conversation.get("crm_json") or {}).get("inbound_labels") or {})
        for message in inbound:
            row = conn.execute(
                """
                insert into messages
                  (organization_id, conversation_id, connection_id, direction, provider_message_id,
                   rfc_message_id, provider_thread_id, in_reply_to, from_email, to_emails, subject,
                   body_text, body_sha256, received_at, status)
                values (%s, %s, %s, 'inbound', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'received')
                on conflict (connection_id, provider_message_id) do nothing
                returning id, provider_message_id
                """,
                (
                    lease.organization_id,
                    lease.conversation_id,
                    conversation["connection_id"],
                    message.provider_message_id,
                    message.rfc_message_id,
                    message.provider_thread_id,
                    message.in_reply_to,
                    message.from_email,
                    [str(e) for e in message.to_emails],
                    message.subject,
                    message.body_text,
                    sha256(message.body_text.encode()).hexdigest(),
                    message.received_at,
                ),
            ).fetchone()
            if row:
                inserted.append(row["id"])
                labels[row["provider_message_id"]] = label

        if inserted:
            trigger = inserted[-1]
            conn.execute(
                """
                update conversations
                set state = 'evaluating_reply',
                    version = version + 1,
                    last_inbound_at = now(),
                    crm_json = coalesce(crm_json, '{}'::jsonb) || %s
                where organization_id = %s and id = %s
                """,
                (
                    Jsonb({"inbound_labels": labels, "last_inbound_id": str(trigger)}),
                    lease.organization_id,
                    lease.conversation_id,
                ),
            )
            conn.execute(
                """
                insert into decisions (organization_id, campaign_id, prospect_id, conversation_id, task_id, kind,
                                       status, reason, input_refs_json, policy_result_json)
                values (%s, %s, %s, %s, %s, 'poll', 'accepted', %s, %s, %s)
                """,
                (
                    lease.organization_id,
                    lease.campaign_id,
                    conversation["prospect_id"],
                    lease.conversation_id,
                    lease.task_id,
                    f"Persisted {len(inserted)} inbound message(s).",
                    Jsonb({"message_ids": [str(i) for i in inserted], "execution_label": label}),
                    Jsonb({"pass": True, "checks": []}),
                ),
            )
            conn.execute(
                """
                insert into tasks (organization_id, campaign_id, conversation_id, kind, dedupe_key, payload_json, status)
                values (%s, %s, %s, 'handle_reply', %s, %s, 'ready')
                on conflict (organization_id, dedupe_key) do nothing
                """,
                (
                    lease.organization_id,
                    lease.campaign_id,
                    lease.conversation_id,
                    f"reply:{lease.conversation_id}:{trigger}",
                    Jsonb(
                        {
                            "schema_version": CONTRACT_VERSION,
                            "campaign_id": str(lease.campaign_id),
                            "conversation_id": str(lease.conversation_id),
                            "expected_conversation_version": conversation["version"] + 1,
                            "trigger_message_id": str(trigger),
                            "decision_id": None,
                            "input_ref_ids": [str(i) for i in inserted],
                        }
                    ),
                ),
            )
        else:
            conn.execute(
                """
                insert into decisions (organization_id, campaign_id, prospect_id, conversation_id, task_id, kind,
                                       status, reason, input_refs_json, policy_result_json)
                values (%s, %s, %s, %s, %s, 'poll', 'accepted', 'No new inbound from the consented buyer.', %s, %s)
                """,
                (
                    lease.organization_id,
                    lease.campaign_id,
                    conversation["prospect_id"],
                    lease.conversation_id,
                    lease.task_id,
                    Jsonb({"execution_label": label}),
                    Jsonb({"pass": True, "checks": []}),
                ),
            )
        queue.complete(conn, lease)
