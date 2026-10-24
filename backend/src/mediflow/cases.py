"""Bounded patient-owned workflow metadata, without document or analysis payloads."""

import base64
import hashlib
import json
import re

from mediflow.contracts import Account, CasePage, CaseSummary, ErrorCode, Role
from mediflow.errors import ApplicationError
from mediflow.uploads.database import Database, Transaction


def patient_cases(database: Database, account: Account, cursor: str | None, limit: int) -> CasePage:
    if account.role != Role.PATIENT or not account.active:
        raise ApplicationError(ErrorCode.PERMISSION_DENIED, 403, "Access is denied.")
    scope = hashlib.sha256(json.dumps([account.hospital_id, account.uid]).encode()).hexdigest()
    after = None
    if cursor:
        try:
            data = json.loads(
                base64.b64decode(cursor + "=" * (-len(cursor) % 4), altchars=b"-_", validate=True)
            )
            if data["scope"] != scope or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", data["after"]):
                raise ValueError("Invalid cursor")
            after = data["after"]
        except (ValueError, KeyError, TypeError):
            raise ApplicationError(
                ErrorCode.INVALID_REQUEST, 400, "Refresh the case list."
            ) from None
    page = database.scoped_page(
        "cases", {"hospitalId": account.hospital_id, "patientId": account.uid}, after, limit + 1
    )
    items = []
    for case_id, _ in page[:limit]:

        def read(tx: Transaction, case_id: str = case_id) -> CaseSummary | None:
            case = tx.get("cases", case_id)
            if (
                not case
                or case.get("hospitalId") != account.hospital_id
                or case.get("patientId") != account.uid
            ):
                return None
            if (
                not {"processingStatus", "reviewStatus", "reviewVersion", "createdAt"}
                <= case.keys()
            ):
                # The old authorization-only seed has no actual upload/job workflow.
                return None
            report = tx.get("reports", case["reportId"])
            if (
                not report
                or report.get("caseId") != case_id
                or report.get("hospitalId") != account.hospital_id
                or report.get("patientId") != account.uid
            ):
                return None
            return CaseSummary(
                case_id=case_id,
                report_id=case["reportId"],
                patient_id=account.uid,
                assigned_doctor_id=case.get("assignedDoctorId"),
                processing_status=case["processingStatus"],
                review_status=case["reviewStatus"],
                version=case["version"],
                review_version=case["reviewVersion"],
                created_at=case["createdAt"],
                expires_at=report.get("expiresAt"),
            )

        item = database.run(read)
        if item is not None:
            items.append(item)
    next_cursor = None
    if len(page) > limit:
        next_cursor = (
            base64.urlsafe_b64encode(
                json.dumps({"scope": scope, "after": page[limit - 1][0]}).encode()
            )
            .decode()
            .rstrip("=")
        )
    return CasePage(items=tuple(items), next_cursor=next_cursor)
