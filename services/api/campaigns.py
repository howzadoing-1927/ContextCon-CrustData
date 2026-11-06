import re
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from services.core import db
from services.core.campaigns import get_mission_detail, inject_buyer_reply, launch_campaign, list_campaigns, list_ledger
from services.core.contracts.enums import ErrorCode
from services.core.contracts.envelopes import ListData, SuccessEnvelope
from services.core.contracts.requests import BuyerReplyInput, CampaignCreate
from services.core.contracts.version import API_PREFIX
from services.core.contracts.views import CampaignLaunchView, CampaignView, DecisionView, MissionDetail

from .auth import Principal, require_member
from .errors import ApiError, correlation_id

router = APIRouter(prefix=API_PREFIX, tags=["campaigns"])

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


@router.get("/campaigns", response_model=SuccessEnvelope[ListData[CampaignView]])
def get_campaigns(
    request: Request,
    principal: Principal = Depends(require_member),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=25, ge=1, le=100),
) -> SuccessEnvelope[ListData[CampaignView]]:
    with db.connection() as conn:
        data = list_campaigns(conn, organization_id=principal.organization_id, cursor=cursor, limit=limit)
    return SuccessEnvelope[ListData[CampaignView]](data=data, correlation_id=correlation_id(request))


@router.get("/campaigns/{campaign_id}/ledger", response_model=SuccessEnvelope[ListData[DecisionView]])
def get_campaign_ledger(
    request: Request,
    campaign_id: UUID,
    principal: Principal = Depends(require_member),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=25, ge=1, le=100),
) -> SuccessEnvelope[ListData[DecisionView]]:
    with db.connection() as conn:
        data = list_ledger(
            conn, organization_id=principal.organization_id, campaign_id=campaign_id, cursor=cursor, limit=limit
        )
    return SuccessEnvelope[ListData[DecisionView]](data=data, correlation_id=correlation_id(request))


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


@router.post("/campaigns/{campaign_id}/buyer-reply", response_model=SuccessEnvelope[MissionDetail])
def post_buyer_reply(
    request: Request, campaign_id: UUID, body: BuyerReplyInput, principal: Principal = Depends(require_member)
) -> SuccessEnvelope[MissionDetail]:
    with db.transaction() as conn:
        detail = inject_buyer_reply(
            conn, organization_id=principal.organization_id, campaign_id=campaign_id, body_text=body.body_text
        )
    return SuccessEnvelope[MissionDetail](data=detail, correlation_id=correlation_id(request))
