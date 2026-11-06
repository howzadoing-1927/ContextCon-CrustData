"""After the draft: send through Gmail, poll the thread, offer free slots, book the meeting, write the handoff.

Every email goes to the conversation's consented test inbox (one of the launch snapshot's buyer_tests), never to
the researched person. The campaign status is rolled up from all of its conversations. Each provider effect goes through the action outbox: intent is committed before the call, and an effect
whose failure may have applied becomes `unknown` and needs a human, never a blind retry.
"""

import hashlib
import json
import logging
import re
from datetime import UTC, datetime, time, timedelta
from collections.abc import Callable
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

import psycopg
from psycopg.types.json import Jsonb

from services.core.contracts.google_adapter import (
    CalendarEventRequest,
    GoogleAdapter,
    GoogleAdapterError,
    GoogleConnectionRef,
    OutboundEmail,
)
from services.core.contracts.base import normalize_email
from services.core.contracts.version import CONTRACT_VERSION
from services.models.client import ModelClient, ModelUnavailable, parse_json

from . import actions, queue

log = logging.getLogger("outcome.worker.converse")

POLL_SECONDS = 20
MAX_POLLS = 540  # three hours of 20 s polls
SLOT_COUNT = 3
REPLY_PROMPT_VERSION = "reply-intent.v1"
SLOT_HOURS = (time(10, 0), time(12, 30), time(15, 30), time(11, 0), time(16, 30))


# ---------------------------------------------------------------- helpers


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _decision(conn: psycopg.Connection, lease: queue.Lease, *, kind: str, status: str, reason: str,
              checks: list[dict] | None = None, prospect_id: UUID | None = None, conversation_id: UUID | None = None,
              input_refs: dict | None = None, proposed: dict | None = None, model: dict | None = None) -> UUID:
    checks = checks or []
    return conn.execute(
        """
        insert into decisions (organization_id, campaign_id, prospect_id, conversation_id, task_id, kind, status, reason,
                               input_refs_json, model_metadata_json, policy_result_json, proposed_action_json)
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) returning id
        """,
        (lease.organization_id, lease.campaign_id, prospect_id, conversation_id, lease.task_id, kind, status, reason,
         Jsonb(input_refs or {}), Jsonb(model) if model else None,
         Jsonb({"pass": all(c["pass"] for c in checks), "checks": checks}), Jsonb(proposed) if proposed else None),
    ).fetchone()["id"]


def _set_campaign(conn: psycopg.Connection, lease: queue.Lease, *, status: str, stage: str) -> None:
    conn.execute(
        "update campaigns set status = %s, stage = %s, version = version + 1, "
        "completed_at = case when %s in ('completed', 'no_match', 'stopped', 'failed') then now() else completed_at end "
        "where organization_id = %s and id = %s",
        (status, stage, status, lease.organization_id, lease.campaign_id),
    )


_BUSY = ("researching", "qualified", "drafting", "evaluating_reply", "offering_slots", "booking")
_WAITING = ("waiting_reply", "waiting_slot_acceptance")
_ATTENTION = ("needs_human", "send_unknown")


def _roll_up(conn: psycopg.Connection, lease: queue.Lease) -> None:
    """Campaign status follows all of its conversations, so one stuck conversation never blocks the others."""
    campaign = conn.execute("select status from campaigns where organization_id = %s and id = %s",
                            (lease.organization_id, lease.campaign_id)).fetchone()
    if campaign["status"] not in ("running", "waiting_reply", "needs_human"):
        return
    states = [r["state"] for r in conn.execute(
        "select state from conversations where organization_id = %s and campaign_id = %s",
        (lease.organization_id, lease.campaign_id)).fetchall()]
    counts = {s: states.count(s) for s in set(states)}
    stage = ", ".join(f"{n} {s.replace('_', ' ')}" for s, n in sorted(counts.items()))
    sending = conn.execute(
        "select exists(select 1 from tasks where organization_id = %s and campaign_id = %s and kind = 'send_email' "
        "and status in ('ready', 'leased') and id <> %s) as pending",
        (lease.organization_id, lease.campaign_id, lease.task_id)).fetchone()["pending"]
    if sending or any(s in _BUSY for s in states):
        status = "running"
    elif any(s in _WAITING for s in states):
        status = "waiting_reply"
    elif any(s in _ATTENTION for s in states):
        status = "needs_human"
    else:
        status = "completed"
    _set_campaign(conn, lease, status=status, stage=stage[:200] or "send")


