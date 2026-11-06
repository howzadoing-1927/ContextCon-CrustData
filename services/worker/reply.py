"""handle_reply: classify inbound, answer questions, book on explicit accept, never book an ambiguous time.

Confirm and answer mail reuse the send outbox. Booking is a display Meet receipt (no Calendar insert).
"""

from hashlib import sha256
from typing import Any, Literal
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from services.core.contracts.base import normalize_email
from services.core.contracts.enums import ReplyIntent
from services.core.contracts.google_adapter import (
    GmailSendReceipt,
    GoogleAdapter,
    GoogleAdapterError,
    GoogleConnectionRef,
    OutboundEmail,
)
from services.core.contracts.views import BookingReceipt, Handoff
from services.core.workspace import canonical_hash
from services.models.reply import classify_intent

from . import actions, queue
from .send import display_meet

_TERMINAL = ("booked", "declined", "suppressed", "needs_human", "stopped", "completed")
_BOOK = {ReplyIntent.ACCEPT_SLOT, ReplyIntent.INTERESTED}
_CLARIFY = {ReplyIntent.QUESTION, ReplyIntent.OBJECTION, ReplyIntent.AMBIGUOUS, ReplyIntent.SCHEDULE_PREFERENCE}


def _connection(conn: psycopg.Connection, organization_id: UUID) -> dict | None:
    return conn.execute(
        """
        select id, status, account_email from connections
        where organization_id = %s and provider = 'google' and purpose = 'seller'
        """,
        (organization_id,),
    ).fetchone()


def _decision(
    conn: psycopg.Connection,
    lease: queue.Lease,
    *,
    kind: str,
    status: str,
    reason: str,
    prospect_id: UUID | None,
    proposed: dict | None = None,
    input_refs: dict | None = None,
) -> UUID:
    return conn.execute(
        """
        insert into decisions (organization_id, campaign_id, prospect_id, conversation_id, task_id, kind, status,
                               reason, input_refs_json, policy_result_json, proposed_action_json)
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        returning id
        """,
        (
            lease.organization_id,
            lease.campaign_id,
            prospect_id,
            lease.conversation_id,
            lease.task_id,
            kind,
            status,
            reason,
            Jsonb(input_refs or {}),
            Jsonb({"pass": status == "accepted", "checks": []}),
            Jsonb(proposed) if proposed else None,
        ),
    ).fetchone()["id"]


def _set_campaign(conn: psycopg.Connection, lease: queue.Lease, *, status: str, stage: str, terminal: bool = False) -> None:
    conn.execute(
        """
        update campaigns
        set status = %s, stage = %s, version = version + 1,
            completed_at = case when %s then now() else completed_at end
        where organization_id = %s and id = %s
        """,
        (status, stage, terminal, lease.organization_id, lease.campaign_id),
    )


def _set_conversation(conn: psycopg.Connection, lease: queue.Lease, *, state: str, extra: dict | None = None) -> None:
    conn.execute(
        """
        update conversations
        set state = %s, version = version + 1,
            crm_json = case when %s::jsonb is null then crm_json else coalesce(crm_json, '{}'::jsonb) || %s end
        where organization_id = %s and id = %s
        """,
        (state, Jsonb(extra) if extra else None, Jsonb(extra) if extra else None, lease.organization_id, lease.conversation_id),
    )


def _reserve_outbound(conn: psycopg.Connection, organization_id: UUID, campaign_id: UUID) -> bool:
    row = conn.execute(
        """
        update campaigns
        set budget_json = jsonb_set(
              budget_json, '{usage,outbound_attempts}',
              to_jsonb(coalesce((budget_json -> 'usage' ->> 'outbound_attempts')::int, 0) + 1))
        where organization_id = %s and id = %s and status = 'running'
          and coalesce((budget_json -> 'usage' ->> 'outbound_attempts')::int, 0)
              < coalesce((limits_json ->> 'max_outbound_messages')::int, 0)
        returning id
        """,
        (organization_id, campaign_id),
    ).fetchone()
    return row is not None


def _slot_copy(text: str) -> str:
    return (text or "the time we offered").strip()


def _format_slot(booking: dict) -> str:
    start = booking.get("start") or ""
    zone = booking.get("timezone") or "UTC"
    return f"{start} ({zone})"


