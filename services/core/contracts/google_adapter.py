"""Shared Google adapter protocol (outcome.v1).

D2 implements `GoogleAdapter` in services/adapters/google. D1's worker decides workflow from the
typed results and from `GoogleFailure`; it never inspects raw provider payloads or retries an
effect whose failure says it may have applied.
"""

from enum import StrEnum
from typing import Annotated, Literal, Protocol, runtime_checkable
from uuid import UUID

from pydantic import AfterValidator, AwareDatetime, Field, model_validator

from .base import ContractModel, Email, Reference, Zone
from .enums import ConnectionPurpose, ConnectionStatus, ExecutionLabel


class GoogleOperation(StrEnum):
    START_OAUTH = "google.start_oauth"
    COMPLETE_OAUTH = "google.complete_oauth"
    GMAIL_SEND = "gmail.send"
    GMAIL_POLL_THREAD = "gmail.poll_thread"
    GMAIL_RECONCILE_SEND = "gmail.reconcile_send"
    CALENDAR_FREEBUSY = "calendar.freebusy"
    CALENDAR_INSERT = "calendar.insert"
    CALENDAR_GET = "calendar.get"


EFFECT_OPERATIONS = frozenset({GoogleOperation.GMAIL_SEND, GoogleOperation.CALENDAR_INSERT})


class FailurePhase(StrEnum):
    PREFLIGHT = "preflight"
    AUTH = "auth"
    REQUEST_BUILD = "request_build"
    DISPATCH = "dispatch"
    RESPONSE = "response"
    READ_BACK = "read_back"


PRE_DISPATCH_PHASES = frozenset({FailurePhase.PREFLIGHT, FailurePhase.AUTH, FailurePhase.REQUEST_BUILD})


class Retryability(StrEnum):
    SAFE_RETRY = "safe_retry"
    RECONCILE_FIRST = "reconcile_first"
    REAUTHORIZE = "reauthorize"
    NEVER = "never"


class GoogleFailure(ContractModel):
    operation: GoogleOperation
    phase: FailurePhase
    retryability: Retryability
    may_have_applied: bool
    explicit_rejection: bool = Field(
        default=False,
        description="True only when a documented adapter classifier proves the provider rejected the request before accepting it.",
    )
    provider_status: int | None = Field(ge=100, le=599)
    redacted_detail: str = Field(max_length=500)

    @model_validator(mode="after")
    def _ambiguity_invariants(self) -> "GoogleFailure":
        if self.may_have_applied and self.retryability is Retryability.SAFE_RETRY:
            raise ValueError("a failure that may have applied cannot be safe_retry")
        if self.explicit_rejection and self.may_have_applied:
            raise ValueError("an explicit rejection cannot also have possibly applied")
        if self.phase in PRE_DISPATCH_PHASES and self.may_have_applied:
            raise ValueError(f"phase {self.phase} happens before dispatch and cannot have applied")
        if (
            self.operation in EFFECT_OPERATIONS
            and self.phase in (FailurePhase.DISPATCH, FailurePhase.RESPONSE)
            and not self.explicit_rejection
            and not self.may_have_applied
        ):
            raise ValueError("an unclassified dispatch/response failure of an effect must set may_have_applied")
        return self


class GoogleAdapterError(Exception):
    def __init__(self, failure: GoogleFailure) -> None:
        super().__init__(f"{failure.operation} failed in {failure.phase}: {failure.redacted_detail}")
        self.failure = failure


def _single_line(value: str) -> str:
    if "\r" in value or "\n" in value:
        raise ValueError("header values must not contain CR or LF")
    return value


HeaderText = Annotated[str, AfterValidator(_single_line), Field(max_length=200)]
EventId = Annotated[str, Field(pattern=r"^[a-v0-9]{5,1024}$")]


class GoogleConnectionRef(ContractModel):
    """Server-selected connection. Adapters load and refresh tokens themselves; tokens never cross this boundary."""

    organization_id: UUID
    connection_id: UUID
    account_email: Email


class OAuthStart(ContractModel):
    organization_id: UUID
    connection_id: UUID
    initiator_user_id: UUID
    purpose: Literal[ConnectionPurpose.SELLER]
    return_path: Literal["/setup"]


class OAuthStartResult(ContractModel):
    authorization_url: str
    expires_at: AwareDatetime


class ConnectionSummary(ContractModel):
    connection_id: UUID
    status: ConnectionStatus
    account_email: Email | None
    granted_scopes: list[str]
    calendar_id: str | None


