from typing import Any, Literal
from uuid import UUID

from pydantic import Field

from .base import ContractModel, Email
from .enums import CampaignControl, ResolutionType


class Limits(ContractModel):
    """P0 single-conversation ceilings. Raising a bound needs a reviewed contract and quota change."""

    max_discovered: int = Field(ge=1, le=10)
    max_enriched: int = Field(ge=1, le=3)
    max_conversations: int = Field(ge=1, le=1)
    max_outbound_messages: int = Field(ge=1, le=6)
    max_model_calls: int = Field(ge=1, le=20)
    max_research_calls: int = Field(ge=1, le=10)
    max_runtime_seconds: int = Field(ge=1, le=600)
    max_reply_turns: int = Field(ge=1, le=4)
    no_reply_followups: int = Field(ge=0, le=0)


class CampaignCreate(ContractModel):
    request_text: str = Field(min_length=1, max_length=4000)
    mode: Literal["simulation"]
    buyer_test_email: Email
    profile_version: int = Field(ge=1)
    config_version: int = Field(ge=1)
    limits: Limits


class ControlInput(ContractModel):
    action: CampaignControl
    expected_version: int = Field(ge=0)


class ResolveInput(ContractModel):
    expected_conversation_version: int | None = Field(ge=0)
    resolution_type: ResolutionType
    note: str = Field(max_length=4000)
    evidence_ids: list[UUID]
    value: dict[str, Any]