def _set_conversation(conn: psycopg.Connection, lease: queue.Lease, conversation_id: UUID, *, state: str, **fields: Any) -> None:
    sets, params = ["state = %s", "version = version + 1"], [state]
    for key, value in fields.items():
        if key == "crm":
            sets.append("crm_json = crm_json || %s")
            params.append(Jsonb(value))
        elif key == "handoff":
            sets.append("handoff_json = %s")
            params.append(Jsonb(value))
        else:
            sets.append(f"{key} = %s")
            params.append(value)
    conn.execute(f"update conversations set {', '.join(sets)} where organization_id = %s and id = %s",
                 (*params, lease.organization_id, conversation_id))


def _usage(conn: psycopg.Connection, lease: queue.Lease, field: str, delta: int = 1) -> None:
    conn.execute(
        """
        update campaigns set budget_json = jsonb_set(budget_json, '{usage}',
            coalesce(budget_json -> 'usage', '{}'::jsonb) || jsonb_build_object(%(f)s::text,
              coalesce((budget_json -> 'usage' ->> %(f)s)::int, 0) + %(d)s))
        where organization_id = %(org)s and id = %(cid)s
        """,
        {"f": field, "d": delta, "org": lease.organization_id, "cid": lease.campaign_id},
    )


def _queue(conn: psycopg.Connection, lease: queue.Lease, conversation_id: UUID, kind: str, dedupe: str,
           extra: dict | None = None, delay_seconds: int = 0) -> None:
    conn.execute(
        "insert into tasks (organization_id, campaign_id, conversation_id, kind, dedupe_key, payload_json, status, run_after) "
        "values (%s, %s, %s, %s, %s, %s, 'ready', now() + make_interval(secs => %s)) "
        "on conflict (organization_id, dedupe_key) do nothing",
        (lease.organization_id, lease.campaign_id, conversation_id, kind, dedupe,
         Jsonb({"schema_version": CONTRACT_VERSION, "campaign_id": str(lease.campaign_id),
                "conversation_id": str(conversation_id), "expected_conversation_version": None,
                "trigger_message_id": None, "decision_id": None, "input_ref_ids": [], **(extra or {})}),
         delay_seconds),
    )


def _context(conn: psycopg.Connection, lease: queue.Lease) -> dict[str, Any]:
    row = conn.execute(
        """
        select c.id as conversation_id, c.state, c.prospect_id, c.provider_thread_id, c.buyer_test_email, c.crm_json,
               c.last_inbound_at, c.connection_id, k.account_email as seller_email, k.calendar_id,
               p.status as campaign_status, p.launch_snapshot_json as snapshot, p.limits_json as limits,
               p.budget_json as budget, p.buyer_test_email as campaign_buyer, pr.identity_json
        from conversations c
        join connections k on k.organization_id = c.organization_id and k.id = c.connection_id
        join campaigns p on p.organization_id = c.organization_id and p.id = c.campaign_id
        join prospects pr on pr.organization_id = c.organization_id and pr.id = c.prospect_id
        where c.organization_id = %s and c.id = %s
        """,
        (lease.organization_id, lease.conversation_id),
    ).fetchone()
    return dict(row)


def _ref(ctx: dict, lease: queue.Lease) -> GoogleConnectionRef:
    return GoogleConnectionRef(organization_id=lease.organization_id, connection_id=ctx["connection_id"],
                               account_email=ctx["seller_email"])


def _first_name(ctx: dict) -> str:
    name = ((ctx["identity_json"] or {}).get("person") or {}).get("name") or ""
    return name.split()[0] if name.strip() else "there"


# ---------------------------------------------------------------- send_email


def _record_found_email(conn: psycopg.Connection, lease: queue.Lease, ctx: dict,
                        email_lookup: Callable[[str], dict] | None) -> None:
    """Display-only: the prospect's real business email, looked up once. It is never used as a recipient."""
    person_ref = conn.execute("select canonical_person_ref from prospects where organization_id = %s and id = %s",
                              (lease.organization_id, ctx["prospect_id"])).fetchone()["canonical_person_ref"]
    if email_lookup is None or not person_ref or (ctx["identity_json"] or {}).get("found_email"):
        return
    found = email_lookup(person_ref)
    with queue.fenced(conn, lease):
        conn.execute("update prospects set identity_json = identity_json || jsonb_build_object('found_email', %s::jsonb) "
                     "where organization_id = %s and id = %s", (Jsonb(found), lease.organization_id, ctx["prospect_id"]))
        _decision(conn, lease, kind="find_contact", status="accepted" if found.get("email") else "rejected",
                  conversation_id=ctx["conversation_id"], prospect_id=ctx["prospect_id"],
                  reason=("Business email found via Crustdata (display only; mail goes to the test inbox)." if found.get("email")
                          else f"No business email found ({found.get('status')})."),
                  checks=[{"name": "not_a_recipient", "pass": True, "reason": "found email is display-only"}],
                  input_refs={"source": found.get("source"), "status": found.get("status")})
        if found.get("credits_used") is not None:
            _usage(conn, lease, "research_calls")


