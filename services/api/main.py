from uuid import UUID, uuid4

from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from services.core.contracts.envelopes import ErrorBody, ErrorEnvelope, SuccessEnvelope
from services.core.contracts.enums import ErrorCode
from services.core.contracts.version import API_PREFIX, CONTRACT_VERSION
from services.core.contracts.views import HealthLive

CORRELATION_HEADER = "X-Correlation-ID"

_STATUS_CODES: dict[int, tuple[ErrorCode, bool]] = {
    400: (ErrorCode.VALIDATION_FAILED, False),
    401: (ErrorCode.UNAUTHENTICATED, False),
    403: (ErrorCode.FORBIDDEN, False),
    404: (ErrorCode.NOT_FOUND, False),
    405: (ErrorCode.NOT_FOUND, False),
    409: (ErrorCode.CONFLICT, False),
    422: (ErrorCode.DOMAIN_INVALID, False),
    429: (ErrorCode.RATE_LIMITED, True),
    503: (ErrorCode.DEPENDENCY_UNAVAILABLE, True),
}


def correlation_id(request: Request) -> UUID:
    return request.state.correlation_id


def error_response(request: Request, status: int, code: ErrorCode, message: str, retryable: bool, details: dict | None = None) -> JSONResponse:
    envelope = ErrorEnvelope(
        error=ErrorBody(code=code, message=message, retryable=retryable, details=details or {}),
        correlation_id=correlation_id(request),
    )
    return JSONResponse(status_code=status, content=envelope.model_dump(mode="json"))


router = APIRouter(prefix=API_PREFIX)


@router.get("/health/live", response_model=SuccessEnvelope[HealthLive], tags=["health"])
def health_live(request: Request) -> SuccessEnvelope[HealthLive]:
    return SuccessEnvelope[HealthLive](
        data=HealthLive(status="alive", service="api", contract_version=CONTRACT_VERSION),
        correlation_id=correlation_id(request),
    )


def create_app() -> FastAPI:
    app = FastAPI(title="Outcome AI API", version=CONTRACT_VERSION)

    @app.middleware("http")
    async def assign_correlation_id(request: Request, call_next):
        request.state.correlation_id = uuid4()
        response = await call_next(request)
        response.headers[CORRELATION_HEADER] = str(request.state.correlation_id)
        return response

    @app.exception_handler(RequestValidationError)
    async def on_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        fields = [".".join(str(p) for p in err.get("loc", ())) for err in exc.errors()]
        return error_response(
            request, 400, ErrorCode.VALIDATION_FAILED, "Request failed validation.", False, {"fields": fields}
        )

    @app.exception_handler(StarletteHTTPException)
    async def on_http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code, retryable = _STATUS_CODES.get(exc.status_code, (ErrorCode.INTERNAL, False))
        message = exc.detail if isinstance(exc.detail, str) else "Request failed."
        return error_response(request, exc.status_code, code, message, retryable)

    @app.exception_handler(Exception)
    async def on_unexpected(request: Request, exc: Exception) -> JSONResponse:
        return error_response(request, 500, ErrorCode.INTERNAL, "Internal error.", False)

    app.include_router(router)
    return app


app = create_app()
