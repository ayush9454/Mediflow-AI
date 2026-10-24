"""Paginated role-scoped metadata and atomic administrator assignment."""

from uuid import uuid4

from mediflow.contracts import (
    Account,
    AssignmentRequest,
    CasePage,
    CaseSummary,
    CaseView,
    DoctorPage,
    DoctorSummary,
    Role,
)
from mediflow.uploads import scoped_key
from mediflow.uploads.database import Database, Transaction
from mediflow.workflow import (
    active_account,
    audit,
    case_report,
    conflict,
    decode_cursor,
    denied,
    eligible_doctor,
    next_cursor,
    page_scope,
    summary,
    unexpired,
)


def role_scoped_cases(
    database: Database,
    account: Account,
    cursor: str | None,
    limit: int,
    view: CaseView = CaseView.ALL,
) -> CasePage:
    allowed = {
        Role.PATIENT: {CaseView.ALL, CaseView.HISTORY},
        Role.DOCTOR: {CaseView.ALL, CaseView.PENDING, CaseView.REVIEWED},
        Role.ADMINISTRATOR: {CaseView.ALL, CaseView.UNASSIGNED, CaseView.ASSIGNED},
    }
    if not account.active or view not in allowed[account.role]:
        raise denied()
    filters = {"hospitalId": account.hospital_id}
    if account.role == Role.PATIENT:
        filters["patientId"] = account.uid
    elif account.role == Role.DOCTOR:
        filters["assignedDoctorId"] = account.uid
    scope = page_scope(account, "cases", view.value)
    page = database.scoped_page("cases", filters, decode_cursor(cursor, scope), limit + 1)
    items = []
    for case_id, _ in page[:limit]:

        def read(tx: Transaction, case_id: str = case_id) -> CaseSummary | None:
            case = tx.get("cases", case_id)
            if (
                not case
                or not all(case.get(k) == v for k, v in filters.items())
                or not {"processingStatus", "reviewStatus", "reviewVersion", "createdAt"}
                <= case.keys()
            ):
                return None
            report = tx.get("reports", case["reportId"])
            if (
                not report
                or report.get("caseId") != case_id
                or report.get("hospitalId") != account.hospital_id
                or report.get("patientId") != case.get("patientId")
            ):
                return None
            head = tx.get("jobHeads", case["reportId"])
            job = tx.get("processingJobs", head["jobId"]) if head else None
            return summary(case_id, case, report, job.get("failureCode") if job else None)

        item = database.run(read)
        if item is not None and matches_view(item, view):
            items.append(item)
    return CasePage(items=tuple(items), next_cursor=next_cursor(page, limit, scope))


def matches_view(item: CaseSummary, view: CaseView) -> bool:
    """Filter a bounded role-scoped page without scanning the hospital unboundedly."""
    if view == CaseView.HISTORY:
        return item.processing_status in {"succeeded", "failed", "rejected"}
    if view == CaseView.PENDING:
        return item.processing_status != "succeeded" or item.review_status not in {
            "approved",
            "rejected",
        }
    if view == CaseView.REVIEWED:
        return item.processing_status == "succeeded" and item.review_status in {
            "approved",
            "rejected",
        }
    if view == CaseView.UNASSIGNED:
        return item.assigned_doctor_id is None
    if view == CaseView.ASSIGNED:
        return item.assigned_doctor_id is not None
    return True


def doctors(database: Database, account: Account, cursor: str | None, limit: int) -> DoctorPage:
    scope = page_scope(account, "doctors")
    page = database.scoped_page(
        "doctors", {"hospitalId": account.hospital_id}, decode_cursor(cursor, scope), limit + 1
    )
    items = []
    for uid, _ in page[:limit]:

        def read(tx: Transaction, uid: str = uid) -> DoctorSummary | None:
            active_account(tx, account, Role.ADMINISTRATOR)
            doctor = eligible_doctor(tx, uid, account.hospital_id)
            return (
                DoctorSummary(
                    doctor_id=uid,
                    display_name=doctor["displayName"],
                    department=doctor.get("department", "General"),
                    active=True,
                )
                if doctor
                else None
            )

        item = database.run(read)
        if item:
            items.append(item)
    return DoctorPage(items=tuple(items), next_cursor=next_cursor(page, limit, scope))


def assign(
    database: Database,
    account: Account,
    case_id: str,
    body: AssignmentRequest,
    key: str,
    request_id: str,
) -> CaseSummary:
    index = scoped_key(account.hospital_id, account.uid, case_id, "assignment", key)
    fingerprint = scoped_key(body.model_dump_json())
    event_id = uuid4().hex

    def change(tx: Transaction) -> CaseSummary:
        active_account(tx, account, Role.ADMINISTRATOR)
        stored_case = tx.get("cases", case_id)
        if not stored_case:
            raise denied()
        case, report = case_report(tx, account, stored_case["reportId"])
        if report["caseId"] != case_id:
            raise denied()
        unexpired(report)
        previous = tx.get("assignmentKeys", index)
        if previous:
            if previous["fingerprint"] != fingerprint:
                raise conflict()
            return CaseSummary.model_validate(previous["response"])
        if case["version"] != body.expected_case_version:
            raise conflict()
        if not eligible_doctor(tx, body.doctor_id, account.hospital_id):
            raise denied()
        old_doctor = case.get("assignedDoctorId")
        case.update(assignedDoctorId=body.doctor_id, version=case["version"] + 1)
        # A new doctor must explicitly begin review again.
        if case["reviewStatus"] == "under_review":
            case["reviewStatus"] = "pending"
        report.update(
            assignedDoctorId=body.doctor_id,
            caseVersion=case["version"],
            reviewStatus=case["reviewStatus"],
        )
        response = summary(case_id, case, report)
        tx.put("cases", case_id, case)
        tx.put("reports", report["reportId"], report)
        tx.put(
            "assignmentKeys",
            index,
            {
                "fingerprint": fingerprint,
                "response": response.model_dump(mode="json", by_alias=True),
                "expiresAt": report.get("expiresAt"),
            },
        )
        audit(
            tx,
            event_id,
            account,
            report["reportId"],
            "case_assigned",
            request_id,
            previousDoctorId=old_doctor,
            assignedDoctorId=body.doctor_id,
            caseVersion=case["version"],
        )
        return response

    return database.run(change)
