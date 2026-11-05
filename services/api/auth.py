"""Supabase access-token verification plus server-side membership for the selected organization.

The X-Organization-ID header is a selection, never authorization: membership is always looked up.
"""

from dataclasses import dataclass
from functools import lru_cache
from uuid import UUID

import jwt
from fastapi import Request

from services.core import db
from services.core.config import get_settings
from services.core.contracts.enums import ErrorCode, MembershipRole

from .errors import ApiError

ASYMMETRIC_ALGORITHMS = ("ES256", "RS256")


@dataclass(frozen=True)
class Principal:
    user_id: UUID
    organization_id: UUID
    role: MembershipRole


def _unauthenticated(message: str = "Missing or invalid access token.") -> ApiError:
    return ApiError(401, ErrorCode.UNAUTHENTICATED, message)


@lru_cache
def _jwks_client(url: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(url, cache_keys=True, lifespan=600, timeout=5)


def verify_access_token(token: str) -> dict:
    settings = get_settings()
    if not settings.jwt_issuer:
        raise ApiError(503, ErrorCode.DEPENDENCY_UNAVAILABLE, "Authentication is not configured.", retryable=True)
    try:
        algorithm = jwt.get_unverified_header(token).get("alg")
        if algorithm == "HS256":
            if not settings.supabase_jwt_secret:
                raise _unauthenticated()
            key = settings.supabase_jwt_secret
        elif algorithm in ASYMMETRIC_ALGORITHMS:
            key = _jwks_client(settings.jwks_url).get_signing_key_from_jwt(token).key
        else:
            raise _unauthenticated()
        return jwt.decode(
            token,
            key,
            algorithms=[algorithm],
            audience="authenticated",
            issuer=settings.jwt_issuer,
            options={"require": ["exp", "sub", "iss", "aud"]},
        )
    except jwt.PyJWKClientConnectionError as exc:
        raise ApiError(503, ErrorCode.DEPENDENCY_UNAVAILABLE, "Signing keys unavailable.", retryable=True) from exc
    except jwt.PyJWTError as exc:
        raise _unauthenticated() from exc


def _bearer_token(request: Request) -> str:
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise _unauthenticated()
    return token.strip()


def _organization_header(request: Request) -> UUID:
    raw = request.headers.get("x-organization-id", "").strip()
    try:
        return UUID(raw)
    except ValueError as exc:
        raise ApiError(
            400, ErrorCode.VALIDATION_FAILED, "X-Organization-ID must be a UUID.", details={"field": "X-Organization-ID"}
        ) from exc


def require_member(request: Request) -> Principal:
    claims = verify_access_token(_bearer_token(request))
    try:
        user_id = UUID(claims["sub"])
    except ValueError as exc:
        raise _unauthenticated() from exc
    organization_id = _organization_header(request)
    with db.connection() as conn:
        row = conn.execute(
            "select role from memberships where organization_id = %s and user_id = %s",
            (organization_id, user_id),
        ).fetchone()
    if row is None:
        raise ApiError(403, ErrorCode.FORBIDDEN, "Not a member of the selected organization.")
    return Principal(user_id=user_id, organization_id=organization_id, role=MembershipRole(row["role"]))
