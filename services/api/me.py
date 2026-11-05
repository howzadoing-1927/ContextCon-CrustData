from uuid import UUID

from fastapi import APIRouter, Depends, Request

from services.core import db
from services.core.contracts.envelopes import SuccessEnvelope
from services.core.contracts.version import API_PREFIX
from services.core.contracts.views import MembershipsView
from services.core.workspace import list_memberships

from .auth import require_user
from .errors import correlation_id

router = APIRouter(prefix=API_PREFIX, tags=["me"])


@router.get("/me/memberships", response_model=SuccessEnvelope[MembershipsView])
def get_memberships(request: Request, user_id: UUID = Depends(require_user)) -> SuccessEnvelope[MembershipsView]:
    with db.connection() as conn:
        data = list_memberships(conn, user_id=user_id)
    return SuccessEnvelope[MembershipsView](data=data, correlation_id=correlation_id(request))
