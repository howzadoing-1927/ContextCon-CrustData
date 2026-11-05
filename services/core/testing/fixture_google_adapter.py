"""Deterministic, network-free GoogleAdapter for isolated tests. Every result is labeled FIXTURE."""

import hashlib
import os
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime

from services.core.contracts.enums import ConnectionStatus, ExecutionLabel
from services.core.contracts.google_adapter import (
    CalendarEventLookup,
    CalendarEventReceipt,
    CalendarEventRequest,
    ConnectionSummary,
    FailurePhase,
    FreeBusyResult,
    GmailSendReceipt,
    GoogleAdapterError,
    GoogleConnectionRef,
    GoogleFailure,
    GoogleOperation,
    OAuthStart,
    OAuthStartResult,
    OutboundEmail,
    PolledMessage,
    ReconcileResult,
    Retryability,
    ThreadPoll,
)

FixtureMode = Literal["ok", "send_unknown", "rejected", "freebusy_error", "reauth"]

FIXTURE_NOW = datetime(2026, 11, 6, 4, 30, tzinfo=UTC)
LABEL = ExecutionLabel.FIXTURE


def _short_hash(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


class FixtureGoogleAdapter:
    def __init__(self, mode: FixtureMode = "ok", inbox: list[PolledMessage] | None = None) -> None:
        if os.environ.get("LIVE_EFFECTS_ENABLED", "").strip().lower() in {"1", "true", "yes"}:
            raise RuntimeError("FixtureGoogleAdapter must not be constructed while LIVE_EFFECTS_ENABLED is set")
        self.mode = mode
        self._inbox = list(inbox or [])
        self._sent: dict[str, GmailSendReceipt] = {}
        self._events: dict[tuple[str, str], CalendarEventReceipt] = {}

    def _check_auth(self, operation: GoogleOperation) -> None:
        if self.mode == "reauth":
            raise GoogleAdapterError(
                GoogleFailure(
                    operation=operation,
                    phase=FailurePhase.AUTH,
                    retryability=Retryability.REAUTHORIZE,
                    may_have_applied=False,
                    provider_status=401,
                    redacted_detail="fixture: refresh token rejected (invalid_grant)",
                )
            )

    def start_oauth(self, request: OAuthStart) -> OAuthStartResult:
        self._check_auth(GoogleOperation.START_OAUTH)
        return OAuthStartResult(
            authorization_url=f"https://fixture.invalid/oauth?c={request.connection_id}",
            expires_at=FIXTURE_NOW.replace(hour=4, minute=40),
        )

    def complete_oauth(self, connection_id: UUID, code: str, state: str) -> ConnectionSummary:
        self._check_auth(GoogleOperation.COMPLETE_OAUTH)
        return ConnectionSummary(
            connection_id=connection_id,
            status=ConnectionStatus.CONNECTED,
            account_email="seller@example.invalid",
            granted_scopes=[
                "https://www.googleapis.com/auth/gmail.readonly",
                "https://www.googleapis.com/auth/gmail.send",
                "https://www.googleapis.com/auth/calendar.events",
                "https://www.googleapis.com/auth/calendar.freebusy",
            ],
            calendar_id="primary",
        )

    def gmail_send(self, connection: GoogleConnectionRef, message: OutboundEmail) -> GmailSendReceipt:
        self._check_auth(GoogleOperation.GMAIL_SEND)
        if self.mode == "send_unknown":
            raise GoogleAdapterError(
                GoogleFailure(
                    operation=GoogleOperation.GMAIL_SEND,
                    phase=FailurePhase.DISPATCH,
                    retryability=Retryability.RECONCILE_FIRST,
                    may_have_applied=True,
                    provider_status=None,
                    redacted_detail="fixture: connection reset after request body was written",
                )
            )
        if self.mode == "rejected":
            raise GoogleAdapterError(
                GoogleFailure(
                    operation=GoogleOperation.GMAIL_SEND,
                    phase=FailurePhase.RESPONSE,
                    retryability=Retryability.NEVER,
                    may_have_applied=False,
                    explicit_rejection=True,
                    provider_status=400,
                    redacted_detail="fixture: provider rejected message as invalid",
                )
            )
        receipt = GmailSendReceipt(
            provider_message_id=f"fixture-msg-{_short_hash(message.action_key)}",
            provider_thread_id=message.provider_thread_id or f"fixture-thread-{_short_hash(str(message.action_id))}",
            rfc_message_id=message.rfc_message_id,
            sent_at=FIXTURE_NOW,
            execution_label=LABEL,
        )
        self._sent[message.rfc_message_id] = receipt
        return receipt

    def gmail_poll_thread(
        self, connection: GoogleConnectionRef, provider_thread_id: str, after: AwareDatetime | None
    ) -> ThreadPoll:
        self._check_auth(GoogleOperation.GMAIL_POLL_THREAD)
        messages = [
            m
            for m in self._inbox
            if m.provider_thread_id == provider_thread_id and (after is None or m.received_at > after)
        ]
        return ThreadPoll(
            provider_thread_id=provider_thread_id, messages=messages, polled_at=FIXTURE_NOW, execution_label=LABEL
        )

    def gmail_reconcile_send(
        self, connection: GoogleConnectionRef, rfc_message_id: str, provider_thread_id: str | None
    ) -> ReconcileResult:
        self._check_auth(GoogleOperation.GMAIL_RECONCILE_SEND)
        receipt = self._sent.get(rfc_message_id)
        return ReconcileResult(
            status="matched" if receipt else "unresolved",
            receipt=receipt,
            checked_at=FIXTURE_NOW,
            execution_label=LABEL,
        )

    def calendar_freebusy(
        self,
        connection: GoogleConnectionRef,
        calendar_id: str,
        time_min: AwareDatetime,
        time_max: AwareDatetime,
        timezone: str,
    ) -> FreeBusyResult:
        self._check_auth(GoogleOperation.CALENDAR_FREEBUSY)
        if self.mode == "freebusy_error":
            return FreeBusyResult(
                calendar_id=calendar_id,
                time_min=time_min,
                time_max=time_max,
                status="error",
                busy=[],
                error_reasons=["fixture: notFound"],
                checked_at=FIXTURE_NOW,
                execution_label=LABEL,
            )
        return FreeBusyResult(
            calendar_id=calendar_id,
            time_min=time_min,
            time_max=time_max,
            status="ok",
            busy=[],
            error_reasons=[],
            checked_at=FIXTURE_NOW,
            execution_label=LABEL,
        )

    def calendar_insert(self, connection: GoogleConnectionRef, event: CalendarEventRequest) -> CalendarEventReceipt:
        self._check_auth(GoogleOperation.CALENDAR_INSERT)
        if self.mode == "send_unknown":
            raise GoogleAdapterError(
                GoogleFailure(
                    operation=GoogleOperation.CALENDAR_INSERT,
                    phase=FailurePhase.RESPONSE,
                    retryability=Retryability.RECONCILE_FIRST,
                    may_have_applied=True,
                    provider_status=None,
                    redacted_detail="fixture: response timed out after insert dispatch",
                )
            )
        key = (event.calendar_id, event.event_id)
        if key in self._events:
            raise GoogleAdapterError(
                GoogleFailure(
                    operation=GoogleOperation.CALENDAR_INSERT,
                    phase=FailurePhase.RESPONSE,
                    retryability=Retryability.RECONCILE_FIRST,
                    may_have_applied=True,
                    provider_status=409,
                    redacted_detail="fixture: event id already exists; read back and compare fingerprint",
                )
            )
        receipt = CalendarEventReceipt(
            event_id=event.event_id,
            calendar_id=event.calendar_id,
            start=event.start,
            end=event.end,
            timezone=event.timezone,
            attendees=event.attendees,
            booking_fingerprint=event.booking_fingerprint,
            html_link=None,
            status="confirmed",
            read_at=FIXTURE_NOW,
            execution_label=LABEL,
        )
        self._events[key] = receipt
        return receipt

    def calendar_get(self, connection: GoogleConnectionRef, calendar_id: str, event_id: str) -> CalendarEventLookup:
        self._check_auth(GoogleOperation.CALENDAR_GET)
        event = self._events.get((calendar_id, event_id))
        return CalendarEventLookup(found=event is not None, event=event, execution_label=LABEL)