def _ensure_booking(*, action_id: UUID, snapshot: dict, crm: dict, execution_label: str | None) -> dict:
    existing = crm.get("booking")
    if existing:
        return existing
    slots = crm.get("offered_slots") or []
    if slots:
        slot = slots[0]
        code = display_meet(action_id=action_id, snapshot=snapshot, execution_label=execution_label)[1]
        booking = {
            **code,
            "start": slot.get("start") or code["start"],
            "end": slot.get("end") or code["end"],
            "timezone": slot.get("timezone") or code["timezone"],
        }
        return BookingReceipt.model_validate(booking).model_dump(mode="json")
    return display_meet(action_id=action_id, snapshot=snapshot, execution_label=execution_label)[1]


def _handoff(
    *,
    campaign_id: UUID,
    prospect: dict,
    conversation: dict,
    inbound: dict,
    booking: dict,
    snapshot: dict,
) -> dict:
    identity = prospect.get("identity_json") or {}
    company = (identity.get("company") or {}).get("name") or "the account"
    fit = prospect.get("fit_json") or {}
    evidence_ids = []
    for criterion in fit.get("criteria") or []:
        for item in criterion.get("evidence_ids") or []:
            try:
                evidence_ids.append(str(UUID(str(item))))
            except ValueError:
                continue
    brief = snapshot.get("seller_brief") or {}
    owner = brief.get("founder_email") if isinstance(brief, dict) else None
    body = (inbound.get("body_text") or "").strip()
    return Handoff(
        version=1,
        status="complete",
        mode="simulation",
        campaign_id=campaign_id,
        prospect_id=prospect["id"],
        conversation_id=conversation["id"],
        booking=BookingReceipt.model_validate(booking),
        fit_summary=fit.get("fit_summary")
        or f"{company} passed qualification against the founder ICP. The simulated buyer accepted a time.",
        fit_evidence_ids=list(dict.fromkeys(evidence_ids)),
        buyer_stated_needs=[{"text": body[:300], "message_id": inbound["id"]}] if body else [],
        hypotheses=[h.get("text") if isinstance(h, dict) else str(h) for h in (fit.get("hypotheses") or [])],
        open_questions=[],
        next_steps=["Join the Meet at the booked time.", "Seller prepares a 15-minute walkthrough."],
        owner_email=owner,
        notification_status="not_requested",
    ).model_dump(mode="json")


def _reply_bodies(intent: ReplyIntent, *, inbound_body: str, booking: dict | None) -> tuple[str, str]:
    slot = _format_slot(booking) if booking else "the offered weekday 10:00 slot"
    meet = (booking or {}).get("html_link") or "the Meet link in the product"
    if intent in _BOOK:
        return (
            "Re: demo time",
            (
                f"Thanks — locking that time in.\n\n"
                f"When: {slot}\nMeet: {meet}\n\n"
                "This is a simulation booking shown in the product. No Google Calendar event was inserted."
            ),
        )
    if intent is ReplyIntent.SCHEDULE_PREFERENCE:
        return (
            "Re: which time works",
            (
                "Happy to meet. I need one of the offered times, not a range.\n\n"
                f"The slot still open is {slot}. Reply if that exact time works."
            ),
        )
    excerpt = _slot_copy(inbound_body).splitlines()[0][:180]
    return (
        "Re: your question",
        (
            f'Thanks for the note about "{excerpt}".\n\n'
            "I don't want to guess beyond what we already know. A short call is the better place to answer that.\n\n"
            f"The slot we offered is still open: {slot}. Reply if that time works."
        ),
    )


