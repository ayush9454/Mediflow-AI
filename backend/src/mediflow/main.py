"""Application factory with safe errors and explicit foundation readiness."""

import logging
from collections.abc import Awaitable, Callable
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException
from starlette.responses import Response

from mediflow import __version__
from mediflow.api import router
from mediflow.config import Settings
from mediflow.contracts import ErrorCode, ErrorDetail, ErrorField, ErrorResponse, HealthResponse
from mediflow.errors import ApplicationError

logger = logging.getLogger(__name__)


def error_response(
    request: Request,
    status_code: int,
    code: ErrorCode,
    message: str,
    fields: tuple[ErrorField, ...] = (),
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", str(uuid4()))
    payload = ErrorResponse(
        error=ErrorDetail(code=code, message=message, request_id=request_id, fields=fields)
    )
    headers = {"X-Request-ID": request_id}
    if status_code == 401:
        headers["WWW-Authenticate"] = "Bearer"
    return JSONResponse(
        status_code=status_code,
        content=payload.model_dump(mode="json", by_alias=True),
        headers=headers,
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    application = FastAPI(
        title="MediFlow AI API",
        version=__version__,
        description=(
            "Synthetic laboratory document workflow. Foundation build: liveness and contracts "
            "are available; authentication, storage, queue and AI adapters are not connected."
        ),
        openapi_url="/api/v1/openapi.json",
        docs_url="/api/v1/docs",
        redoc_url=None,
    )
    application.state.settings = settings or Settings.from_environment()

    @application.middleware("http")
    async def request_identity(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        # Generate server IDs; do not reflect untrusted request headers into logs.
        request.state.request_id = str(uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    @application.exception_handler(ApplicationError)
    async def application_error(request: Request, error: ApplicationError) -> JSONResponse:
        return error_response(request, error.status_code, error.code, error.safe_message)

    @application.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError) -> JSONResponse:
        # Extra-key locations are also user input; do not reflect those names.
        fields = tuple(
            ErrorField(
                field=".".join(
                    str(part)
                    for part in (
                        item["loc"][:1] if item["type"] == "extra_forbidden" else item["loc"]
                    )
                ),
                code=item["type"],
            )
            for item in error.errors()
        )
        return error_response(
            request, 422, ErrorCode.INVALID_REQUEST, "The request is invalid.", fields
        )

    @application.exception_handler(HTTPException)
    async def http_error(request: Request, error: HTTPException) -> JSONResponse:
        code = ErrorCode.NOT_FOUND if error.status_code == 404 else ErrorCode.INVALID_REQUEST
        return error_response(
            request, error.status_code, code, "The request could not be completed."
        )

    @application.exception_handler(Exception)
    async def unexpected_error(request: Request, error: Exception) -> JSONResponse:
        logger.error("Unhandled API error (%s)", type(error).__name__)
        return error_response(
            request, 500, ErrorCode.INTERNAL_ERROR, "The request could not be completed."
        )

    @application.get("/health/live", response_model=HealthResponse, tags=["health"])
    async def live() -> HealthResponse:
        return HealthResponse(status="ok", version=__version__)

    @application.get(
        "/health/ready", response_model=HealthResponse, status_code=503, tags=["health"]
    )
    async def ready() -> HealthResponse:
        # Environment variables alone do not prove that a functioning adapter exists.
        return HealthResponse(status="not_ready", version=__version__)

    application.include_router(router)
    return application


app = create_app()
