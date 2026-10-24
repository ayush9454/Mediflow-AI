"""Authenticated workflows; unavailable integrations and later tickets fail closed."""

from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, Header, Path, Query, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.concurrency import run_in_threadpool
from starlette.responses import StreamingResponse

from mediflow.authorization import Authorization
from mediflow.contracts import (
    Account,
    AssignmentRequest,
    BeginReviewRequest,
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
    ResultKind,
    ReviewPage,
    ReviewRecord,
    ReviewRequest,
    Role,
    UploadSession,
)
from mediflow.errors import ApplicationError
from mediflow.jobs import Jobs
from mediflow.uploads import Uploads

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
    return await run_in_threadpool(
        authorization(request).authenticate, credentials.credentials, request.state.request_id
    )


router = APIRouter(
    prefix="/api/v1",
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        408: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        410: {"model": ErrorResponse},
        413: {"model": ErrorResponse},
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


def upload_module(request: Request) -> Uploads:
    module = request.app.state.uploads
    if module is None:
        pending()
    return module


def job_module(request: Request) -> Jobs:
    module = request.app.state.jobs
    if module is None:
        pending()
    return module


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
    await run_in_threadpool(
        authorization(request).require_role, account, {Role.PATIENT}, request.state.request_id
    )
    return await run_in_threadpool(
        upload_module(request).register, account, body, idempotency_key, request.state.request_id
    )


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
    resolved = await run_in_threadpool(upload_module(request).resolve, report_id)
    await run_in_threadpool(
        authorization(request).report_access, account, resolved, "upload", request.state.request_id
    )
    await upload_module(request).upload(
        report_id, request.stream(), request.headers.get("content-type", "")
    )
    return Response(status_code=204)


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
    resolved = await run_in_threadpool(upload_module(request).resolve, report_id)
    await run_in_threadpool(
        authorization(request).report_access, account, resolved, "upload", request.state.request_id
    )
    return await run_in_threadpool(
        upload_module(request).complete, report_id, request.state.request_id
    )


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
    kind: ResultKind | None = None,
    account: Account = Depends(current_account),
) -> ReportResult:
    from mediflow.results import report_result as read_result

    await run_in_threadpool(
        authorization(request).report_access, account, report_id, "result", request.state.request_id
    )
    return await run_in_threadpool(
        read_result, upload_module(request).database, account, report_id, kind
    )


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
    await run_in_threadpool(
        authorization(request).report_access,
        account,
        report_id,
        "document",
        request.state.request_id,
    )
    source = await run_in_threadpool(upload_module(request).document, report_id)
    return StreamingResponse(
        iter(source[start : start + 65536] for start in range(0, len(source), 65536)),
        media_type="application/pdf",
        headers={"Content-Disposition": "inline; filename=report.pdf"},
    )


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
    await run_in_threadpool(
        authorization(request).report_access,
        account,
        report_id,
        "reprocess",
        request.state.request_id,
    )
    return await run_in_threadpool(
        job_module(request).reprocess, account, report_id, body, idempotency_key
    )


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
    from mediflow.reviews import decide

    return await run_in_threadpool(
        decide,
        upload_module(request).database,
        account,
        report_id,
        body,
        idempotency_key,
        request.state.request_id,
    )


@router.get("/cases", response_model=CasePage, tags=["cases"])
async def list_cases(
    request: Request,
    cursor: str | None = Query(default=None, max_length=1000),
    limit: int = Query(default=20, ge=1, le=100),
    account: Account = Depends(current_account),
) -> CasePage:
    from mediflow.cases import patient_cases

    await run_in_threadpool(
        authorization(request).require_role,
        account,
        {Role.PATIENT, Role.DOCTOR, Role.ADMINISTRATOR},
        request.state.request_id,
    )
    return await run_in_threadpool(
        patient_cases, upload_module(request).database, account, cursor, limit
    )


@router.get("/doctors", response_model=DoctorPage, tags=["cases"])
async def list_doctors(
    request: Request,
    cursor: str | None = Query(default=None, max_length=1000),
    limit: int = Query(default=20, ge=1, le=100),
    account: Account = Depends(current_account),
) -> DoctorPage:
    authorization(request).require_role(account, {Role.ADMINISTRATOR}, request.state.request_id)
    from mediflow.cases import doctors

    return await run_in_threadpool(doctors, upload_module(request).database, account, cursor, limit)


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
    from mediflow.cases import assign

    return await run_in_threadpool(
        assign,
        upload_module(request).database,
        account,
        case_id,
        body,
        idempotency_key,
        request.state.request_id,
    )


@router.post("/reports/{report_id}/begin-review", response_model=CaseSummary, tags=["reviews"])
async def begin_review(
    request: Request,
    report_id: ResourceId,
    body: BeginReviewRequest,
    idempotency_key: IdempotencyKey,
    account: Account = Depends(current_account),
) -> CaseSummary:
    authorization(request).report_access(account, report_id, "review", request.state.request_id)
    from mediflow.reviews import begin

    return await run_in_threadpool(
        begin,
        upload_module(request).database,
        account,
        report_id,
        body,
        idempotency_key,
        request.state.request_id,
    )


@router.get("/reports/{report_id}/reviews", response_model=ReviewPage, tags=["reviews"])
async def review_history(
    request: Request,
    report_id: ResourceId,
    cursor: str | None = Query(default=None, max_length=1000),
    limit: int = Query(default=20, ge=1, le=100),
    account: Account = Depends(current_account),
) -> ReviewPage:
    authorization(request).report_access(account, report_id, "review", request.state.request_id)
    from mediflow.reviews import history

    return await run_in_threadpool(
        history, upload_module(request).database, account, report_id, cursor, limit
    )
