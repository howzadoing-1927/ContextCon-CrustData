"""send_email: rerun gate 1-6, reserve budget and scopes (7), prepare+lock the outbox (8), then dispatch.

The provider call happens only after begin_execute commits. Ambiguous failures mark the action unknown,
queue reconcile_action, and never resend.
"""

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import psycopg
from psycopg.types.json import Jsonb

from services.core.admin import REQUIRED_GOOGLE_SCOPES
from services.core.contracts.google_adapter import (
    GoogleAdapter,
    GoogleAdapterError,
    GoogleConnectionRef,
    OutboundEmail,
)
from services.core.contracts.model_io import DraftProposal, VerificationResult
from services.core.contracts.version import CONTRACT_VERSION
from services.core.contracts.views import BookingReceipt, Slot
from services.core.policy_gate import GateResult, initial_send_gate
from services.core.workspace import canonical_hash

from . import actions, queue

SEND_KEY = "email:{conversation}:initial:initial"
_MEET_ALPHABET = "abcdefghijklmnop"


def _meet_code(action_id: UUID) -> str:
    mapped = "".join(_MEET_ALPHABET[int(ch, 16)] for ch in action_id.hex[:10])
    return f"{mapped[:3]}-{mapped[3:7]}-{mapped[7:10]}"


def _next_weekday(start: datetime) -> datetime:
    while start.weekday() >= 5:
        start += timedelta(days=1)
    return start


def display_meet(
    *,
    action_id: UUID,
    snapshot: dict,
    execution_label: str | None,
    now: datetime | None = None,
) -> tuple[list[dict], dict]:
    """A demo meeting the UI can render. No Calendar insert — reply handling still owns the real book path."""
    zone_name = (snapshot.get("seller") or {}).get("timezone") or "Asia/Kolkata"
    try:
        zone = ZoneInfo(zone_name)
    except (ZoneInfoNotFoundError, ValueError):
        zone_name, zone = "Asia/Kolkata", ZoneInfo("Asia/Kolkata")
    duration = int((snapshot.get("policy") or {}).get("duration_minutes") or 15)
    local_now = (now or datetime.now(UTC)).astimezone(zone)
    start_local = _next_weekday(local_now.replace(hour=10, minute=0, second=0, microsecond=0))
    if start_local <= local_now:
        start_local = _next_weekday(start_local + timedelta(days=1))
    end_local = start_local + timedelta(minutes=duration)
    start, end = start_local.astimezone(UTC), end_local.astimezone(UTC)
    checked = local_now.astimezone(UTC)
    slot = Slot(
        id="slot-1",
        start=start,
        end=end,
        timezone=zone_name,
        freebusy_checked_at=checked,
    )
    code = _meet_code(action_id)
    booking = BookingReceipt(
        action_id=action_id,
        event_id=code,
        calendar_id="meet",
        start=start,
        end=end,
        timezone=zone_name,
        html_link=f"https://meet.google.com/{code}",
        verified_at=checked,
        attendee_acceptance="not_verified",
        mode="simulation",
        execution_label=execution_label,
    )
    return [slot.model_dump(mode="json")], booking.model_dump(mode="json")


def _decision(
    conn: psycopg.Connection,
    lease: queue.Lease,
    *,
    status: str,
    reason: str,
    policy: dict,
    prospect_id: UUID | None,
    proposed: dict | None = None,
    input_refs: dict | None = None,
) -> UUID:
    return conn.execute(
        """
        insert into decisions (organization_id, campaign_id, prospect_id, conversation_id, task_id, kind, status,
                               reason, input_refs_json, policy_result_json, proposed_action_json)
        values (%s, %s, %s, %s, %s, 'send', %s, %s, %s, %s, %s)
        returning id
        """,
        (
            lease.organization_id, lease.campaign_id, prospect_id, lease.conversation_id, lease.task_id,
            status, reason, Jsonb(input_refs or {}), Jsonb(policy), Jsonb(proposed) if proposed else None,
        ),
    ).fetchone()["id"]


def _set_campaign(conn: psycopg.Connection, lease: queue.Lease, *, status: str, stage: str) -> None:
    conn.execute(
        "update campaigns set status = %s, stage = %s, version = version + 1 where organization_id = %s and id = %s",
        (status, stage, lease.organization_id, lease.campaign_id),
    )


def _rfc_message_id(conversation_id: UUID) -> str:
    return f"<outcome.{conversation_id}.initial.initial@outcome.invalid>"


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


def _connection(conn: psycopg.Connection, organization_id: UUID) -> dict | None:
    return conn.execute(
        """
        select id, status, account_email, granted_scopes from connections
        where organization_id = %s and provider = 'google' and purpose = 'seller'
        """,
        (organization_id,),
    ).fetchone()