def handle_reply(conn: psycopg.Connection, lease: queue.Lease, *, adapter: GoogleAdapter) -> None:
    if lease.conversation_id is None:
        with queue.fenced(conn, lease):
            queue.complete(conn, lease)
        return

    conversation = conn.execute(
        "select * from conversations where organization_id = %s and id = %s",
        (lease.organization_id, lease.conversation_id),
    ).fetchone()
    campaign = conn.execute(
        "select status, stage, launch_snapshot_json, buyer_test_email from campaigns "
        "where organization_id = %s and id = %s",
        (lease.organization_id, lease.campaign_id),
    ).fetchone()
    if conversation is None or campaign is None:
        with queue.fenced(conn, lease):
            queue.complete(conn, lease)
        return
    if conversation["state"] in _TERMINAL:
        with queue.fenced(conn, lease):
            queue.complete(conn, lease)
        return

    trigger = lease.payload.get("trigger_message_id") or (conversation.get("crm_json") or {}).get("last_inbound_id")
    inbound = (
        conn.execute(
            "select * from messages where organization_id = %s and id = %s and direction = 'inbound'",
            (lease.organization_id, trigger),
        ).fetchone()
        if trigger
        else None
    )
    if inbound is None:
        inbound = conn.execute(
            """
            select * from messages
            where organization_id = %s and conversation_id = %s and direction = 'inbound'
            order by received_at desc, id desc limit 1
            """,
            (lease.organization_id, lease.conversation_id),
        ).fetchone()
    if inbound is None:
        with queue.fenced(conn, lease):
            queue.complete(conn, lease)
        return

    intent = classify_intent(inbound["body_text"])
    prospect = conn.execute(
        "select * from prospects where organization_id = %s and id = %s",
        (lease.organization_id, conversation["prospect_id"]),
    ).fetchone()
    snapshot = campaign["launch_snapshot_json"] or {}
    crm = conversation.get("crm_json") or {}

    if intent is ReplyIntent.OPT_OUT:
        with queue.fenced(conn, lease):
            conn.execute(
                """
                insert into suppressions (organization_id, identity_kind, identity_value, reason, source_message_id)
                values (%s, 'email', %s, 'opt_out', %s)
                on conflict (organization_id, identity_kind, identity_value) do nothing
                """,
                (lease.organization_id, normalize_email(campaign["buyer_test_email"]), inbound["id"]),
            )
            _set_conversation(conn, lease, state="suppressed")
            _set_campaign(conn, lease, status="stopped", stage="suppressed", terminal=True)
            _decision(
                conn, lease, kind="reply", status="accepted", prospect_id=conversation["prospect_id"],
                reason="Intent: opt_out. Recipient suppressed; no further mail.",
                input_refs={"intent": intent.value, "message_id": str(inbound["id"])},
            )
            queue.complete(conn, lease)
        return

    if intent is ReplyIntent.DECLINE:
        with queue.fenced(conn, lease):
            _set_conversation(conn, lease, state="declined")
            _set_campaign(conn, lease, status="completed", stage="declined", terminal=True)
            _decision(
                conn, lease, kind="reply", status="accepted", prospect_id=conversation["prospect_id"],
                reason="Intent: decline. Conversation ends with no booking follow-up.",
                input_refs={"intent": intent.value, "message_id": str(inbound["id"])},
            )
            queue.complete(conn, lease)
        return

    if intent is ReplyIntent.OUT_OF_OFFICE:
        with queue.fenced(conn, lease):
            _set_conversation(conn, lease, state="waiting_reply")
            _decision(
                conn, lease, kind="reply", status="accepted", prospect_id=conversation["prospect_id"],
                reason="Out-of-office. Stay waiting; do not book.",
                input_refs={"intent": intent.value, "message_id": str(inbound["id"])},
            )
            queue.complete(conn, lease)
        return

    if intent is ReplyIntent.REQUEST_HUMAN:
        with queue.fenced(conn, lease):
            _set_conversation(conn, lease, state="needs_human")
            _set_campaign(conn, lease, status="needs_human", stage="reply")
            _decision(
                conn, lease, kind="reply", status="blocked", prospect_id=conversation["prospect_id"],
                reason="Buyer asked for a human. No autonomous send or booking.",
                input_refs={"intent": intent.value, "message_id": str(inbound["id"])},
            )
            queue.complete(conn, lease)
        return

    purpose: Literal["confirm", "answer"] = "confirm" if intent in _BOOK else "answer"
    booking = crm.get("booking")
    if intent in _BOOK and not booking:
        # Placeholder until the confirm action exists; replaced after prepare with the real action id.
        booking = display_meet(action_id=inbound["id"], snapshot=snapshot, execution_label="FIXTURE")[1]
    subject, body_text = _reply_bodies(intent, inbound_body=inbound["body_text"], booking=booking)
    last_out = conn.execute(
        """
        select subject, rfc_message_id, provider_thread_id from messages
        where organization_id = %s and conversation_id = %s and direction = 'outbound'
        order by created_at desc, id desc limit 1
        """,
        (lease.organization_id, lease.conversation_id),
    ).fetchone()
    if last_out and last_out["subject"]:
        subject = last_out["subject"] if last_out["subject"].lower().startswith("re:") else f"Re: {last_out['subject']}"
        subject = subject[:200]

    sent = _send_followup(
        conn,
        lease,
        adapter=adapter,
        conversation=conversation,
        prospect=prospect or {},
        inbound=inbound,
        purpose=purpose,
        subject=subject,
        body_text=body_text,
        recipient=campaign["buyer_test_email"],
        thread_id=conversation.get("provider_thread_id") or (last_out["provider_thread_id"] if last_out else None),
        in_reply_to=last_out["rfc_message_id"] if last_out else None,
    )
    if sent is None:
        return

    action, receipt = sent
    with queue.fenced(conn, lease):
        conn.execute(
            """
            insert into messages
              (organization_id, conversation_id, connection_id, action_id, direction, provider_message_id,
               rfc_message_id, provider_thread_id, in_reply_to, from_email, to_emails, subject, body_text,
               body_sha256, received_at, status)
            values (%s, %s, %s, %s, 'outbound', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'sent')
            on conflict (organization_id, action_id) do nothing
            """,
            (
                lease.organization_id,
                lease.conversation_id,
                conversation["connection_id"],
                action["id"],
                receipt.provider_message_id,
                action["payload_json"]["rfc_message_id"],
                receipt.provider_thread_id,
                action["payload_json"].get("in_reply_to"),
                action["payload_json"]["from_email"],
                [action["payload_json"]["to_email"]],
                action["payload_json"]["subject"],
                action["payload_json"]["body_text"],
                sha256(action["payload_json"]["body_text"].encode()).hexdigest(),
                receipt.sent_at,
            ),
        )
        if intent in _BOOK:
            booking = _ensure_booking(
                action_id=action["id"],
                snapshot=snapshot,
                crm=crm,
                execution_label=getattr(receipt, "execution_label", None),
            )
            payload = _handoff(
                campaign_id=lease.campaign_id,
                prospect=prospect or {},
                conversation=conversation,
                inbound=inbound,
                booking=booking,
                snapshot=snapshot,
            )
            conn.execute(
                """
                update conversations
                set state = 'booked', version = version + 1, handoff_json = %s,
                    crm_json = coalesce(crm_json, '{}'::jsonb) || %s
                where organization_id = %s and id = %s
                """,
                (
                    Jsonb(payload),
                    Jsonb({"booking": booking, "handoff_written": True}),
                    lease.organization_id,
                    lease.conversation_id,
                ),
            )
            _set_campaign(conn, lease, status="completed", stage="handoff_written", terminal=True)
            _decision(
                conn, lease, kind="reply", status="accepted", prospect_id=conversation["prospect_id"],
                reason="Intent: accept. Confirmation sent; display Meet booked; handoff written.",
                proposed={"action_id": str(action["id"]), "intent": intent.value},
                input_refs={"message_id": str(inbound["id"]), "intent": intent.value},
            )
            _decision(
                conn, lease, kind="book", status="accepted", prospect_id=conversation["prospect_id"],
                reason="Simulation booking persisted. No Calendar insert.",
                proposed=booking,
                input_refs={"action_id": str(action["id"])},
            )
        else:
            _set_conversation(conn, lease, state="waiting_reply")
            _decision(
                conn, lease, kind="reply", status="accepted", prospect_id=conversation["prospect_id"],
                reason=f"Intent: {intent.value}. Answered; no booking.",
                proposed={"action_id": str(action["id"]), "intent": intent.value},
                input_refs={"message_id": str(inbound["id"]), "intent": intent.value},
            )
            conn.execute(
                """
                insert into tasks (organization_id, campaign_id, conversation_id, kind, dedupe_key, payload_json, status)
                values (%s, %s, %s, 'poll_inbox', %s, %s, 'ready')
                on conflict (organization_id, dedupe_key) do nothing
                """,
                (
                    lease.organization_id,
                    lease.campaign_id,
                    lease.conversation_id,
                    f"poll:{lease.conversation_id}:{inbound['id']}",
                    Jsonb(
                        {
                            "campaign_id": str(lease.campaign_id),
                            "conversation_id": str(lease.conversation_id),
                            "trigger_message_id": str(inbound["id"]),
                        }
                    ),
                ),
            )
        queue.complete(conn, lease)