def handle_send_email(conn: psycopg.Connection, lease: queue.Lease, *, google: GoogleAdapter,
                      email_lookup: Callable[[str], dict] | None = None) -> None:
    ctx = _context(conn, lease)
    payload = lease.payload
    compose = payload.get("compose")
    if compose is None:
        _record_found_email(conn, lease, ctx, email_lookup)
        draft = conn.execute("select proposed_action_json from decisions where organization_id = %s and id = %s",
                             (lease.organization_id, payload["decision_id"])).fetchone()["proposed_action_json"]
        compose = {"subject": draft["subject"], "body_text": draft["body_text"], "after_state": "waiting_reply", "purpose": "initial"}

    policy = ctx["snapshot"].get("policy", {})
    inboxes = policy.get("buyer_tests") or ([policy["buyer_test"]] if policy.get("buyer_test") else [])
    rotation = {normalize_email(b["email"]) for b in inboxes}
    to_email = ctx["buyer_test_email"]
    sent_count = conn.execute("select count(*) as n from messages where organization_id = %s and conversation_id = %s "
                              "and direction = 'outbound' and status in ('sent', 'unknown')",
                              (lease.organization_id, ctx["conversation_id"])).fetchone()["n"]
    checks = [
        {"name": "step 7: outbound_budget", "pass": sent_count < ctx["limits"]["max_outbound_messages"],
         "reason": f"{sent_count} of {ctx['limits']['max_outbound_messages']} emails used"},
        {"name": "step 8: recipient_is_snapshot_buyer", "pass": normalize_email(to_email) in rotation,
         "reason": "To is this conversation's consented test inbox from the launch snapshot, not the researched person"},
        {"name": "step 8: campaign_executable", "pass": ctx["campaign_status"] in actions.EXECUTABLE_CAMPAIGN_STATUSES,
         "reason": f"campaign is {ctx['campaign_status']}"},
    ]
    last_in = conn.execute(
        "select rfc_message_id from messages where organization_id = %s and conversation_id = %s and direction = 'inbound' "
        "order by received_at desc limit 1", (lease.organization_id, ctx["conversation_id"])).fetchone()
    refs = [r["rfc_message_id"] for r in conn.execute(
        "select rfc_message_id from messages where organization_id = %s and conversation_id = %s and rfc_message_id is not null "
        "order by created_at", (lease.organization_id, ctx["conversation_id"])).fetchall()]
    subject = compose["subject"] if not ctx["provider_thread_id"] or compose["subject"].lower().startswith("re:") else f"Re: {compose['subject']}"
    idem = f"send:{ctx['conversation_id']}:{compose['purpose']}:{lease.task_id}"
    rfc = f"<{_sha(idem)[:32]}@outcome.vedora>"
    request = {"to_email": to_email, "from_email": ctx["seller_email"], "subject": subject, "body_text": compose["body_text"],
               "rfc_message_id": rfc, "provider_thread_id": ctx["provider_thread_id"],
               "in_reply_to": last_in["rfc_message_id"] if last_in else None, "references": refs[-10:]}
    request_hash = _sha(json.dumps(request, sort_keys=True))

    with queue.fenced(conn, lease):
        if not all(c["pass"] for c in checks):
            _decision(conn, lease, kind="dispatch_email", status="blocked", conversation_id=ctx["conversation_id"],
                      prospect_id=ctx["prospect_id"], checks=checks, reason="Send blocked at dispatch: " +
                      "; ".join(c["reason"] for c in checks if not c["pass"]))
            _set_conversation(conn, lease, ctx["conversation_id"], state="needs_human")
            _roll_up(conn, lease)
            queue.complete(conn, lease)
            return
        decision_id = _decision(conn, lease, kind="dispatch_email", status="accepted", conversation_id=ctx["conversation_id"],
                                prospect_id=ctx["prospect_id"], checks=checks,
                                reason=f"Sending the {compose['purpose']} email to the consented test inbox.",
                                proposed={"subject": subject, "body_text": compose["body_text"], "to": "buyer_test"})
        action = actions.prepare(conn, organization_id=lease.organization_id, campaign_id=lease.campaign_id,
                                 conversation_id=ctx["conversation_id"], decision_id=decision_id, kind="email_send",
                                 idempotency_key=idem, request_hash=request_hash, payload=request)
        conn.execute(
            """
            insert into messages (organization_id, conversation_id, connection_id, action_id, direction, rfc_message_id,
                                  provider_thread_id, in_reply_to, from_email, to_emails, subject, body_text, body_sha256, status)
            values (%s, %s, %s, %s, 'outbound', %s, %s, %s, %s, %s, %s, %s, %s, 'planned')
            on conflict (organization_id, action_id) do nothing
            """,
            (lease.organization_id, ctx["conversation_id"], ctx["connection_id"], action["id"], rfc, ctx["provider_thread_id"],
             request["in_reply_to"], ctx["seller_email"], [to_email], subject, compose["body_text"], _sha(compose["body_text"])),
        )

    actions.begin_execute(conn, lease, action["id"])
    try:
        receipt = google.gmail_send(_ref(ctx, lease), OutboundEmail(
            action_id=action["id"], action_key=idem, request_hash=request_hash, rfc_message_id=rfc,
            from_email=ctx["seller_email"], to_email=to_email, subject=subject, body_text=compose["body_text"],
            provider_thread_id=ctx["provider_thread_id"], in_reply_to=request["in_reply_to"], references=request["references"],
        ))
    except GoogleAdapterError as exc:
        failure = exc.failure
        state = "unknown" if failure.may_have_applied else "failed"
        actions.record_result(conn, organization_id=lease.organization_id, action_id=action["id"], state=state,
                              provider_ref=None, result=failure.model_dump(mode="json"))
        with queue.fenced(conn, lease):
            conn.execute("update messages set status = %s where organization_id = %s and action_id = %s",
                         ("unknown" if failure.may_have_applied else "planned", lease.organization_id, action["id"]))
            _decision(conn, lease, kind="dispatch_email", status="blocked", conversation_id=ctx["conversation_id"],
                      prospect_id=ctx["prospect_id"], reason=f"Gmail send {state}: {failure.redacted_detail}",
                      checks=[{"name": "gmail_send", "pass": False, "reason": f"{failure.phase}/{failure.retryability}"}])
            _set_conversation(conn, lease, ctx["conversation_id"], state="send_unknown" if failure.may_have_applied else "needs_human")
            _roll_up(conn, lease)
            queue.complete(conn, lease)
        return

    actions.record_result(conn, organization_id=lease.organization_id, action_id=action["id"], state="succeeded",
                          provider_ref=receipt.provider_message_id, result=receipt.model_dump(mode="json"))
    with queue.fenced(conn, lease):
        conn.execute(
            "update messages set status = 'sent', provider_message_id = %s, provider_thread_id = %s "
            "where organization_id = %s and action_id = %s",
            (receipt.provider_message_id, receipt.provider_thread_id, lease.organization_id, action["id"]),
        )
        _usage(conn, lease, "outbound_attempts")
        after = compose["after_state"]
        _set_conversation(conn, lease, ctx["conversation_id"], state=after, provider_thread_id=receipt.provider_thread_id,
                          next_poll_at=datetime.now(UTC) + timedelta(seconds=POLL_SECONDS),
                          crm={"last_sent_at": receipt.sent_at.isoformat(), "stage": after})
        if after not in ("completed", "declined"):
            _queue(conn, lease, ctx["conversation_id"], "poll_inbox", f"poll:{ctx['conversation_id']}:{receipt.provider_message_id}:0",
                   {"poll": 0, "since": receipt.sent_at.isoformat()}, delay_seconds=POLL_SECONDS)
        _roll_up(conn, lease)
        queue.complete(conn, lease)
    log.info("sent %s email message=%s thread=%s", compose["purpose"], receipt.provider_message_id, receipt.provider_thread_id)


