import time
from uuid import UUID

import jwt
from fastapi import APIRouter, Request

from services.core import db
from services.core.config import get_settings
from services.core.contracts.enums import ErrorCode
from services.core.contracts.envelopes import SuccessEnvelope
from services.core.contracts.version import API_PREFIX
from services.core.contracts.views import DemoSessionView

from .errors import ApiError, correlation_id

router = APIRouter(prefix=API_PREFIX, tags=["demo"])


@router.post("/demo/session", response_model=SuccessEnvelope[DemoSessionView])
def create_demo_session(request: Request) -> SuccessEnvelope[DemoSessionView]:
    settings = get_settings()
    if not settings.demo_session_enabled:
        raise ApiError(404, ErrorCode.NOT_FOUND, "Demo session is not enabled.")
    if settings.demo_organization_id is None:
        raise ApiError(503, ErrorCode.DEPENDENCY_UNAVAILABLE, "DEMO_ORGANIZATION_ID is not configured.", retryable=True)
    if not settings.supabase_jwt_secret or not settings.jwt_issuer:
        raise ApiError(503, ErrorCode.DEPENDENCY_UNAVAILABLE, "Authentication is not configured.", retryable=True)

    with db.connection() as conn:
        row = conn.execute(
            """
            select o.id, o.name, m.user_id, m.role
            from organizations o
            join memberships m on m.organization_id = o.id and m.role = 'owner'
            where o.id = %s
            order by m.created_at, m.user_id
            limit 1
            """,
            (settings.demo_organization_id,),
        ).fetchone()
    if row is None:
        raise ApiError(503, ErrorCode.DEPENDENCY_UNAVAILABLE, "Demo workspace is not seeded.", retryable=True)

    now = int(time.time())
    expires_in = max(60, settings.demo_session_ttl_seconds)
    token = jwt.encode(
        {
            "sub": str(row["user_id"]),
            "aud": "authenticated",
            "role": "authenticated",
            "iss": settings.jwt_issuer,
            "iat": now,
            "exp": now + expires_in,
            "outcome_session_kind": "demo",
        },
        settings.supabase_jwt_secret,
        algorithm="HS256",
    )
    return SuccessEnvelope[DemoSessionView](
        data=DemoSessionView(
            access_token=token,
            expires_in=expires_in,
            organization_id=UUID(str(row["id"])),
            organization_name=row["name"],
            role=row["role"],
        ),
        correlation_id=correlation_id(request),
    )
