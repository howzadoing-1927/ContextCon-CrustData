from typing import Any

from .contracts.enums import ErrorCode


class DomainError(Exception):
    """A typed rejection that the API renders as an outcome.v1 ErrorEnvelope."""

    def __init__(
        self,
        status: int,
        code: ErrorCode,
        message: str,
        *,
        retryable: bool = False,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.retryable = retryable
        self.details = details or {}
