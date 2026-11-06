import re
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from services.core import db
from services.core.campaigns import campaign_ledger, get_mission_detail, launch_campaign, list_campaigns
from services.core.contracts.enums import ErrorCode
from services.core.contracts.base import ContractModel
from services.core.contracts.envelopes import SuccessEnvelope
from services.core.contracts.requests import CampaignCreate
from services.core.contracts.version import API_PREFIX
from services.core.contracts.views import CampaignLaunchView, CampaignView, DecisionView, MissionDetail

from .auth import Principal, require_member
from .errors import ApiError, correlation_id

router = APIRouter(prefix=API_PREFIX, tags=["campaigns"])


class CampaignPage(ContractModel):
    items: list[CampaignView]
    next_cursor: str | None


class LedgerPage(ContractModel):
    items: list[DecisionView]
    next_cursor: str | None

_IDEMPOTENCY_KEY = re.compile(r"^[\x21-\x7e]{1,128}$")


def idempotency_key(request: Request) -> str:
    key = request.headers.get("idempotency-key", "")
    if not _IDEMPOTENCY_KEY.match(key):
        raise ApiError(
            400,
            ErrorCode.VALIDATION_FAILED,
            "Idempotency-Key header is required (1-128 printable ASCII characters, no spaces).",
            details={"field": "Idempotency-Key"},
        )
    return key


@router.post("/campaigns", status_code=202, response_model=SuccessEnvelope[CampaignLaunchView])
def create_campaign(
    request: Request, body: CampaignCreate, principal: Principal = Depends(require_member)
) -> SuccessEnvelope[CampaignLaunchView]:
    key = idempotency_key(request)
    with db.transaction() as conn:
        view = launch_campaign(
            conn,
            organization_id=principal.organization_id,
            user_id=principal.user_id,
            idempotency_key=key,
            body=body,
        )
    return SuccessEnvelope[CampaignLaunchView](data=view, correlation_id=correlation_id(request))


@router.get("/campaigns/{campaign_id}", response_model=SuccessEnvelope[MissionDetail])
def get_campaign(
    request: Request, campaign_id: UUID, principal: Principal = Depends(require_member)
) -> SuccessEnvelope[MissionDetail]:
    with db.connection() as conn:
        detail = get_mission_detail(conn, organization_id=principal.organization_id, campaign_id=campaign_id)
    return SuccessEnvelope[MissionDetail](data=detail, correlation_id=correlation_id(request))


@router.get("/campaigns", response_model=SuccessEnvelope[CampaignPage])
def get_campaigns(
    request: Request, limit: int = Query(25, ge=1, le=100), principal: Principal = Depends(require_member)
) -> SuccessEnvelope[CampaignPage]:
    with db.connection() as conn:
        items = list_campaigns(conn, organization_id=principal.organization_id, limit=limit)
    return SuccessEnvelope[CampaignPage](data=CampaignPage(items=items, next_cursor=None), correlation_id=correlation_id(request))


@router.get("/campaigns/{campaign_id}/ledger", response_model=SuccessEnvelope[LedgerPage])
def get_ledger(
    request: Request, campaign_id: UUID, limit: int = Query(200, ge=1, le=500), principal: Principal = Depends(require_member)
) -> SuccessEnvelope[LedgerPage]:
    with db.connection() as conn:
        items = campaign_ledger(conn, organization_id=principal.organization_id, campaign_id=campaign_id, limit=limit)
    return SuccessEnvelope[LedgerPage](data=LedgerPage(items=items, next_cursor=None), correlation_id=correlation_id(request))
