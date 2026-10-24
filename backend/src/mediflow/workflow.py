"""Shared transactional workflow checks, safe metadata, cursors and audit events."""

import base64
import json
import re
from dataclasses import asdict
from datetime import UTC, datetime, timedelta

from mediflow.authorization import AuditEvent
from mediflow.contracts import Account, CaseSummary, ErrorCode, Role
from mediflow.errors import ApplicationError
from mediflow.uploads import scoped_key
from mediflow.uploads.database import Record, Transaction


def denied() -> ApplicationError:
    return ApplicationError(ErrorCode.PERMISSION_DENIED, 403, "Access is denied.")


def conflict() -> ApplicationError:
    return ApplicationError(ErrorCode.CONFLICT, 409, "Refresh the case before continuing.")


def active_account(tx: Transaction, account: Account, role: Role) -> None:
    user = tx.get("users", account.uid)
    hospital = tx.get("hospitals", account.hospital_id)
    if (
        not account.active
        or account.role != role
        or not user
        or user.get("uid") != account.uid
        or user.get("role") != role.value
        or user.get("hospitalId") != account.hospital_id
        or user.get("active") is not True
        or not hospital
        or hospital.get("active") is not True
    ):
        raise denied()
    if role == Role.DOCTOR and not eligible_doctor(tx, account.uid, account.hospital_id):
        raise denied()


def eligible_doctor(tx: Transaction, uid: str, hospital: str) -> Record | None:
    user, doctor = tx.get("users", uid), tx.get("doctors", uid)
    if (
        user
        and doctor
        and user.get("uid") == uid
        and user.get("role") == "doctor"
        and user.get("active") is True
        and user.get("hospitalId") == hospital
        and doctor.get("hospitalId") == hospital
        and doctor.get("active") is True
    ):
        return {**doctor, "displayName": user["displayName"]}
    return None


def case_report(tx: Transaction, account: Account, report_id: str) -> tuple[Record, Record]:
    report = tx.get("reports", report_id)
    case = tx.get("cases", report["caseId"]) if report else None
    if (
        not report
        or not case
        or report.get("hospitalId") != account.hospital_id
        or case.get("hospitalId") != account.hospital_id
        or case.get("reportId") != report_id
        or case.get("patientId") != report.get("patientId")
    ):
        raise denied()
    return case, report


def unexpired(report: Record) -> None:
    if report.get("expiresAt") and datetime.fromisoformat(
        report["expiresAt"].replace("Z", "+00:00")
    ) <= datetime.now(UTC):
        raise ApplicationError(ErrorCode.EXPIRED, 410, "This report has expired.")


def summary(
    case_id: str, case: Record, report: Record, failure_code: str | None = None
) -> CaseSummary:
    return CaseSummary(
        case_id=case_id,
        report_id=case["reportId"],
        patient_id=case["patientId"],
        assigned_doctor_id=case.get("assignedDoctorId"),
        processing_status=case["processingStatus"],
        review_status=case["reviewStatus"],
        version=case["version"],
        review_version=case["reviewVersion"],
        created_at=case["createdAt"],
        expires_at=report.get("expiresAt"),
        failure_code=failure_code,
        has_approved_result=bool(report.get("approvedAnalysisId")),
    )


def audit(
    tx: Transaction,
    identifier: str,
    account: Account,
    resource: str,
    action: str,
    request_id: str,
    **metadata: str | int | None,
) -> None:
    now = datetime.now(UTC)
    event = asdict(
        AuditEvent(
            account.uid,
            account.hospital_id,
            resource,
            action,
            "allowed",
            request_id,
            occurred_at=now,
            expires_at=now + timedelta(days=30),
        )
    )
    event.update(metadata)
    tx.put("auditEvents", identifier, event)


def page_scope(account: Account, collection: str, resource: str = "") -> str:
    return scoped_key(account.hospital_id, account.uid, account.role.value, collection, resource)


def decode_cursor(cursor: str | None, scope: str) -> str | None:
    if cursor is None:
        return None
    try:
        data = json.loads(
            base64.b64decode(cursor + "=" * (-len(cursor) % 4), altchars=b"-_", validate=True)
        )
        if data["scope"] != scope or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", data["after"]):
            raise ValueError("Invalid cursor")
        return str(data["after"])
    except (ValueError, KeyError, TypeError):
        raise ApplicationError(ErrorCode.INVALID_REQUEST, 400, "Refresh the list.") from None


def next_cursor(page: list[tuple[str, Record]], limit: int, scope: str) -> str | None:
    if len(page) <= limit:
        return None
    return (
        base64.urlsafe_b64encode(json.dumps({"scope": scope, "after": page[limit - 1][0]}).encode())
        .decode()
        .rstrip("=")
    )
