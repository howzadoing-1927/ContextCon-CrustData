"""Model-output contracts (doc 03). Models propose these; code validates them and decides."""

from typing import Annotated, Literal

from pydantic import Field

from .base import ContractModel

Item = Annotated[str, Field(min_length=1, max_length=300)]
Scalar = str | int | float | bool


class CompanyRule(ContractModel):
    field: Item
    operator: Literal["equals", "contains", "range"]
    value: Scalar | list[Scalar]
    must_have: bool


class Assumption(ContractModel):
    text: Item
    status: Literal["hypothesis"]


class ResearchQuery(ContractModel):
    intent: Item
    limit: int = Field(ge=1, le=10)


class NormalizedPlan(ContractModel):
    objective: Literal["book_demo"]
    geography: list[Item] = Field(max_length=20)
    industries: list[Item] = Field(max_length=20)
    company_rules: list[CompanyRule] = Field(max_length=20)
    buyer_roles: list[Item] = Field(max_length=20)
    exclusions: list[Item] = Field(max_length=20)
    missing_required_fields: list[Item] = Field(max_length=20)
    assumptions: list[Assumption] = Field(max_length=20)
    research_queries: list[ResearchQuery] = Field(max_length=10)
    stop_conditions: list[Item] = Field(max_length=20)