# ---------------------------------------------------------------- poll + reply


REPLY_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["intent", "slot_id", "need", "reason"],
    "properties": {
        "intent": {"type": "string", "enum": ["picks_slot", "wants_meeting", "question", "declines", "other"]},
        "slot_id": {"type": ["string", "null"]},
        "need": {"type": ["string", "null"]},
        "reason": {"type": "string"},
    },
}

REPLY_SYSTEM = (
    "You classify one reply from a prospect in a sales email thread. Return JSON only.\n"
    "intent: picks_slot if they accept one of the offered slots (return its id in slot_id); wants_meeting if they are open to "
    "a call or ask for times; question if they ask something about the offering; declines if they say no, not interested, "
    "or ask to stop; other otherwise.\n"
    "need: one short sentence of what the prospect said they need, or null. Never invent details."
)


def _classify(client: ModelClient | None, body: str, slots: list[dict]) -> tuple[dict, dict | None]:
    lowered = body.lower()
    fallback = {"intent": "other", "slot_id": None, "need": None, "reason": "keyword fallback"}
    picked = re.search(r"\b(?:option|slot|#)?\s*([1-3])\b", lowered)
    if slots and picked and len(lowered) < 400:
        fallback = {"intent": "picks_slot", "slot_id": f"S{picked.group(1)}", "need": None, "reason": "keyword fallback"}
    elif re.search(r"not interested|no thanks|unsubscribe|stop emailing|remove me", lowered):
        fallback = {**fallback, "intent": "declines"}
    elif re.search(r"call|meet|time|schedule|interested|demo|sure|yes", lowered):
        fallback = {**fallback, "intent": "wants_meeting"}
    if client is None:
        return fallback, None
    offered = "\n".join(f"{s['id']}: {s['label']}" for s in slots) or "none offered yet"
    try:
        call = client.complete_json(role="fast", system=REPLY_SYSTEM, user=f"Offered slots:\n{offered}\n\nReply:\n{body[:3000]}",
                                    schema_name="reply_intent", schema=REPLY_SCHEMA, prompt_version=REPLY_PROMPT_VERSION, attempt=1)
        result = parse_json(call.content)
        if result.get("intent") not in REPLY_SCHEMA["properties"]["intent"]["enum"]:
            return fallback, None
        meta = {"deployment": call.deployment, "model_version": call.model_version, "prompt_version": REPLY_PROMPT_VERSION,
                "usage": {"model_calls": 1, "tokens_in": call.usage.get("prompt_tokens") or 0,
                          "tokens_out": call.usage.get("completion_tokens") or 0}}
        return result, meta
    except (ModelUnavailable, ValueError, json.JSONDecodeError):
        return fallback, None


