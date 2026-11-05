from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from services.core import db
from services.core.contracts.envelopes import SuccessEnvelope
from services.core.contracts.requests import BriefSave, PolicyUpdate, ProfileUpdate, SourceInput
from services.core.contracts.version import API_PREFIX
from services.core.contracts.views import EvidenceView, OrganizationView
from services.core.workspace import ingest_source, save_brief, update_policy, update_profile, workspace_view

from .auth import Principal, require_member, require_owner
from .campaigns import idempotency_key
from .errors import correlation_id
from .health import readiness

router = APIRouter(prefix=API_PREFIX, tags=["workspace"])


def _view(request: Request, principal: Principal) -> SuccessEnvelope[OrganizationView]:
    worker = readiness()
    with db.connection() as conn:
        view = workspace_view(conn, organization_id=principal.organization_id, role=principal.role.value, worker=worker)
    return SuccessEnvelope[OrganizationView](data=view, correlation_id=correlation_id(request))


@router.get("/workspace", response_model=SuccessEnvelope[OrganizationView])
def get_workspace(request: Request, principal: Principal = Depends(require_member)) -> SuccessEnvelope[OrganizationView]:
    return _view(request, principal)


@router.put("/workspace/profile", response_model=SuccessEnvelope[OrganizationView])
def put_profile(
    request: Request, body: ProfileUpdate, principal: Principal = Depends(require_owner)
) -> SuccessEnvelope[OrganizationView]:
    with db.transaction() as conn:
        update_profile(conn, organization_id=principal.organization_id, user_id=principal.user_id, update=body)
    return _view(request, principal)


@router.put("/workspace/brief", response_model=SuccessEnvelope[OrganizationView])
def put_brief(
    request: Request, body: BriefSave, principal: Principal = Depends(require_owner)
) -> SuccessEnvelope[OrganizationView]:
    key = idempotency_key(request)
    with db.transaction() as conn:
        save_brief(
            conn, organization_id=principal.organization_id, user_id=principal.user_id, idempotency_key=key, update=body
        )
    return _view(request, principal)


@router.put("/workspace/policy", response_model=SuccessEnvelope[OrganizationView])
def put_policy(
    request: Request, body: PolicyUpdate, principal: Principal = Depends(require_owner)
) -> SuccessEnvelope[OrganizationView]:
    key = idempotency_key(request)
    with db.transaction() as conn:
        update_policy(conn, organization_id=principal.organization_id, idempotency_key=key, update=body)
    return _view(request, principal)


@router.post("/workspace/sources", status_code=201, response_model=SuccessEnvelope[EvidenceView])
def post_source(request: Request, body: SourceInput, principal: Principal = Depends(require_owner)):
    """Synchronous bounded ingestion (fetch <=10 s / 1 MB). Returns the new untrusted evidence; never approves facts.
    A replay of the same key and body returns 200 with the original evidence."""
    key = idempotency_key(request)
    with db.transaction() as conn:
        evidence, replayed = ingest_source(
            conn, organization_id=principal.organization_id, user_id=principal.user_id, idempotency_key=key, source=body
        )
    envelope = SuccessEnvelope[EvidenceView](data=evidence, correlation_id=correlation_id(request))
    return JSONResponse(status_code=200 if replayed else 201, content=envelope.model_dump(mode="json"))
