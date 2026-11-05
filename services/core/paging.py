"""Opaque (created_at, id) cursors for oldest-first and newest-first lists."""

import base64
import json
from datetime import datetime
from uuid import UUID

from .contracts.enums import ErrorCode
from .errors import DomainError


def encode_cursor(created_at: datetime, row_id: UUID) -> str:
    payload = json.dumps({"t": created_at.isoformat(), "id": str(row_id)}, separators=(",", ":"))
    return base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded.encode()))
        return datetime.fromisoformat(data["t"]), UUID(data["id"])
    except (ValueError, KeyError, json.JSONDecodeError, TypeError) as exc:
        raise DomainError(
            400, ErrorCode.VALIDATION_FAILED, "cursor is not a valid page token.", details={"field": "cursor"}
        ) from exc
