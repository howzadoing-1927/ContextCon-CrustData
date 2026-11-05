from uuid import UUID

from fastapi import Request
from fastapi.responses import JSONResponse

from services.core.contracts.enums import ErrorCode
from services.core.contracts.envelopes import ErrorBody, ErrorEnvelope
from services.core.errors import DomainError as ApiError

__all__ = ["ApiError", "correlation_id", "error_response"]


def correlation_id(request: Request) -> UUID:
    return request.state.correlation_id


def error_response(
    request: Request, status: int, code: ErrorCode, message: str, retryable: bool, details: dict | None = None
) -> JSONResponse:
    envelope = ErrorEnvelope(
        error=ErrorBody(code=code, message=message, retryable=retryable, details=details or {}),
        correlation_id=correlation_id(request),
    )
    return JSONResponse(status_code=status, content=envelope.model_dump(mode="json"))