def _step7(conn: psycopg.Connection, organization_id: UUID, campaign_id: UUID) -> tuple[GateResult, dict | None]:
    gate = GateResult()
    reserved = _reserve_outbound(conn, organization_id, campaign_id)
    gate.add(7, "outbound_budget", reserved, "reserved one outbound slot" if reserved else "max_outbound_messages exhausted or campaign not running")
    connection = _connection(conn, organization_id)
    scopes = set(connection["granted_scopes"] if connection else [])
    missing = sorted(set(REQUIRED_GOOGLE_SCOPES) - scopes)
    ready = (
        connection is not None
        and connection["status"] == "connected"
        and connection.get("account_email")
        and not missing
    )
    gate.add(
        7,
        "seller_connection_ready",
        ready,
        "seller connected with required scopes" if ready else f"connection={connection and connection['status']}; missing={missing}",
    )
    return gate, connection if ready else None


def handle_send_email(conn: psycopg.Connection, lease: queue.Lease, *, adapter: GoogleAdapter) -> None:
    if lease.conversation_id is None:
        with queue.fenced(conn, lease):
            queue.complete(conn, lease)
        return

    campaign = conn.execute(
        "select status, stage, launch_snapshot_json, buyer_test_email from campaigns "
        "where organization_id = %s and id = %s",
        (lease.organization_id, lease.campaign_id),
    ).fetchone()
    conversation = conn.execute(
        "select * from conversations where organization_id = %s and id = %s",
        (lease.organization_id, lease.conversation_id),
    ).fetchone()
    if campaign is None or conversation is None or campaign["status"] != "running":
        with queue.fenced(conn, lease):
            queue.complete(conn, lease)
        return

    draft_id = lease.payload.get("decision_id") or (conversation.get("crm_json") or {}).get("draft_decision_id")
    draft_row = conn.execute(
        "select * from decisions where organization_id = %s and id = %s and kind = 'draft' and status = 'accepted'",
        (lease.organization_id, draft_id),
    ).fetchone() if draft_id else None
    prospect = conn.execute(
        "select * from prospects where organization_id = %s and id = %s",
        (lease.organization_id, conversation["prospect_id"]),
    ).fetchone()
    verify_row = conn.execute(
        "select proposed_action_json from decisions where organization_id = %s and campaign_id = %s "
        "and kind = 'verify' and status = 'accepted' order by created_at desc, id desc limit 1",
        (lease.organization_id, lease.campaign_id),
    ).fetchone()
    seller = _connection(conn, lease.organization_id)
    snapshot = campaign["launch_snapshot_json"] or {}
    recipient = campaign["buyer_test_email"]
    draft = DraftProposal.model_validate(draft_row["proposed_action_json"]) if draft_row and draft_row["proposed_action_json"] else None
    verification = (
        VerificationResult.model_validate(verify_row["proposed_action_json"])
        if verify_row and verify_row["proposed_action_json"]
        else None
    )

    gate_16 = initial_send_gate(
        conn,
        organization_id=lease.organization_id,
        campaign_id=lease.campaign_id,
        prospect=prospect or {},
        qualified=bool(prospect and prospect["status"] == "qualified"),
        draft=draft,
        verification=verification,
        deterministic_findings=[],
        snapshot=snapshot,
        recipient=recipient,
        sender=seller["account_email"] if seller else None,
        conversation=conversation,
    )

    with queue.fenced(conn, lease):
        current = conn.execute(
            "select status, stage from campaigns where organization_id = %s and id = %s for update",
            (lease.organization_id, lease.campaign_id),
        ).fetchone()
        if current["status"] != "running":
            queue.complete(conn, lease)
            return
        if not gate_16.passed:
            failure = gate_16.first_failure
            _decision(
                conn, lease, status="blocked", prospect_id=conversation["prospect_id"],
                reason=f"Blocked at step {failure['step']} {failure['name']}: {failure['reason']}",
                policy=gate_16.as_policy(),
            )
            _set_campaign(conn, lease, status="needs_human", stage="send")
            queue.complete(conn, lease)
            return

        step7, connection = _step7(conn, lease.organization_id, lease.campaign_id)
        combined = GateResult(checks=list(gate_16.checks) + list(step7.checks))
        if not step7.passed or connection is None:
            failure = step7.first_failure
            _decision(
                conn, lease, status="blocked", prospect_id=conversation["prospect_id"],
                reason=f"Blocked at step {failure['step']} {failure['name']}: {failure['reason']}",
                policy=combined.as_policy(),
            )
            _set_campaign(conn, lease, status="needs_human", stage="send")
            queue.complete(conn, lease)
            return

        key = SEND_KEY.format(conversation=lease.conversation_id)
        rfc_id = _rfc_message_id(lease.conversation_id)
        payload = {
            "to_email": recipient,
            "from_email": connection["account_email"],
            "subject": draft.subject,
            "body_text": draft.body_text,
            "rfc_message_id": rfc_id,
            "purpose": "initial",
            "suppression_identities": [
                {"kind": "email", "value": recipient},
                {"kind": "company", "value": prospect["canonical_company_ref"]},
            ],
        }
        if prospect.get("canonical_person_ref"):
            payload["suppression_identities"].append({"kind": "person", "value": prospect["canonical_person_ref"]})
        request_hash = canonical_hash(payload)
        action = actions.prepare(
            conn,
            organization_id=lease.organization_id,
            campaign_id=lease.campaign_id,
            conversation_id=lease.conversation_id,
            decision_id=UUID(str(draft_row["id"])),
            kind="email_send",
            idempotency_key=key,
            request_hash=request_hash,
            payload=payload,
        )
        if action["state"] in {"succeeded", "unknown"}:
            queue.complete(conn, lease)
            return
        outbound = OutboundEmail(
            action_id=action["id"],
            action_key=key,
            request_hash=request_hash,
            rfc_message_id=rfc_id,
            from_email=connection["account_email"],
            to_email=recipient,
            subject=draft.subject,
            body_text=draft.body_text,
            provider_thread_id=conversation.get("provider_thread_id"),
            in_reply_to=None,
            references=[],
        )
        conn.execute(
            "update conversations set crm_json = coalesce(crm_json, '{}'::jsonb) || %s where organization_id = %s and id = %s",
            (Jsonb({"pending_action_id": str(action["id"]), "pending_rfc_message_id": rfc_id}), lease.organization_id, lease.conversation_id),
        )

    try:
        executing = actions.begin_execute(conn, lease, action["id"])
    except actions.ActionNotExecutable as exc:
        with queue.fenced(conn, lease):
            combined.checks.append(
                {"step": 8, "name": "immutable_action_lock_recheck", "pass": False, "reason": str(exc)}
            )
            _decision(
                conn, lease, status="blocked", prospect_id=conversation["prospect_id"],
                reason=f"Blocked at lock-time recheck: {exc}",
                policy=combined.as_policy(),
            )
            queue.complete(conn, lease)
        return

    combined.checks.append(
        {"step": 8, "name": "immutable_action_lock_recheck", "pass": True, "reason": f"action {executing['id']} executing under lease"}
    )
    connection_ref = GoogleConnectionRef(
        organization_id=lease.organization_id,
        connection_id=connection["id"],
        account_email=connection["account_email"],
    )
    try:
        receipt = adapter.gmail_send(connection_ref, outbound)
    except GoogleAdapterError as exc:
        _on_adapter_error(conn, lease, conversation, combined, executing, outbound, exc)
        return

    _on_success(conn, lease, conversation, connection, combined, executing, outbound, receipt, snapshot)


