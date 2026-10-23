"""Versioned wire contracts. Exported to OpenAPI, JSON Schema and Dart.

Printed laboratory strings remain strings: do not coerce decimals, inequalities,
units or qualitative findings into inferred clinical values.
"""

from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel

Identifier = Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")]
PrintedText = Annotated[str, Field(min_length=1, max_length=5000)]
Reason = Annotated[str, Field(min_length=1, max_length=2000)]


class WireModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
        frozen=True,
    )


class VersionedModel(WireModel):
    schema_version: Literal["1.0"] = "1.0"


class Role(StrEnum):
    PATIENT = "patient"
    DOCTOR = "doctor"
    ADMINISTRATOR = "administrator"


class ProcessingStatus(StrEnum):
    UPLOAD_PENDING = "upload_pending"
    VALIDATING = "validating"
    QUEUED = "queued"
    PROCESSING = "processing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REJECTED = "rejected"


class ReviewStatus(StrEnum):
    NOT_READY = "not_ready"
    PENDING = "pending"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    REJECTED = "rejected"


class ReviewDecision(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"


class ExtractionMethod(StrEnum):
    NATIVE = "native"
    OCR = "ocr"


class IssueSeverity(StrEnum):
    WARNING = "warning"
    BLOCKING = "blocking"


class ErrorCode(StrEnum):
    UNAUTHENTICATED = "unauthenticated"
    PERMISSION_DENIED = "permission_denied"
    NOT_FOUND = "not_found"
    INVALID_REQUEST = "invalid_request"
    INVALID_UPLOAD = "invalid_upload"
    EXPIRED = "expired"
    QUOTA_EXHAUSTED = "quota_exhausted"
    CONFLICT = "conflict"
    TEMPORARILY_UNAVAILABLE = "temporarily_unavailable"
    INTEGRATION_NOT_CONFIGURED = "integration_not_configured"
    NOT_IMPLEMENTED = "not_implemented"
    INTERNAL_ERROR = "internal_error"


class Account(VersionedModel):
    uid: Identifier
    hospital_id: Identifier
    display_name: Annotated[str, Field(min_length=1, max_length=200)]
    role: Role
    active: bool


class EvidenceReference(WireModel):
    page: Annotated[int, Field(ge=1, le=10)]
    quotation: PrintedText
    extraction_method: ExtractionMethod


class ValidationIssue(WireModel):
    issue_id: Identifier
    field: Annotated[str, Field(min_length=1, max_length=200)]
    code: Annotated[str, Field(min_length=1, max_length=100)]
    severity: IssueSeverity
    message: Annotated[str, Field(min_length=1, max_length=1000)]


class LaboratoryRow(WireModel):
    row_id: Identifier
    analyte: PrintedText
    result: PrintedText
    unit: PrintedText | None = None
    reference_range: PrintedText | None = None
    abnormality_flag: PrintedText | None = None
    collection_date: PrintedText | None = None
    evidence: tuple[EvidenceReference, ...] = ()
    issues: tuple[ValidationIssue, ...] = ()

    @model_validator(mode="after")
    def missing_evidence_is_explicit(self) -> Self:
        if not self.evidence and not any(
            issue.code == "missing_evidence" and issue.severity == IssueSeverity.BLOCKING
            for issue in self.issues
        ):
            raise ValueError("A row needs evidence or an explicit blocking missing_evidence issue.")
        return self


class AnalysisProvenance(WireModel):
    pipeline_version: PrintedText
    prompt_version: PrintedText
    model_provider: PrintedText
    model_version: PrintedText


class AnalysisCandidate(VersionedModel):
    analysis_id: Identifier
    report_id: Identifier
    job_id: Identifier
    version: Annotated[int, Field(ge=1)]
    rows: tuple[LaboratoryRow, ...]
    summary: PrintedText | None = None
    issues: tuple[ValidationIssue, ...] = ()
    provenance: AnalysisProvenance
    created_at: AwareDatetime


class ReportMetadata(VersionedModel):
    report_id: Identifier
    case_id: Identifier
    case_version: Annotated[int, Field(ge=1)]
    review_version: Annotated[int, Field(ge=0)]
    patient_id: Identifier
    hospital_id: Identifier
    file_name: Annotated[str, Field(min_length=1, max_length=255)]
    processing_status: ProcessingStatus
    review_status: ReviewStatus = ReviewStatus.NOT_READY
    assigned_doctor_id: Identifier | None = None
    latest_analysis_id: Identifier | None = None
    approved_analysis_id: Identifier | None = None
    page_count: Annotated[int, Field(ge=1, le=10)] | None = None
    created_at: AwareDatetime
    expires_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def consistent_expiry(self) -> Self:
        if self.expires_at is not None and self.expires_at <= self.created_at:
            raise ValueError("Expiry must follow creation.")
        return self


class CaseSummary(VersionedModel):
    case_id: Identifier
    report_id: Identifier
    patient_id: Identifier
    assigned_doctor_id: Identifier | None = None
    processing_status: ProcessingStatus
    review_status: ReviewStatus
    version: Annotated[int, Field(ge=1)]
    review_version: Annotated[int, Field(ge=0)]
    created_at: AwareDatetime


class CasePage(VersionedModel):
    items: tuple[CaseSummary, ...]
    next_cursor: str | None = None


class DoctorSummary(WireModel):
    doctor_id: Identifier
    display_name: PrintedText
    department: PrintedText
    active: bool


class DoctorPage(VersionedModel):
    items: tuple[DoctorSummary, ...]
    next_cursor: str | None = None


class ReportRegistration(VersionedModel):
    file_name: Annotated[str, Field(min_length=1, max_length=255)]
    byte_count: Annotated[int, Field(gt=0, le=10_000_000)]
    synthetic_data_acknowledged: Literal[True]


class UploadSession(VersionedModel):
    report: ReportMetadata
    upload_path: Annotated[str, Field(pattern=r"^/api/v1/reports/[A-Za-z0-9_-]+/file$")]
    expires_at: AwareDatetime


class CompletionRequest(VersionedModel):
    """Patient identity and storage paths are never client input."""


class ProcessingJob(VersionedModel):
    job_id: Identifier
    report_id: Identifier
    status: ProcessingStatus
    attempt_count: Annotated[int, Field(ge=0, le=3)] = 0
    maximum_attempts: Literal[3] = 3
    created_at: AwareDatetime
    updated_at: AwareDatetime
    failure_code: ErrorCode | None = None


class ReprocessingRequest(VersionedModel):
    expected_latest_analysis_id: Identifier | None
    reason: Reason


class AssignmentRequest(VersionedModel):
    doctor_id: Identifier
    expected_case_version: Annotated[int, Field(ge=1)]


class RowCorrection(WireModel):
    row_id: Identifier
    corrected_row: LaboratoryRow
    reason: Reason

    @model_validator(mode="after")
    def correction_identifies_same_row(self) -> Self:
        if self.row_id != self.corrected_row.row_id:
            raise ValueError("Correction row identifiers must match.")
        if not self.reason.strip():
            raise ValueError("A correction needs a reason.")
        return self


class UnresolvedAcknowledgement(WireModel):
    issue_id: Identifier
    reason: Reason

    @model_validator(mode="after")
    def meaningful_reason(self) -> Self:
        if not self.reason.strip():
            raise ValueError("An unresolved issue needs a reason.")
        return self


class ReviewRequest(VersionedModel):
    analysis_id: Identifier
    expected_analysis_version: Annotated[int, Field(ge=1)]
    expected_case_version: Annotated[int, Field(ge=1)]
    expected_review_version: Annotated[
        int,
        Field(ge=0, description="Zero before the first review; otherwise the last review version."),
    ]
    decision: ReviewDecision
    corrections: tuple[RowCorrection, ...] = ()
    unresolved_acknowledgements: tuple[UnresolvedAcknowledgement, ...] = ()
    comment: Reason | None = None

    @model_validator(mode="after")
    def consistent_decision(self) -> Self:
        row_ids = [correction.row_id for correction in self.corrections]
        issue_ids = [item.issue_id for item in self.unresolved_acknowledgements]
        if len(row_ids) != len(set(row_ids)) or len(issue_ids) != len(set(issue_ids)):
            raise ValueError("Duplicate corrections or acknowledgements are ambiguous.")
        if self.decision == ReviewDecision.REJECTED:
            if self.comment is None or not self.comment.strip():
                raise ValueError("Rejection requires a reason.")
            if self.corrections or self.unresolved_acknowledgements:
                raise ValueError("Rejection cannot apply corrections or approvals.")
        return self


class ReviewRecord(VersionedModel):
    review_id: Identifier
    version: Annotated[int, Field(ge=1)]
    report_id: Identifier
    reviewer_id: Identifier
    reviewed_at: AwareDatetime
    request: ReviewRequest


class ApprovedResult(VersionedModel):
    report_id: Identifier
    analysis_id: Identifier
    analysis_version: Annotated[int, Field(ge=1)]
    review_id: Identifier
    reviewer_id: Identifier
    reviewed_at: AwareDatetime
    rows: tuple[LaboratoryRow, ...]
    summary: PrintedText | None = None
    unresolved_acknowledgements: tuple[UnresolvedAcknowledgement, ...] = ()


class ResultKind(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"


class ReportResult(VersionedModel):
    kind: ResultKind
    draft: AnalysisCandidate | None = None
    approved: ApprovedResult | None = None

    @model_validator(mode="after")
    def only_one_result_kind(self) -> Self:
        if self.kind == ResultKind.DRAFT and (self.draft is None or self.approved is not None):
            raise ValueError("A draft response contains only a draft.")
        if self.kind == ResultKind.APPROVED and (self.approved is None or self.draft is not None):
            raise ValueError("An approved response cannot contain an AI draft.")
        return self


class ErrorField(WireModel):
    field: str
    code: str


class ErrorDetail(WireModel):
    code: ErrorCode
    message: str
    request_id: str
    fields: tuple[ErrorField, ...] = ()


class ErrorResponse(VersionedModel):
    error: ErrorDetail


class HealthResponse(VersionedModel):
    status: Literal["ok", "not_ready"]
    service: Literal["mediflow-api"] = "mediflow-api"
    synthetic_data_only: Literal[True] = True
    version: str
