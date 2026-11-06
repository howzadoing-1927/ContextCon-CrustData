import re
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, field_validator, model_validator

from .base import ContractModel, Email, Zone
from .enums import CampaignControl, ResolutionType

_CLOCK = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
ShortText = Annotated[str, Field(min_length=1, max_length=1000)]


MAX_PEOPLE = 25
DEFAULT_PEOPLE = 10
MAX_BUYER_INBOXES = 5


class Limits(ContractModel):
    """Per-mission ceilings. `max_conversations` is the number of people reached; outbound messages and reply turns
    are per conversation. Raising a bound needs a reviewed contract and quota change."""

    max_discovered: int = Field(ge=1, le=50)
    max_enriched: int = Field(ge=1, le=MAX_PEOPLE)
    max_conversations: int = Field(ge=1, le=MAX_PEOPLE)
    max_outbound_messages: int = Field(ge=1, le=6)
    max_model_calls: int = Field(ge=1, le=150)
    max_research_calls: int = Field(ge=1, le=80)
    max_runtime_seconds: int = Field(ge=1, le=1800)
    max_reply_turns: int = Field(ge=1, le=4)
    no_reply_followups: int = Field(ge=0, le=0)


def limits_for(people: int) -> dict[str, int]:
    """Budgets that let a mission reach `people` prospects. Mirrored by `limitsFor` in apps/web/src/lib/contracts."""
    n = max(1, min(MAX_PEOPLE, people))
    return {
        "max_discovered": min(50, max(10, 2 * n)),
        "max_enriched": n,
        "max_conversations": n,
        "max_outbound_messages": 6,
        "max_model_calls": min(150, 5 * n + 10),
        "max_research_calls": min(80, 3 * n + 5),
        "max_runtime_seconds": min(1800, 60 * n + 300),
        "max_reply_turns": 4,
        "no_reply_followups": 0,
    }


class CampaignCreate(ContractModel):
    request_text: str = Field(min_length=1, max_length=4000)
    mode: Literal["simulation"]
    buyer_test_email: Email
    profile_version: int = Field(ge=1)
    config_version: int = Field(ge=1)
    limits: Limits


class WebsiteSource(ContractModel):
    kind: Literal["website"]
    url: str = Field(min_length=8, max_length=2048)


class PastedTextSource(ContractModel):
    kind: Literal["pasted_text"]
    title: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=20_000)


SourceInput = Annotated[WebsiteSource | PastedTextSource, Field(discriminator="kind")]


class ApprovedFact(ContractModel):
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,40}$")
    text: ShortText
    evidence_ids: list[UUID] = Field(min_length=1)
    authority: Literal["operator_approved"]
    approved: Literal[True]


class FAQ(ContractModel):
    question: ShortText
    answer: ShortText
    fact_ids: list[str]


class ProfileUpdate(ContractModel):
    expected_profile_version: int = Field(ge=0)
    approval_key: str = Field(pattern=r"^[\x21-\x7e]{1,128}$")
    name: str = Field(min_length=1, max_length=200)
    website_url: str = Field(pattern=r"^https://", max_length=2048)
    timezone: Zone
    approved_facts: list[ApprovedFact] = Field(min_length=1, max_length=50)
    faq: list[FAQ] = Field(max_length=50)
    forbidden_promises: list[ShortText] = Field(max_length=50)

    @model_validator(mode="after")
    def _fact_ids_consistent(self) -> "ProfileUpdate":
        ids = [fact.id for fact in self.approved_facts]
        if len(ids) != len(set(ids)):
            raise ValueError("approved fact ids must be unique")
        unknown = sorted({fid for item in self.faq for fid in item.fact_ids} - set(ids))
        if unknown:
            raise ValueError(f"faq references unknown fact ids: {unknown}")
        return self


class ConsentedRecipient(ContractModel):
    email: Email
    role: Literal["buyer_test", "owner_test"]
    consent_record: str = Field(min_length=3, max_length=500)
    consented_at: AwareDatetime


class WorkingHours(ContractModel):
    timezone: Zone
    weekdays: list[int] = Field(min_length=1, max_length=7)
    start: str
    end: str

    @field_validator("weekdays")
    @classmethod
    def _weekdays(cls, value: list[int]) -> list[int]:
        if any(d < 1 or d > 7 for d in value) or len(set(value)) != len(value):
            raise ValueError("weekdays must be unique ISO weekdays 1-7")
        return sorted(value)

    @model_validator(mode="after")
    def _clock(self) -> "WorkingHours":
        if not (_CLOCK.match(self.start) and _CLOCK.match(self.end)) or self.start >= self.end:
            raise ValueError("start/end must be HH:MM with start before end")
        return self


class PolicyUpdate(ContractModel):
    expected_config_version: int = Field(ge=0)
    simulation: Literal[True]
    consented_recipients: list[ConsentedRecipient] = Field(min_length=1, max_length=MAX_BUYER_INBOXES + 1)
    selected_calendar_id: str = Field(min_length=1, max_length=300)
    working_hours: WorkingHours
    duration_minutes: Literal[15]
    limits: Limits

    @model_validator(mode="after")
    def _p0_recipients(self) -> "PolicyUpdate":
        roles = [r.role for r in self.consented_recipients]
        if not 1 <= roles.count("buyer_test") <= MAX_BUYER_INBOXES or roles.count("owner_test") > 1:
            raise ValueError(f"requires 1 to {MAX_BUYER_INBOXES} buyer_test inboxes and at most one owner_test recipient")
        if len({r.email for r in self.consented_recipients}) != len(self.consented_recipients):
            raise ValueError("recipient emails must be distinct")
        return self


class ControlInput(ContractModel):
    action: CampaignControl
    expected_version: int = Field(ge=0)


class ResolveInput(ContractModel):
    expected_conversation_version: int | None = Field(ge=0)
    resolution_type: ResolutionType
    note: str = Field(max_length=4000)
    evidence_ids: list[UUID]
    value: dict[str, Any]