def _on_success(
    conn: psycopg.Connection,
    lease: queue.Lease,
    conversation: dict,
    connection: dict,
    gate: GateResult,
    action: dict,
    outbound: OutboundEmail,
    receipt: Any,
    snapshot: dict,
) -> None:
    result = receipt.model_dump(mode="json")
    actions.record_result(
        conn,
        organization_id=lease.organization_id,
        action_id=action["id"],
        state="succeeded",
        provider_ref=receipt.provider_message_id,
        result=result,
    )
    with queue.fenced(conn, lease):
        conn.execute(
            """
            insert into messages
              (organization_id, conversation_id, connection_id, action_id, direction, provider_message_id,
               rfc_message_id, provider_thread_id, from_email, to_emails, subject, body_text, body_sha256,
               received_at, status)
            values (%s, %s, %s, %s, 'outbound', %s, %s, %s, %s, %s, %s, %s, %s, %s, 'sent')
            on conflict (organization_id, action_id) do nothing
            """,
            (
                lease.organization_id, lease.conversation_id, conversation["connection_id"], action["id"],
                receipt.provider_message_id, outbound.rfc_message_id, receipt.provider_thread_id,
                outbound.from_email, [outbound.to_email], outbound.subject, outbound.body_text,
                hashlib.sha256(outbound.body_text.encode()).hexdigest(), receipt.sent_at,
            ),
        )
        slots, booking = display_meet(
            action_id=action["id"],
            snapshot=snapshot,
            execution_label=getattr(receipt, "execution_label", None),
        )
        conn.execute(
            """
            update conversations
            set state = 'waiting_reply',
                version = version + 1,
                provider_thread_id = %s,
                next_poll_at = now(),
                crm_json = coalesce(crm_json, '{}'::jsonb) || %s
            where organization_id = %s and id = %s
            """,
            (
                receipt.provider_thread_id,
                Jsonb({"offered_slots": slots, "booking": booking}),
                lease.organization_id,
                lease.conversation_id,
            ),
        )
        _decision(
            conn, lease, status="accepted", prospect_id=conversation["prospect_id"],
            reason="Initial message sent; waiting for a reply.",
            policy=gate.as_policy(),
            proposed={"action_id": str(action["id"]), "rfc_message_id": outbound.rfc_message_id},
            input_refs={"action_id": str(action["id"]), "provider_message_id": receipt.provider_message_id},
        )
        conn.execute(
            """
            insert into tasks (organization_id, campaign_id, conversation_id, kind, dedupe_key, payload_json, status)
            values (%s, %s, %s, 'poll_inbox', %s, %s, 'ready')
            on conflict (organization_id, dedupe_key) do nothing
            """,
            (
                lease.organization_id, lease.campaign_id, lease.conversation_id,
                f"poll:{lease.conversation_id}",
                Jsonb(
                    {
                        "schema_version": CONTRACT_VERSION,
                        "campaign_id": str(lease.campaign_id),
                        "conversation_id": str(lease.conversation_id),
                        "expected_conversation_version": conversation["version"] + 1,
                        "trigger_message_id": None,
                        "decision_id": None,
                        "input_ref_ids": [str(action["id"])],
                    }
                ),
            ),
        )
        queue.complete(conn, lease)


