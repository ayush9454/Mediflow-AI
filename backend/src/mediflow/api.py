"""Foundation routes expose contracts and fail closed until adapters are implemented."""

from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, Header, Path, Query, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from mediflow.authorization import Authorization
from mediflow.contracts import (
    Account,
    AssignmentRequest,
    CasePage,
    CaseSummary,
    CompletionRequest,
    DoctorPage,
    ErrorCode,
    ErrorResponse,
    ProcessingJob,
    ReportMetadata,
    ReportRegistration,
    ReportResult,
    ReprocessingRequest,
    ReviewRecord,
    ReviewRequest,
    Role,
    UploadSession,
)
from mediflow.errors import ApplicationError

bearer = HTTPBearer(auto_error=False)
IdempotencyKey = Annotated[
    str,
    Header(
        alias="Idempotency-Key",
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9_-]+$",
        description="Reuse this key when retrying the same operation.",
    ),
]
ResourceId = Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{1,128}$")]


def authorization(request: Request) -> Authorization:
    module = request.app.state.authorization
    if module is None:
        raise ApplicationError(
            ErrorCode.INTEGRATION_NOT_CONFIGURED, 503, "Account verification is not configured yet."
        )
    return module


async def current_account(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> Account:
    if credentials is None:
        raise ApplicationError(ErrorCode.UNAUTHENTICATED, 401, "Sign in to continue.")
    return authorization(request).authenticate(credentials.credentials, request.state.request_id)


router = APIRouter(
    prefix="/api/v1",
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        410: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        429: {"model": ErrorResponse},
        501: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)


def pending() -> NoReturn:
    raise ApplicationError(
        ErrorCode.NOT_IMPLEMENTED, 501, "This workflow is not available in this foundation build."
    )


@router.get("/me", response_model=Account, tags=["accounts"])
async def me(account: Account = Depends(current_account)) -> Account:
    return account


@router.post("/reports", response_model=UploadSession, status_code=201, tags=["reports"])
async def register_report(
    request: Request,
    body: ReportRegistration,
    idempotency_key: IdempotencyKey,
    account: Account = Depends(current_account),
) -> UploadSession:
    authorization(request).require_role(account, {Role.PATIENT}, request.state.request_id)
    pending()


@router.put(
    "/reports/{report_id}/file",
    status_code=204,
    response_class=Response,
    tags=["reports"],
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"application/pdf": {"schema": {"type": "string", "format": "binary"}}},
        }
    },
)
async def upload_file(
    request: Request,
    report_id: ResourceId,
    account: Account = Depends(current_account),
) -> Response:
    authorization(request).report_access(account, report_id, "upload", request.state.request_id)
    pending()


@router.post(
    "/reports/{report_id}/complete-upload",
    response_model=ProcessingJob,
    status_code=202,
    tags=["reports"],
)
async def complete_upload(
    request: Request,
    report_id: ResourceId,
    body: CompletionRequest,
    idempotency_key: IdempotencyKey,
    account: Account = Depends(current_account),
) -> ProcessingJob:
    authorization(request).report_access(account, report_id, "upload", request.state.request_id)
    pending()


@router.get("/reports/{report_id}", response_model=ReportMetadata, tags=["reports"])
async def report_metadata(
    request: Request,
    report_id: ResourceId,
    account: Account = Depends(current_account),
) -> ReportMetadata:
    record = authorization(request).report_access(
        account, report_id, "metadata", request.state.request_id
    )
    return record


@router.get("/reports/{report_id}/result", response_model=ReportResult, tags=["reports"])
async def report_result(
    request: Request,
    report_id: ResourceId,
    account: Account = Depends(current_account),
) -> ReportResult:
    authorization(request).report_access(account, report_id, "result", request.state.request_id)
    pending()


@router.get(
    "/reports/{report_id}/document",
    response_class=Response,
    tags=["reports"],
    responses={
        200: {"content": {"application/pdf": {"schema": {"type": "string", "format": "binary"}}}}
    },
)
async def original_document(
    request: Request,
    report_id: ResourceId,
    account: Account = Depends(current_account),
) -> Response:
    authorization(request).report_access(account, report_id, "document", request.state.request_id)
    pending()


@router.post(
    "/reports/{report_id}/reprocess",
    response_model=ProcessingJob,
    status_code=202,
    tags=["reports"],
)
async def reprocess(
    request: Request,
    report_id: ResourceId,
    body: ReprocessingRequest,
    idempotency_key: IdempotencyKey,
    account: Account = Depends(current_account),
) -> ProcessingJob:
    authorization(request).report_access(account, report_id, "reprocess", request.state.request_id)
    pending()


@router.post(
    "/reports/{report_id}/review", response_model=ReviewRecord, status_code=201, tags=["reviews"]
)
async def review(
    request: Request,
    report_id: ResourceId,
    body: ReviewRequest,
    idempotency_key: IdempotencyKey,
    account: Account = Depends(current_account),
) -> ReviewRecord:
    authorization(request).report_access(account, report_id, "review", request.state.request_id)
    pending()


@router.get("/cases", response_model=CasePage, tags=["cases"])
async def list_cases(
    request: Request,
    cursor: str | None = Query(default=None, max_length=1000),
    limit: int = Query(default=20, ge=1, le=100),
    account: Account = Depends(current_account),
) -> CasePage:
    pending()


@router.get("/doctors", response_model=DoctorPage, tags=["cases"])
async def list_doctors(
    request: Request,
    cursor: str | None = Query(default=None, max_length=1000),
    limit: int = Query(default=20, ge=1, le=100),
    account: Account = Depends(current_account),
) -> DoctorPage:
    authorization(request).require_role(account, {Role.ADMINISTRATOR}, request.state.request_id)
    pending()


@router.post("/cases/{case_id}/assignment", response_model=CaseSummary, tags=["cases"])
async def assign_case(
    request: Request,
    case_id: ResourceId,
    body: AssignmentRequest,
    idempotency_key: IdempotencyKey,
    account: Account = Depends(current_account),
) -> CaseSummary:
    authorization(request).require_role(account, {Role.ADMINISTRATOR}, request.state.request_id)
    authorization(request).case_access(account, case_id, request.state.request_id)
    pending()
