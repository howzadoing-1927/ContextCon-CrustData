import logging

from fastapi import APIRouter, Request

from services.core import db
from services.core.config import get_settings
from services.core.contracts.enums import ErrorCode
from services.core.contracts.envelopes import SuccessEnvelope
from services.core.contracts.version import API_PREFIX, CONTRACT_VERSION
from services.core.contracts.views import HealthLive, HealthReady

from .errors import ApiError, correlation_id

log = logging.getLogger("outcome.api.health")

router = APIRouter(prefix=API_PREFIX, tags=["health"])


@router.get("/health/live", response_model=SuccessEnvelope[HealthLive])
def health_live(request: Request) -> SuccessEnvelope[HealthLive]:
    return SuccessEnvelope[HealthLive](
        data=HealthLive(status="alive", service="api", contract_version=CONTRACT_VERSION),
        correlation_id=correlation_id(request),
    )


def readiness() -> HealthReady:
    settings = get_settings()
    try:
        with db.connection(timeout=3) as conn:
            conn.execute("select 1")
            row = None
            if settings.runtime_organization_id is not None:
                row = conn.execute(
                    """
                    select floor(extract(epoch from now() - (runtime_json -> 'worker' ->> 'last_seen_at')::timestamptz))::int
                           as age
                    from public.organizations where id = %s
                    """,
                    (settings.runtime_organization_id,),
                ).fetchone()
    except Exception:  # noqa: BLE001 - readiness reports, never raises provider/DB detail
        log.warning("readiness database check failed", exc_info=True)
        return HealthReady(status="not_ready", database="error", worker="unknown", last_seen_age_seconds=None)

    age = row["age"] if row else None
    if age is None:
        worker = "missing"
    elif age <= settings.worker_stale_seconds:
        worker = "fresh"
    else:
        worker = "stale"
    return HealthReady(
        status="ready" if worker == "fresh" else "not_ready",
        database="ok",
        worker=worker,
        last_seen_age_seconds=age,
    )


@router.get("/health/ready", response_model=SuccessEnvelope[HealthReady])
def health_ready(request: Request) -> SuccessEnvelope[HealthReady]:
    summary = readiness()
    if summary.status != "ready":
        raise ApiError(
            503,
            ErrorCode.DEPENDENCY_UNAVAILABLE,
            "Service is not ready.",
            retryable=True,
            details=summary.model_dump(mode="json"),
        )
    return SuccessEnvelope[HealthReady](data=summary, correlation_id=correlation_id(request))
