import os
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse

from services.adapters.google import oauth
from services.core import db
from services.core.contracts.enums import ErrorCode
from services.core.contracts.envelopes import SuccessEnvelope
from services.core.contracts.google_adapter import OAuthStartResult
from services.core.contracts.version import API_PREFIX

from .auth import Principal, require_owner
from .errors import ApiError, correlation_id

router = APIRouter(prefix=API_PREFIX, tags=["google"])


def _web(path: str, **query: str) -> str:
    origin = os.environ.get("WEB_PUBLIC_ORIGIN", "").strip().rstrip("/") or "http://localhost:3100"
    return f"{origin}{path}{'?' + urlencode(query) if query else ''}"


@router.post("/google/oauth/start", response_model=SuccessEnvelope[OAuthStartResult])
def start_oauth(request: Request, principal: Principal = Depends(require_owner)) -> SuccessEnvelope[OAuthStartResult]:
    try:
        with db.transaction() as conn:
            url, expires = oauth.start(conn, organization_id=principal.organization_id, user_id=principal.user_id)
    except oauth.OAuthError as exc:
        raise ApiError(503, ErrorCode.DEPENDENCY_UNAVAILABLE, "Google sign-in isn't configured on this server.") from exc
    return SuccessEnvelope[OAuthStartResult](
        data=OAuthStartResult(authorization_url=url, expires_at=expires), correlation_id=correlation_id(request)
    )


@router.get("/google/callback", include_in_schema=False)
def oauth_callback(code: str | None = None, state: str | None = None, error: str | None = None) -> RedirectResponse:
    if error or not code or not state:
        return RedirectResponse(_web("/setup", google="error", reason=error or "missing_code"), status_code=303)
    try:
        with db.transaction() as conn:
            result = oauth.complete(conn, code=code, state=state)
    except oauth.OAuthError as exc:
        return RedirectResponse(_web("/setup", google="error", reason=exc.reason), status_code=303)
    status = "connected" if result["connected"] else "missing_scopes"
    return RedirectResponse(_web("/setup", google=status), status_code=303)