def _free_slots(google: GoogleAdapter, ref: GoogleConnectionRef, ctx: dict) -> tuple[list[dict], str | None]:
    policy = ctx["snapshot"].get("policy", {})
    hours = policy.get("working_hours") or {}
    tz_name = hours.get("timezone") or ctx["snapshot"]["seller"]["timezone"]
    tz = ZoneInfo(tz_name)
    duration = timedelta(minutes=policy.get("duration_minutes") or 15)
    weekdays = set(hours.get("weekdays") or [1, 2, 3, 4, 5])
    start_h, end_h = time.fromisoformat(hours.get("start", "09:00")), time.fromisoformat(hours.get("end", "17:00"))
    now = datetime.now(tz)
    days = []
    day = now.date() + timedelta(days=1)
    while len(days) < 3:
        if day.isoweekday() in weekdays:
            days.append(day)
        day += timedelta(days=1)
    window_start = datetime.combine(days[0], time(0, 0), tz)
    window_end = datetime.combine(days[-1], time(23, 59), tz)
    fb = google.calendar_freebusy(ref, ctx["calendar_id"] or "primary", window_start, window_end, tz_name)
    if fb.status != "ok":
        return [], "; ".join(fb.error_reasons)
    slots: list[dict] = []
    for i, d in enumerate(days):
        for hour in SLOT_HOURS[i % 2::2]:
            start = datetime.combine(d, hour, tz)
            end = start + duration
            if not (start_h <= hour and end.time() <= end_h):
                continue
            if any(b.start < end and start < b.end for b in fb.busy):
                continue
            slots.append({"id": f"S{len(slots) + 1}", "start": start.isoformat(), "end": end.isoformat(), "timezone": tz_name,
                          "freebusy_checked_at": fb.checked_at.isoformat(),
                          "label": start.strftime("%A %d %b, %I:%M %p").replace(" 0", " ") + f" ({tz_name})"})
            break
        if len(slots) == SLOT_COUNT:
            break
    return slots, None


