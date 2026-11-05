import re
from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AfterValidator, BaseModel, ConfigDict, StringConstraints


class ContractModel(BaseModel):
    """Base for every outcome.v1 payload: unknown fields and invalid enum values are rejected."""

    model_config = ConfigDict(extra="forbid", frozen=True, use_enum_values=False)


def _valid_zone(value: str) -> str:
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"not a valid IANA zone: {value!r}") from exc
    return value


_LOCAL_PART = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+$")
_DOMAIN = re.compile(r"^(?=.{1,253}$)([A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}$")


def _normalize_email(value: str) -> str:
    """One bare mailbox; trims and lowercases the domain only. Dots and plus-tags are preserved."""
    value = value.strip()
    if any(ch in value for ch in "\r\n<>,;\"() \t"):
        raise ValueError("email must be a single bare mailbox")
    local, sep, domain = value.rpartition("@")
    if not sep or not _LOCAL_PART.match(local) or len(local) > 64 or not _DOMAIN.match(domain):
        raise ValueError("invalid email address")
    return f"{local}@{domain.lower()}"


Zone = Annotated[str, AfterValidator(_valid_zone)]
Reference = Annotated[str, StringConstraints(min_length=1)]
Email = Annotated[str, AfterValidator(_normalize_email)]
