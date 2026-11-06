import logging
import os
from contextlib import asynccontextmanager
from uuid import uuid4

import psycopg
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from psycopg_pool import PoolTimeout
from starlette.exceptions import HTTPException as StarletteHTTPException

from services.core.config import get_settings
from services.core.contracts.enums import ErrorCode
from services.core.contracts.version import CONTRACT_VERSION
from services.core.db import DatabaseNotConfigured, reset_pool

from . import campaigns, google, health, workspace
from .errors import ApiError, error_response

log = logging.getLogger("outcome.api")

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


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    reset_pool()


def create_app() -> FastAPI:
    app = FastAPI(title="Outcome AI API", version=CONTRACT_VERSION, lifespan=lifespan)

    @app.middleware("http")
    async def assign_correlation_id(request: Request, call_next):
        request.state.correlation_id = uuid4()
        response = await call_next(request)
        response.headers[CORRELATION_HEADER] = str(request.state.correlation_id)
        return response

    @app.exception_handler(ApiError)
    async def on_api_error(request: Request, exc: ApiError) -> JSONResponse:
        return error_response(request, exc.status, exc.code, exc.message, exc.retryable, exc.details)

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

    @app.exception_handler(PoolTimeout)
    @app.exception_handler(psycopg.OperationalError)
    @app.exception_handler(DatabaseNotConfigured)
    async def on_database_unavailable(request: Request, exc: Exception) -> JSONResponse:
        log.warning("database unavailable: %s", type(exc).__name__)
        return error_response(request, 503, ErrorCode.DEPENDENCY_UNAVAILABLE, "Database unavailable.", True)

    @app.exception_handler(Exception)
    async def on_unexpected(request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled error")
        return error_response(request, 500, ErrorCode.INTERNAL, "Internal error.", False)

    app.include_router(health.router)
    app.include_router(campaigns.router)
    app.include_router(workspace.router)
    app.include_router(google.router)

    get_settings()
    origins = {o.strip() for o in os.environ.get("ALLOWED_CORS_ORIGINS", "").split(",") if o.strip()}
    origins |= {o for o in (os.environ.get("WEB_PUBLIC_ORIGIN", "").strip(), "http://localhost:3100") if o}
    app.add_middleware(
        CORSMiddleware,
        allow_origins=sorted(origins),
        allow_methods=["GET", "POST", "PUT"],
        allow_headers=["Authorization", "Content-Type", "Accept", "Idempotency-Key", "X-Organization-ID"],
        expose_headers=[CORRELATION_HEADER],
    )
    return app


app = create_app()
