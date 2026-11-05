from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, NonNegativeInt

from .base import ContractModel, Email, Reference, Zone
from .enums import (
    ActionState,
    CampaignState,
    ConversationState,
    DecisionStatus,
    EvidenceSourceKind,
    FactStatus,
    MessageDirection,
    MessageStatus,
)


class HealthLive(ContractModel):
    status: Literal["alive"]
    service: Literal["api"]
    contract_version: Literal["outcome.v1"]


class HealthReady(ContractModel):
    """Sanitized readiness summary. Returned as data on 200, and as error.details on 503."""

    status: Literal["ready", "not_ready"]
    database: Literal["ok", "error"]
    worker: Literal["fresh", "stale", "missing", "unknown"]
    last_seen_age_seconds: int | None


class EstimatedCost(ContractModel):
    amount: Decimal = Field(ge=0)
    currency: str = Field(min_length=3, max_length=3)
    pricing_source: str = Field(min_length=1)


class Usage(ContractModel):
    model_calls: NonNegativeInt
    research_calls: NonNegativeInt
    outbound_attempts: NonNegativeInt
    calendar_attempts: NonNegativeInt
    tokens_in: NonNegativeInt
    tokens_out: NonNegativeInt
    estimated_cost: EstimatedCost | None = Field(
        default=None, description="Unknown cost is null, never zero."
    )


class CampaignView(ContractModel):
    id: UUID
    request_text: str
    mode: Literal["simulation"]
    status: CampaignState
    version: int = Field(ge=0)
    stage: str
    profile_version: int = Field(ge=1)
    config_version: int = Field(ge=1)
    usage: Usage
    last_decision_id: UUID | None
    created_at: AwareDatetime
    updated_at: AwareDatetime


class CampaignLaunchView(CampaignView):
    """202 response of POST /campaigns: the campaign plus the queued normalize_mission task."""

    task_id: UUID


class EvidenceView(ContractModel):
    id: UUID
    source_kind: EvidenceSourceKind
    source_url: str | None
    provider_ref: str | None
    field_path: str | None
    excerpt: str
    retrieved_at: AwareDatetime
    source_as_of: AwareDatetime | None
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    fact_status: FactStatus


class ProspectCompany(ContractModel):
    name: str
    domain: str | None


class ProspectPerson(ContractModel):
    name: str
    title: str | None


class ProspectRelationship(ContractModel):
    status: Literal["supported", "unknown", "conflicted"]
    evidence_ids: list[UUID]


class CriterionResult(ContractModel):
    name: str
    result: Literal["pass", "fail", "unknown"]
    evidence_ids: list[UUID]
    reason: str


class ProspectFact(ContractModel):
    text: str
    evidence_ids: list[UUID]


class ProspectHypothesis(ContractModel):
    text: str
    basis_evidence_ids: list[UUID]


class Delivery(ContractModel):
    mode: Literal["simulation"]
    buyer_test_email: Email
    identity_is_simulated: Literal[True]


class ProspectCase(ContractModel):
    id: UUID
    canonical_company_ref: Reference
    canonical_person_ref: Reference | None
    company: ProspectCompany
    person: ProspectPerson | None
    relationship: ProspectRelationship
    criteria: list[CriterionResult]
    fit: Literal["qualified", "rejected", "needs_evidence"]
    facts: list[ProspectFact]
    hypotheses: list[ProspectHypothesis]
    delivery: Delivery


class DecisionModelMeta(ContractModel):
    deployment: str
    model_version: str | None
    prompt_version: str
    usage: dict[str, Any]


class PolicyCheck(ContractModel):
    name: str
    pass_: bool = Field(alias="pass")
    reason: str


class PolicyResult(ContractModel):
    pass_: bool = Field(alias="pass")
    checks: list[PolicyCheck]


class ActualAction(ContractModel):
    action_id: UUID
    state: ActionState
    provider_ref: str | None


class DecisionView(ContractModel):
    id: UUID
    kind: str
    status: DecisionStatus
    reason: str
    evidence_ids: list[UUID]
    input_refs: dict[str, Any]
    model: DecisionModelMeta | None
    policy: PolicyResult
    proposed_action: dict[str, Any] | None
    actual_action: ActualAction | None
    resolution: dict[str, Any] | None
    created_at: AwareDatetime


class MessageView(ContractModel):
    id: UUID
    direction: MessageDirection
    subject: str
    body_text: str
    sent_at: AwareDatetime | None
    received_at: AwareDatetime | None
    provider_message_id: str | None
    status: MessageStatus


class Slot(ContractModel):
    id: str
    start: AwareDatetime
    end: AwareDatetime
    timezone: Zone
    freebusy_checked_at: AwareDatetime


class BookingReceipt(ContractModel):
    action_id: UUID
    event_id: Reference
    calendar_id: Reference
    start: AwareDatetime
    end: AwareDatetime
    timezone: Zone
    html_link: str | None
    verified_at: AwareDatetime
    attendee_acceptance: Literal["not_verified"]
    mode: Literal["simulation"]


class ConversationView(ContractModel):
    id: UUID
    state: ConversationState
    version: int = Field(ge=0)
    buyer_role_label: Literal["simulated buyer"]
    buyer_test_email: Email
    provider_thread_id: str | None
    messages: list[MessageView]
    offered_slots: list[Slot]
    booking: BookingReceipt | None


class BuyerStatedNeed(ContractModel):
    text: str
    message_id: UUID


class Handoff(ContractModel):
    version: Literal[1]
    status: Literal["complete"]
    mode: Literal["simulation"]
    campaign_id: UUID
    prospect_id: UUID
    conversation_id: UUID
    booking: BookingReceipt
    fit_summary: str
    fit_evidence_ids: list[UUID]
    buyer_stated_needs: list[BuyerStatedNeed]
    hypotheses: list[str]
    open_questions: list[str]
    next_steps: list[str]
    owner_email: Email | None
    notification_status: Literal["not_requested", "pending", "sent", "failed"]


class ApprovedProfileView(ContractModel):
    approved_facts: list[dict[str, Any]]
    faq: list[dict[str, Any]]
    forbidden_promises: list[str]


class SafePolicyView(ContractModel):
    simulation: bool
    consented_recipients: list[dict[str, Any]]
    selected_calendar_id: str | None
    working_hours: dict[str, Any] | None
    duration_minutes: int | None
    limits: dict[str, int] | None


class ConnectionSummaryView(ContractModel):
    purpose: Literal["seller", "buyer_test"]
    status: Literal["pending", "connected", "reauth_required", "revoked"]
    account_email: str | None
    granted_scopes: list[str]
    calendar_id: str | None


class OrganizationView(ContractModel):
    id: UUID
    name: str
    website_url: str | None
    timezone: str
    role: Literal["owner", "member"]
    profile_version: int
    approved_at: AwareDatetime | None
    profile: ApprovedProfileView | None
    config_version: int
    policy: SafePolicyView
    connections: list[ConnectionSummaryView]
    worker: HealthReady


class MissionDetail(CampaignView):
    prospects: list[ProspectCase]
    conversation: ConversationView | None
    open_exceptions: list[DecisionView]
    evidence: list[EvidenceView]
    handoff: Handoff | None