class OutboundEmail(ContractModel):
    """Immutable plain-text message built by the server. Exactly one recipient; no Cc/Bcc/Reply-To."""

    action_id: UUID
    action_key: Reference
    request_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    rfc_message_id: HeaderText
    from_email: Email
    to_email: Email
    subject: HeaderText
    body_text: str = Field(min_length=1, max_length=4000)
    provider_thread_id: str | None
    in_reply_to: HeaderText | None
    references: list[HeaderText]


class GmailSendReceipt(ContractModel):
    provider_message_id: Reference
    provider_thread_id: Reference
    rfc_message_id: HeaderText
    sent_at: AwareDatetime
    execution_label: ExecutionLabel


class PolledMessage(ContractModel):
    provider_message_id: Reference
    provider_thread_id: Reference
    rfc_message_id: str | None
    in_reply_to: str | None
    from_email: Email
    to_emails: list[Email]
    subject: str
    body_text: str
    received_at: AwareDatetime


class ThreadPoll(ContractModel):
    provider_thread_id: Reference
    messages: list[PolledMessage]
    polled_at: AwareDatetime
    execution_label: ExecutionLabel


class ReconcileResult(ContractModel):
    """`unresolved` is inconclusive (indexing lag), never proof that nothing was sent."""

    status: Literal["matched", "unresolved"]
    receipt: GmailSendReceipt | None
    checked_at: AwareDatetime
    execution_label: ExecutionLabel

    @model_validator(mode="after")
    def _receipt_iff_matched(self) -> "ReconcileResult":
        if (self.status == "matched") != (self.receipt is not None):
            raise ValueError("receipt is required when matched and forbidden when unresolved")
        return self


class BusyRange(ContractModel):
    start: AwareDatetime
    end: AwareDatetime


class FreeBusyResult(ContractModel):
    """An `error` result means unavailable. An `ok` result with no busy ranges is the only free signal."""

    calendar_id: Reference
    time_min: AwareDatetime
    time_max: AwareDatetime
    status: Literal["ok", "error"]
    busy: list[BusyRange]
    error_reasons: list[str]
    checked_at: AwareDatetime
    execution_label: ExecutionLabel

    @model_validator(mode="after")
    def _error_is_explicit(self) -> "FreeBusyResult":
        if self.status == "error" and (not self.error_reasons or self.busy):
            raise ValueError("error results need reasons and no busy ranges")
        if self.status == "ok" and self.error_reasons:
            raise ValueError("ok results cannot carry calendar errors")
        return self


class CalendarEventRequest(ContractModel):
    action_id: UUID
    calendar_id: Reference
    event_id: EventId
    booking_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    summary: HeaderText = Field(pattern=r"^\[Outcome simulation\] ")
    description: str = Field(max_length=4000)
    start: AwareDatetime
    end: AwareDatetime
    timezone: Zone
    attendees: list[Email] = Field(min_length=1, max_length=2)


class CalendarEventReceipt(ContractModel):
    event_id: EventId
    calendar_id: Reference
    start: AwareDatetime
    end: AwareDatetime
    timezone: Zone
    attendees: list[Email]
    booking_fingerprint: str | None
    html_link: str | None
    status: str
    read_at: AwareDatetime
    execution_label: ExecutionLabel


class CalendarEventLookup(ContractModel):
    found: bool
    event: CalendarEventReceipt | None
    execution_label: ExecutionLabel

    @model_validator(mode="after")
    def _event_iff_found(self) -> "CalendarEventLookup":
        if self.found != (self.event is not None):
            raise ValueError("event is required when found and forbidden otherwise")
        return self


@runtime_checkable
class GoogleAdapter(Protocol):
    """Every method returns its typed result or raises GoogleAdapterError; nothing else escapes."""

    def start_oauth(self, request: OAuthStart) -> OAuthStartResult: ...

    def complete_oauth(self, connection_id: UUID, code: str, state: str) -> ConnectionSummary: ...

    def gmail_send(self, connection: GoogleConnectionRef, message: OutboundEmail) -> GmailSendReceipt: ...

    def gmail_poll_thread(
        self, connection: GoogleConnectionRef, provider_thread_id: str, after: AwareDatetime | None
    ) -> ThreadPoll: ...

    def gmail_reconcile_send(
        self, connection: GoogleConnectionRef, rfc_message_id: str, provider_thread_id: str | None
    ) -> ReconcileResult: ...

    def calendar_freebusy(
        self,
        connection: GoogleConnectionRef,
        calendar_id: str,
        time_min: AwareDatetime,
        time_max: AwareDatetime,
        timezone: str,
    ) -> FreeBusyResult: ...

    def calendar_insert(self, connection: GoogleConnectionRef, event: CalendarEventRequest) -> CalendarEventReceipt: ...

    def calendar_get(self, connection: GoogleConnectionRef, calendar_id: str, event_id: str) -> CalendarEventLookup: ...