def handle_poll_inbox(conn: psycopg.Connection, lease: queue.Lease, *, google: GoogleAdapter, client: ModelClient | None) -> None:
    ctx = _context(conn, lease)
    poll_n = int(lease.payload.get("poll", 0))
    if ctx["state"] not in ("waiting_reply", "waiting_slot_acceptance") or ctx["campaign_status"] not in actions.EXECUTABLE_CAMPAIGN_STATUSES:
        with queue.fenced(conn, lease):
            queue.complete(conn, lease)
        return

    ref = _ref(ctx, lease)
    since = ctx["last_inbound_at"] or (datetime.fromisoformat(lease.payload["since"]) if lease.payload.get("since") else None)
    try:
        poll = google.gmail_poll_thread(ref, ctx["provider_thread_id"], since)
    except GoogleAdapterError as exc:
        with queue.fenced(conn, lease):
            _queue(conn, lease, ctx["conversation_id"], "poll_inbox", f"poll:{ctx['conversation_id']}:{lease.task_id}:retry",
                   {**lease.payload, "poll": poll_n + 1}, delay_seconds=POLL_SECONDS * 3)
            if exc.failure.retryability.value == "reauthorize":
                _set_campaign(conn, lease, status="needs_human", stage="reauthorize_google")
            queue.complete(conn, lease)
        return

    known = {r["provider_message_id"] for r in conn.execute(
        "select provider_message_id from messages where organization_id = %s and conversation_id = %s and provider_message_id is not null",
        (lease.organization_id, ctx["conversation_id"])).fetchall()}
    replies = [m for m in poll.messages if m.provider_message_id not in known and m.from_email == ctx["buyer_test_email"]]

    if not replies:
        with queue.fenced(conn, lease):
            if poll_n + 1 < MAX_POLLS:
                _queue(conn, lease, ctx["conversation_id"], "poll_inbox", f"poll:{ctx['conversation_id']}:{lease.task_id}:next",
                       {**lease.payload, "poll": poll_n + 1}, delay_seconds=POLL_SECONDS)
            else:
                _decision(conn, lease, kind="poll_inbox", status="blocked", conversation_id=ctx["conversation_id"],
                          reason="No reply within the polling window; nothing else is sent.")
                _set_conversation(conn, lease, ctx["conversation_id"], state="needs_human")
                _roll_up(conn, lease)
            conn.execute("update conversations set next_poll_at = now() + make_interval(secs => %s) where organization_id = %s and id = %s",
                         (POLL_SECONDS, lease.organization_id, ctx["conversation_id"]))
            queue.complete(conn, lease)
        return

    reply = replies[-1]
    offered = (ctx["crm_json"] or {}).get("offered_slots", [])
    verdict, model_meta = _classify(client, reply.body_text, offered)
    inbound_count = conn.execute("select count(*) as n from messages where organization_id = %s and conversation_id = %s "
                                 "and direction = 'inbound'", (lease.organization_id, ctx["conversation_id"])).fetchone()["n"] + 1
    turns_left = inbound_count <= ctx["limits"].get("max_reply_turns", 4)
    chosen = next((s for s in offered if s["id"] == verdict.get("slot_id")), None) if verdict["intent"] == "picks_slot" else None

    slots: list[dict] = []
    slot_error = None
    offer = turns_left and (verdict["intent"] in ("wants_meeting", "question", "other") or (verdict["intent"] == "picks_slot" and not chosen))
    if offer:
        try:
            slots, slot_error = _free_slots(google, ref, ctx)
        except GoogleAdapterError as exc:
            slot_error = exc.failure.redacted_detail

    booking = None
    booking_error = None
    if chosen and turns_left:
        booking, booking_error = _book(conn, lease, google, ref, ctx, chosen)

    with queue.fenced(conn, lease):
        message_id = conn.execute(
            """
            insert into messages (organization_id, conversation_id, connection_id, direction, provider_message_id, rfc_message_id,
                                  provider_thread_id, in_reply_to, from_email, to_emails, subject, body_text, body_sha256,
                                  received_at, status)
            values (%s, %s, %s, 'inbound', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'received')
            on conflict (connection_id, provider_message_id) do nothing returning id
            """,
            (lease.organization_id, ctx["conversation_id"], ctx["connection_id"], reply.provider_message_id, reply.rfc_message_id,
             reply.provider_thread_id, reply.in_reply_to, reply.from_email, reply.to_emails, reply.subject, reply.body_text,
             _sha(reply.body_text), reply.received_at),
        ).fetchone()
        if model_meta:
            conn.execute(
                "update campaigns set budget_json = jsonb_set(budget_json, '{usage,model_calls}', "
                "to_jsonb(coalesce((budget_json -> 'usage' ->> 'model_calls')::int, 0) + 1)) where organization_id = %s and id = %s",
                (lease.organization_id, lease.campaign_id))
        if offer:
            _usage(conn, lease, "calendar_attempts")
        needs = list((ctx["crm_json"] or {}).get("buyer_stated_needs", []))
        if verdict.get("need") and message_id:
            needs.append({"text": verdict["need"], "message_id": str(message_id["id"])})
        _decision(conn, lease, kind="handle_reply", status="accepted", conversation_id=ctx["conversation_id"], prospect_id=ctx["prospect_id"],
                  reason=f"Reply classified as {verdict['intent']}" + (f" ({verdict['slot_id']})" if verdict.get("slot_id") else "") +
                  f": {verdict.get('reason', '')}"[:400], input_refs={"message_id": str(message_id["id"]) if message_id else None},
                  model=model_meta, proposed=verdict)
        name = _first_name(ctx)
        seller = ctx["snapshot"]["seller"]["name"]

        if verdict["intent"] == "declines":
            _set_conversation(conn, lease, ctx["conversation_id"], state="declined", last_inbound_at=reply.received_at,
                              crm={"stage": "declined", "buyer_stated_needs": needs})
            _queue(conn, lease, ctx["conversation_id"], "send_email", f"email:{ctx['conversation_id']}:goodbye", {"compose": {
                "purpose": "goodbye", "after_state": "declined", "subject": reply.subject or "Thanks",
                "body_text": f"Thanks for letting me know, {name}. I won't follow up again.\n\nBest,\n{seller}"}})
        elif not turns_left:
            _set_conversation(conn, lease, ctx["conversation_id"], state="needs_human", last_inbound_at=reply.received_at)
            _decision(conn, lease, kind="handle_reply", status="blocked", conversation_id=ctx["conversation_id"],
                      reason="Reply-turn limit reached; the founder takes over.")
        elif chosen and booking:
            handoff = _handoff(conn, lease, ctx, booking, needs)
            _set_conversation(conn, lease, ctx["conversation_id"], state="booked", last_inbound_at=reply.received_at,
                              crm={"stage": "booked", "booking": booking, "buyer_stated_needs": needs}, handoff=handoff)
            _queue(conn, lease, ctx["conversation_id"], "send_email", f"email:{ctx['conversation_id']}:confirm", {"compose": {
                "purpose": "confirmation", "after_state": "completed", "subject": reply.subject or "Confirmed",
                "body_text": (f"Great, {name}. You're booked for {chosen['label']}. A calendar invite is on its way"
                              f"{' (' + booking['html_link'] + ')' if booking.get('html_link') else ''}.\n\nTalk soon,\n{seller}")}})
        elif chosen and booking_error:
            _set_conversation(conn, lease, ctx["conversation_id"], state="needs_human", last_inbound_at=reply.received_at)
            _decision(conn, lease, kind="book_meeting", status="blocked", conversation_id=ctx["conversation_id"],
                      reason=f"Booking failed: {booking_error}")
        elif slots:
            lines = "\n".join(f"{i}. {s['label']}" for i, s in enumerate(slots, start=1))
            _set_conversation(conn, lease, ctx["conversation_id"], state="offering_slots", last_inbound_at=reply.received_at,
                              crm={"stage": "offering_slots", "offered_slots": slots, "buyer_stated_needs": needs})
            _queue(conn, lease, ctx["conversation_id"], "send_email", f"email:{ctx['conversation_id']}:slots:{reply.provider_message_id}",
                   {"compose": {"purpose": "slots", "after_state": "waiting_slot_acceptance", "subject": reply.subject or "Times",
                                "body_text": f"Thanks, {name}. Here are a few {ctx['snapshot']['policy'].get('duration_minutes', 15)}-minute "
                                             f"times that work on my side:\n\n{lines}\n\nReply with the number that suits you and I'll "
                                             f"send the invite.\n\nBest,\n{seller}"}})
        else:
            _set_conversation(conn, lease, ctx["conversation_id"], state="needs_human", last_inbound_at=reply.received_at)
            _decision(conn, lease, kind="check_slots", status="blocked", conversation_id=ctx["conversation_id"],
                      reason=f"No free slot could be offered: {slot_error or 'calendar full'}")
        _roll_up(conn, lease)
        queue.complete(conn, lease)