def _send_followup(
    conn: psycopg.Connection,
    lease: queue.Lease,
    *,
    adapter: GoogleAdapter,
    conversation: dict,
    prospect: dict,
    inbound: dict,
    purpose: str,
    subject: str,
    body_text: str,
    recipient: str,
    thread_id: str | None,
    in_reply_to: str | None,
) -> tuple[dict[str, Any], Any] | None:
    connection = _connection(conn, lease.organization_id)
    if connection is None or connection["status"] != "connected" or not connection.get("account_email"):
        with queue.fenced(conn, lease):
            _decision(
                conn, lease, kind="reply", status="blocked", prospect_id=conversation["prospect_id"],
                reason="Seller connection is not ready for a follow-up send.",
                input_refs={"message_id": str(inbound["id"])},
            )
            queue.complete(conn, lease)
        return None

    key = f"email:{lease.conversation_id}:reply:{inbound['id']}"
    rfc_id = f"<outcome.{lease.conversation_id}.reply.{inbound['id']}@outcome.invalid>"
    with queue.fenced(conn, lease):
        if not _reserve_outbound(conn, lease.organization_id, lease.campaign_id):
            _decision(
                conn, lease, kind="reply", status="blocked", prospect_id=conversation["prospect_id"],
                reason="Outbound budget exhausted; follow-up not sent.",
                input_refs={"message_id": str(inbound["id"])},
            )
            queue.complete(conn, lease)
            return None
        payload = {
            "to_email": recipient,
            "from_email": connection["account_email"],
            "subject": subject,
            "body_text": body_text,
            "rfc_message_id": rfc_id,
            "in_reply_to": in_reply_to,
            "purpose": purpose,
            "suppression_identities": [{"kind": "email", "value": recipient}],
        }
        if prospect.get("canonical_company_ref"):
            payload["suppression_identities"].append({"kind": "company", "value": prospect["canonical_company_ref"]})
        request_hash = canonical_hash(payload)
        decision_id = _decision(
            conn,
            lease,
            kind="reply",
            status="accepted",
            prospect_id=conversation["prospect_id"],
            reason=f"Sending {purpose} after intent classification.",
            input_refs={"message_id": str(inbound["id"]), "purpose": purpose},
        )
        action = actions.prepare(
            conn,
            organization_id=lease.organization_id,
            campaign_id=lease.campaign_id,
            conversation_id=lease.conversation_id,
            decision_id=decision_id,
            kind="email_send",
            idempotency_key=key,
            request_hash=request_hash,
            payload=payload,
        )
        if action["state"] == "succeeded" and action.get("result_json"):
            return action, GmailSendReceipt.model_validate(action["result_json"])
        if action["state"] == "unknown":
            queue.complete(conn, lease)
            return None

    try:
        executing = actions.begin_execute(conn, lease, action["id"])
    except actions.ActionNotExecutable as exc:
        with queue.fenced(conn, lease):
            _decision(
                conn, lease, kind="reply", status="blocked", prospect_id=conversation["prospect_id"],
                reason=f"Follow-up blocked at lock-time: {exc}",
                input_refs={"message_id": str(inbound["id"])},
            )
            queue.complete(conn, lease)
        return None

    outbound = OutboundEmail(
        action_id=executing["id"],
        action_key=key,
        request_hash=action["request_hash"],
        rfc_message_id=rfc_id,
        from_email=connection["account_email"],
        to_email=recipient,
        subject=subject,
        body_text=body_text,
        provider_thread_id=thread_id,
        in_reply_to=in_reply_to,
        references=[in_reply_to] if in_reply_to else [],
    )
    try:
        receipt = adapter.gmail_send(
            GoogleConnectionRef(
                organization_id=lease.organization_id,
                connection_id=connection["id"],
                account_email=connection["account_email"],
            ),
            outbound,
        )
    except GoogleAdapterError as exc:
        failure = exc.failure
        actions.record_result(
            conn,
            organization_id=lease.organization_id,
            action_id=executing["id"],
            state="unknown" if failure.may_have_applied else "failed",
            provider_ref=None,
            result={"google_failure": failure.model_dump(mode="json")},
        )
        with queue.fenced(conn, lease):
            _set_conversation(conn, lease, state="send_unknown" if failure.may_have_applied else "needs_human")
            _set_campaign(conn, lease, status="needs_human", stage="reply")
            _decision(
                conn, lease, kind="reply", status="blocked", prospect_id=conversation["prospect_id"],
                reason="Follow-up send did not get a clean provider receipt. No booking.",
                input_refs={"action_id": str(executing["id"])},
            )
            queue.complete(conn, lease)
        return None

    actions.record_result(
        conn,
        organization_id=lease.organization_id,
        action_id=executing["id"],
        state="succeeded",
        provider_ref=receipt.provider_message_id,
        result=receipt.model_dump(mode="json"),
    )
    return executing, receipt