def _on_adapter_error(
    conn: psycopg.Connection,
    lease: queue.Lease,
    conversation: dict,
    gate: GateResult,
    action: dict,
    outbound: OutboundEmail,
    exc: GoogleAdapterError,
) -> None:
    failure = exc.failure
    if failure.may_have_applied:
        actions.record_result(
            conn,
            organization_id=lease.organization_id,
            action_id=action["id"],
            state="unknown",
            provider_ref=None,
            result={"google_failure": failure.model_dump(mode="json")},
        )
        with queue.fenced(conn, lease):
            conn.execute(
                """
                update conversations
                set state = 'send_unknown', version = version + 1
                where organization_id = %s and id = %s
                """,
                (lease.organization_id, lease.conversation_id),
            )
            _set_campaign(conn, lease, status="needs_human", stage="send")
            _decision(
                conn, lease, status="blocked", prospect_id=conversation["prospect_id"],
                reason="Send may have applied; quarantined for reconcile. No resend.",
                policy=gate.as_policy(),
                input_refs={"action_id": str(action["id"]), "retryability": failure.retryability},
            )
            conn.execute(
                """
                insert into tasks (organization_id, campaign_id, conversation_id, kind, dedupe_key, payload_json, status)
                values (%s, %s, %s, 'reconcile_action', %s, %s, 'ready')
                on conflict (organization_id, dedupe_key) do nothing
                """,
                (
                    lease.organization_id, lease.campaign_id, lease.conversation_id,
                    f"reconcile:{action['id']}",
                    Jsonb(
                        {
                            "schema_version": CONTRACT_VERSION,
                            "campaign_id": str(lease.campaign_id),
                            "conversation_id": str(lease.conversation_id),
                            "expected_conversation_version": None,
                            "trigger_message_id": None,
                            "decision_id": str(lease.payload.get("decision_id")) if lease.payload.get("decision_id") else None,
                            "input_ref_ids": [str(action["id"])],
                            "rfc_message_id": outbound.rfc_message_id,
                        }
                    ),
                ),
            )
            queue.complete(conn, lease)
        return

    actions.record_result(
        conn,
        organization_id=lease.organization_id,
        action_id=action["id"],
        state="failed",
        provider_ref=None,
        result={"google_failure": failure.model_dump(mode="json")},
    )
    with queue.fenced(conn, lease):
        conn.execute(
            """
            update conversations
            set state = 'needs_human', version = version + 1
            where organization_id = %s and id = %s
            """,
            (lease.organization_id, lease.conversation_id),
        )
        _set_campaign(conn, lease, status="needs_human", stage="send")
        _decision(
            conn, lease, status="blocked", prospect_id=conversation["prospect_id"],
            reason=f"Provider rejected the send: {failure.redacted_detail}",
            policy=gate.as_policy(),
            input_refs={"action_id": str(action["id"]), "retryability": failure.retryability},
        )
        queue.complete(conn, lease)