# ---------------------------------------------------------------- booking + handoff


def _book(conn: psycopg.Connection, lease: queue.Lease, google: GoogleAdapter, ref: GoogleConnectionRef,
          ctx: dict, slot: dict) -> tuple[dict | None, str | None]:
    fingerprint = _sha(f"{ctx['conversation_id']}|{slot['start']}|{ctx['buyer_test_email']}")
    event_id = "oc" + fingerprint[:30]
    idem = f"book:{ctx['conversation_id']}:{slot['id']}"
    seller = ctx["snapshot"]["seller"]["name"]
    request = CalendarEventRequest(
        action_id=UUID(int=0), calendar_id=ctx["calendar_id"] or "primary", event_id=event_id, booking_fingerprint=fingerprint,
        summary=f"[Outcome simulation] {seller} intro call"[:200],
        description=f"Booked by the {seller} sales agent after the prospect picked this time by email. Simulation: the attendee is a consented test inbox.",
        start=datetime.fromisoformat(slot["start"]), end=datetime.fromisoformat(slot["end"]), timezone=slot["timezone"],
        attendees=[ctx["buyer_test_email"]] + ([ctx["seller_email"]] if ctx["seller_email"] != ctx["buyer_test_email"] else []),
    )
    payload = request.model_dump(mode="json")
    with queue.fenced(conn, lease):
        decision_id = _decision(conn, lease, kind="book_meeting", status="accepted", conversation_id=ctx["conversation_id"],
                                prospect_id=ctx["prospect_id"], reason=f"Prospect picked {slot['id']} ({slot['label']}); booking it.",
                                checks=[{"name": "slot_was_offered", "pass": True, "reason": "slot is one the agent offered after FreeBusy"}],
                                proposed={"slot": slot})
        action = actions.prepare(conn, organization_id=lease.organization_id, campaign_id=lease.campaign_id,
                                 conversation_id=ctx["conversation_id"], decision_id=decision_id, kind="calendar_insert",
                                 idempotency_key=idem, request_hash=_sha(json.dumps(payload, sort_keys=True)), payload=payload)
    actions.begin_execute(conn, lease, action["id"])
    try:
        receipt = google.calendar_insert(ref, request.model_copy(update={"action_id": action["id"]}))
    except GoogleAdapterError as exc:
        actions.record_result(conn, organization_id=lease.organization_id, action_id=action["id"],
                              state="unknown" if exc.failure.may_have_applied else "failed", provider_ref=None,
                              result=exc.failure.model_dump(mode="json"))
        return None, exc.failure.redacted_detail
    actions.record_result(conn, organization_id=lease.organization_id, action_id=action["id"], state="succeeded",
                          provider_ref=receipt.event_id, result=receipt.model_dump(mode="json"))
    return {"action_id": str(action["id"]), "event_id": receipt.event_id, "calendar_id": receipt.calendar_id,
            "start": receipt.start.isoformat(), "end": receipt.end.isoformat(), "timezone": receipt.timezone,
            "html_link": receipt.html_link, "verified_at": receipt.read_at.isoformat(),
            "attendee_acceptance": "not_verified", "mode": "simulation"}, None


