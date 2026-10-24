"""Read role-specific immutable results under fresh case and retention checks."""

from datetime import UTC, datetime

from mediflow.contracts import (
    Account,
    AnalysisCandidate,
    ApprovedResult,
    ErrorCode,
    ReportMetadata,
    ReportResult,
    ResultKind,
    Role,
)
from mediflow.errors import ApplicationError
from mediflow.uploads.database import Database, Transaction


def report_result(
    database: Database, account: Account, report_id: str, kind: ResultKind | None
) -> ReportResult:
    selected = kind or (ResultKind.APPROVED if account.role == Role.PATIENT else ResultKind.DRAFT)
    if account.role not in {Role.PATIENT, Role.DOCTOR} or (
        account.role == Role.PATIENT and selected != ResultKind.APPROVED
    ):
        raise ApplicationError(ErrorCode.PERMISSION_DENIED, 403, "Access is denied.")

    def read(tx: Transaction) -> ReportResult:
        data = tx.get("reports", report_id)
        case = tx.get("cases", data["caseId"]) if data else None
        if (
            not data
            or not case
            or data.get("hospitalId") != account.hospital_id
            or case.get("hospitalId") != account.hospital_id
            or case.get("reportId") != report_id
            or case.get("patientId") != data.get("patientId")
            or not account.active
            or (account.role == Role.PATIENT and data.get("patientId") != account.uid)
            or (account.role == Role.DOCTOR and case.get("assignedDoctorId") != account.uid)
        ):
            raise ApplicationError(ErrorCode.PERMISSION_DENIED, 403, "Access is denied.")
        report = ReportMetadata.model_validate(data)
        if report.expires_at is not None and report.expires_at <= datetime.now(UTC):
            raise ApplicationError(ErrorCode.EXPIRED, 410, "This report has expired.")
        if selected == ResultKind.DRAFT:
            candidate = (
                tx.get("analyses", report.latest_analysis_id) if report.latest_analysis_id else None
            )
            if candidate and candidate.get("reportId") == report_id:
                return ReportResult(
                    kind=selected, draft=AnalysisCandidate.model_validate(candidate)
                )
        else:
            snapshot = tx.get("approvedResults", report_id) if report.approved_analysis_id else None
            if (
                snapshot
                and snapshot.get("reportId") == report_id
                and snapshot.get("analysisId") == report.approved_analysis_id
            ):
                return ReportResult(kind=selected, approved=ApprovedResult.model_validate(snapshot))
        raise ApplicationError(ErrorCode.CONFLICT, 409, "This result is not available yet.")

    return database.run(read)
