import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from services.core.contracts import enums
from services.core.contracts.envelopes import SuccessEnvelope
from services.core.contracts.google_adapter import FreeBusyResult, GoogleFailure
from services.core.contracts.requests import CampaignCreate, Limits
from services.core.contracts.views import CampaignLaunchView, CampaignView, HealthLive, MissionDetail, PolicyCheck

FIXTURES = Path(__file__).resolve().parents[2] / "contracts" / "fixtures"

FIXTURE_MODELS = {
    "health_live.json": SuccessEnvelope[HealthLive],
    "campaign_view.running.json": SuccessEnvelope[CampaignView],
    "campaign_view.completed.json": SuccessEnvelope[CampaignView],
    "mission_detail.empty.json": SuccessEnvelope[MissionDetail],
    "campaign_launch.json": SuccessEnvelope[CampaignLaunchView],
    "google_failure.send_unknown.json": GoogleFailure,
    "google_failure.reauth.json": GoogleFailure,
    "google_result.freebusy_error.json": FreeBusyResult,
}

DEFAULT_LIMITS = {
    "max_discovered": 10,
    "max_enriched": 3,
    "max_conversations": 1,
    "max_outbound_messages": 6,
    "max_model_calls": 20,
    "max_research_calls": 10,
    "max_runtime_seconds": 600,
    "max_reply_turns": 4,
    "no_reply_followups": 0,
}


def load_fixture(name: str) -> dict:
    raw = json.loads((FIXTURES / name).read_text())
    assert raw.pop("_fixture") == "FIXTURE"
    return raw


def test_every_fixture_file_is_covered():
    assert {p.name for p in FIXTURES.glob("*.json")} == set(FIXTURE_MODELS)


@pytest.mark.parametrize("name", sorted(FIXTURE_MODELS))
def test_fixture_validates_and_round_trips(name):
    raw = load_fixture(name)
    model = FIXTURE_MODELS[name].model_validate(raw)

    assert model.model_dump(mode="json", by_alias=True) == raw


def test_unknown_field_rejected():
    data = load_fixture("campaign_view.running.json")["data"]
    data["tenant_id"] = "anything"

    with pytest.raises(ValidationError, match="extra"):
        CampaignView.model_validate(data)


def test_invalid_enum_rejected():
    data = load_fixture("campaign_view.running.json")["data"]
    data["status"] = "done"

    with pytest.raises(ValidationError):
        CampaignView.model_validate(data)


def test_naive_timestamp_rejected():
    data = load_fixture("campaign_view.running.json")["data"]
    data["created_at"] = "2026-11-05T18:05:00"

    with pytest.raises(ValidationError):
        CampaignView.model_validate(data)


def test_unknown_cost_is_null_not_zero():
    data = load_fixture("campaign_view.running.json")["data"]

    assert CampaignView.model_validate(data).usage.estimated_cost is None


@pytest.mark.parametrize(
    ("field", "value"),
    [("max_conversations", 2), ("max_discovered", 11), ("max_outbound_messages", 0), ("no_reply_followups", 1)],
)
def test_limits_bounds_enforced(field, value):
    with pytest.raises(ValidationError):
        Limits.model_validate({**DEFAULT_LIMITS, field: value})


def test_campaign_create_accepts_doc_example():
    create = CampaignCreate.model_validate(
        {
            "request_text": "Find a relevant B2B company and book a 15-minute demo.",
            "mode": "simulation",
            "buyer_test_email": "Consenting.Buyer+test@Example.INVALID",
            "profile_version": 1,
            "config_version": 1,
            "limits": DEFAULT_LIMITS,
        }
    )

    assert create.buyer_test_email == "Consenting.Buyer+test@example.invalid"


@pytest.mark.parametrize(
    "email",
    ["a@b.co\r\nBcc: x@y.co", "Name <a@b.co>", "a@b.co, c@d.co", "no-at-sign", "a@localhost"],
)
def test_email_rejects_header_and_list_syntax(email):
    with pytest.raises(ValidationError):
        CampaignCreate.model_validate(
            {
                "request_text": "x",
                "mode": "simulation",
                "buyer_test_email": email,
                "profile_version": 1,
                "config_version": 1,
                "limits": DEFAULT_LIMITS,
            }
        )


def test_mode_other_than_simulation_rejected():
    with pytest.raises(ValidationError):
        CampaignCreate.model_validate(
            {
                "request_text": "x",
                "mode": "live",
                "buyer_test_email": "a@b.co",
                "profile_version": 1,
                "config_version": 1,
                "limits": DEFAULT_LIMITS,
            }
        )


def test_policy_pass_serializes_under_contract_name():
    check = PolicyCheck.model_validate({"name": "recipient_allowlist", "pass": True, "reason": "exact match"})

    assert check.model_dump(by_alias=True) == {"name": "recipient_allowlist", "pass": True, "reason": "exact match"}


def values(enum_cls) -> set[str]:
    return {member.value for member in enum_cls}


def test_state_enums_match_doc_02():
    assert values(enums.CampaignState) == {
        "draft", "running", "waiting_reply", "completed", "no_match", "needs_human", "paused", "stopped", "failed",
    }
    assert values(enums.ConversationState) == {
        "researching", "qualified", "drafting", "waiting_reply", "evaluating_reply", "offering_slots",
        "waiting_slot_acceptance", "booking", "booked", "completed",
        "declined", "suppressed", "needs_human", "send_unknown", "stopped",
    }
    assert values(enums.TaskKind) == {
        "normalize_mission", "research", "qualify_and_draft", "send_email", "poll_inbox", "handle_reply",
        "check_slots", "book_meeting", "write_handoff", "notify_owner", "reconcile_action",
    }
    assert values(enums.TaskStatus) == {"ready", "leased", "succeeded", "failed", "cancelled"}
    assert values(enums.ActionKind) == {"email_send", "calendar_insert", "owner_notify"}
    assert values(enums.ActionState) == {"prepared", "executing", "succeeded", "failed", "unknown", "cancelled"}
    assert values(enums.DecisionStatus) == {"accepted", "rejected", "blocked", "resolved"}
    assert values(enums.FactStatus) == {"observed", "operator_approved", "hypothesis", "conflicted"}
    assert values(enums.ConnectionStatus) == {"pending", "connected", "reauth_required", "revoked"}
    assert values(enums.ExecutionLabel) == {"LIVE", "CACHED", "FIXTURE", "SIMULATED_BUYER"}