def _handoff(conn: psycopg.Connection, lease: queue.Lease, ctx: dict, booking: dict, needs: list[dict]) -> dict:
    fit = conn.execute("select fit_json from prospects where organization_id = %s and id = %s",
                       (lease.organization_id, ctx["prospect_id"])).fetchone()["fit_json"] or {}
    criteria = fit.get("criteria", [])
    passed = [c for c in criteria if c.get("result") == "pass"]
    owner = conn.execute("select u.email from memberships m join auth.users u on u.id = m.user_id "
                         "where m.organization_id = %s and m.role = 'owner' order by m.created_at limit 1",
                         (lease.organization_id,)).fetchone()
    return {
        "version": 1, "status": "complete", "mode": "simulation", "campaign_id": str(lease.campaign_id),
        "prospect_id": str(ctx["prospect_id"]), "conversation_id": str(ctx["conversation_id"]), "booking": booking,
        "fit_summary": "; ".join(f"{c['name']}: {c.get('reason', '')}" for c in passed)[:900] or "Qualified on the mission criteria.",
        "fit_evidence_ids": sorted({e for c in passed for e in c.get("evidence_ids", [])}),
        "buyer_stated_needs": needs,
        "hypotheses": [h.get("text", "") for h in fit.get("hypotheses", []) if h.get("text")],
        "open_questions": ["Confirm the buyer's current process and timeline on the call."],
        "next_steps": ["Join the call at the booked time.", "Send a short recap after the call."],
        "owner_email": owner["email"] if owner else None,
        "notification_status": "not_requested",
    }
