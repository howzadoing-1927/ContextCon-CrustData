from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from pydantic import ValidationError

from services.core.contracts.enums import ExecutionLabel
from services.core.contracts.google_adapter import (
    CalendarEventRequest,
    FailurePhase,
    GoogleAdapter,
    GoogleAdapterError,
    GoogleConnectionRef,
    GoogleFailure,
    GoogleOperation,
    OutboundEmail,
    Retryability,
)
from services.core.testing.fixture_google_adapter import FixtureGoogleAdapter

CONNECTION = GoogleConnectionRef(
    organization_id=UUID("11111111-1111-4111-8111-111111111111"),
    connection_id=UUID("22222222-2222-4222-8222-222222222222"),
    account_email="seller@example.invalid",
)
START = datetime(2026, 11, 6, 5, 0, tzinfo=UTC)


def failure(**overrides) -> dict:
    base = {
        "operation": "gmail.send",
        "phase": "dispatch",
        "retryability": "reconcile_first",
        "may_have_applied": True,
        "provider_status": None,
        "redacted_detail": "x",
    }
    return {**base, **overrides}


def outbound(**overrides) -> OutboundEmail:
    base = {
        "action_id": UUID("33333333-3333-4333-8333-333333333333"),
        "action_key": "email:conv:initial:initial",
        "request_hash": "a" * 64,
        "rfc_message_id": "<b1-fixture@outcome.invalid>",
        "from_email": "seller@example.invalid",
        "to_email": "buyer@example.invalid",
        "subject": "Quick question",
        "body_text": "Hello",
        "provider_thread_id": None,
        "in_reply_to": None,
        "references": [],
    }
    return OutboundEmail.model_validate({**base, **overrides})


def event(**overrides) -> CalendarEventRequest:
    base = {
        "action_id": UUID("44444444-4444-4444-8444-444444444444"),
        "calendar_id": "primary",
        "event_id": "0123456789abcdef0123456789abcdef",
        "booking_fingerprint": "b" * 64,
        "summary": "[Outcome simulation] Demo",
        "description": "Simulated booking",
        "start": START,
        "end": START + timedelta(minutes=15),
        "timezone": "Asia/Kolkata",
        "attendees": ["buyer@example.invalid"],
    }
    return CalendarEventRequest.model_validate({**base, **overrides})


def test_valid_unknown_send_failure():
    assert GoogleFailure.model_validate(failure()).may_have_applied is True


@pytest.mark.parametrize(
    "overrides",
    [
        {"retryability": "safe_retry"},
        {"may_have_applied": False},
        {"phase": "auth", "may_have_applied": True, "retryability": "reauthorize"},
        {"explicit_rejection": True},
        {"redacted_detail": "x" * 501},
        {"provider_status": 42},
    ],
)
def test_failure_invariants_reject_unsafe_combinations(overrides):
    with pytest.raises(ValidationError):
        GoogleFailure.model_validate(failure(**overrides))


def test_explicit_rejection_may_be_not_applied():
    parsed = GoogleFailure.model_validate(
        failure(phase="response", may_have_applied=False, explicit_rejection=True, retryability="never", provider_status=400)
    )

    assert parsed.may_have_applied is False


def test_read_only_operation_dispatch_failure_can_be_safe_retry():
    parsed = GoogleFailure.model_validate(
        failure(operation="calendar.freebusy", may_have_applied=False, retryability="safe_retry", provider_status=503)
    )

    assert parsed.retryability is Retryability.SAFE_RETRY


@pytest.mark.parametrize(
    "overrides",
    [{"subject": "Hi\r\nBcc: x@y.co"}, {"to_email": "a@b.co, c@d.co"}, {"cc": ["c@d.co"]}, {"reply_to": "x@y.co"}],
)
def test_outbound_email_blocks_header_injection_and_extra_recipients(overrides):
    with pytest.raises(ValidationError):
        outbound(**overrides)


@pytest.mark.parametrize(
    "overrides",
    [{"summary": "Demo"}, {"event_id": "UPPERCASE123"}, {"attendees": []}, {"attendees": ["a@b.co", "c@d.co", "e@f.co"]}],
)
def test_calendar_event_request_constraints(overrides):
    with pytest.raises(ValidationError):
        event(**overrides)


def test_fixture_adapter_satisfies_protocol():
    assert isinstance(FixtureGoogleAdapter(), GoogleAdapter)


def test_fixture_ok_mode_send_reconcile_and_booking_read_back():
    adapter = FixtureGoogleAdapter("ok")

    receipt = adapter.gmail_send(CONNECTION, outbound())
    reconciled = adapter.gmail_reconcile_send(CONNECTION, receipt.rfc_message_id, receipt.provider_thread_id)
    inserted = adapter.calendar_insert(CONNECTION, event())
    lookup = adapter.calendar_get(CONNECTION, "primary", inserted.event_id)

    assert receipt.execution_label is ExecutionLabel.FIXTURE
    assert reconciled.status == "matched" and reconciled.receipt == receipt
    assert lookup.found and lookup.event == inserted
    assert lookup.event.booking_fingerprint == "b" * 64


def test_fixture_repeated_insert_reports_conflict_not_duplicate():
    adapter = FixtureGoogleAdapter("ok")
    adapter.calendar_insert(CONNECTION, event())

    with pytest.raises(GoogleAdapterError) as exc:
        adapter.calendar_insert(CONNECTION, event())

    assert exc.value.failure.provider_status == 409
    assert exc.value.failure.retryability is Retryability.RECONCILE_FIRST


def test_fixture_send_unknown_is_ambiguous_and_unreconciled():
    adapter = FixtureGoogleAdapter("send_unknown")

    with pytest.raises(GoogleAdapterError) as exc:
        adapter.gmail_send(CONNECTION, outbound())
    reconciled = adapter.gmail_reconcile_send(CONNECTION, "<b1-fixture@outcome.invalid>", None)

    assert exc.value.failure.may_have_applied is True
    assert exc.value.failure.phase is FailurePhase.DISPATCH
    assert reconciled.status == "unresolved" and reconciled.receipt is None


def test_fixture_rejected_mode_is_explicit_rejection():
    with pytest.raises(GoogleAdapterError) as exc:
        FixtureGoogleAdapter("rejected").gmail_send(CONNECTION, outbound())

    assert exc.value.failure.explicit_rejection is True
    assert exc.value.failure.may_have_applied is False


def test_fixture_freebusy_error_is_not_free():
    result = FixtureGoogleAdapter("freebusy_error").calendar_freebusy(
        CONNECTION, "primary", START, START + timedelta(hours=8), "Asia/Kolkata"
    )

    assert result.status == "error" and result.error_reasons and result.busy == []


def test_fixture_reauth_mode():
    with pytest.raises(GoogleAdapterError) as exc:
        FixtureGoogleAdapter("reauth").calendar_freebusy(
            CONNECTION, "primary", START, START + timedelta(hours=8), "Asia/Kolkata"
        )

    assert exc.value.failure.operation is GoogleOperation.CALENDAR_FREEBUSY
    assert exc.value.failure.retryability is Retryability.REAUTHORIZE


def test_fixture_refuses_live_effects(monkeypatch):
    monkeypatch.setenv("LIVE_EFFECTS_ENABLED", "true")

    with pytest.raises(RuntimeError):
        FixtureGoogleAdapter()
