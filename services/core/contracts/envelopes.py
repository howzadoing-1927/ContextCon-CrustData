from typing import Any, Literal
from uuid import UUID

from pydantic import Field

from .base import ContractModel
from .enums import ErrorCode


class SuccessEnvelope[T](ContractModel):
    schema_version: Literal["outcome.v1"] = "outcome.v1"
    data: T
    correlation_id: UUID


class ListData[T](ContractModel):
    items: list[T]
    next_cursor: str | None


class ErrorBody(ContractModel):
    code: ErrorCode
    message: str
    retryable: bool
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorEnvelope(ContractModel):
    schema_version: Literal["outcome.v1"] = "outcome.v1"
    error: ErrorBody
    correlation_id: UUID
