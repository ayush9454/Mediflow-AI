"""Version-specific, idempotent review transitions and immutable decision history."""

from datetime import UTC, datetime
from uuid import uuid4

from mediflow.contracts import (
    Account,
    AnalysisCandidate,
    ApprovedResult,
    BeginReviewRequest,
    CaseSummary,
    ReviewDecision,
    ReviewPage,
    ReviewRecord,
    ReviewRequest,
    Role,
)
from mediflow.review_validation import approved_rows
from mediflow.uploads import STORAGE_LIMIT_BYTES, scoped_key
from mediflow.uploads.capacity import store_payload
from mediflow.uploads.database import Database, Record, Transaction
from mediflow.workflow import (
    active_account,
    audit,
    case_report,
    conflict,
    decode_cursor,
    denied,
    next_cursor,
    page_scope,
    summary,
    unexpired,
)


def review_access(tx: Transaction, account: Account, report_id: str) -> tuple[Record, Record]:
    active_account(tx, account, Role.DOCTOR)
    case, report = case_report(tx, account, report_id)
    if case.get("assignedDoctorId") != account.uid:
        raise denied()
    unexpired(report)
    return case, report


def current_candidate(
    tx: Transaction, case: Record, report: Record, body: BeginReviewRequest | ReviewRequest
) -> AnalysisCandidate:
    data = tx.get("analyses", body.analysis_id)
    if (
        not data
        or data.get("reportId") != report["reportId"]
        or data.get("version") != body.expected_analysis_version
        or report.get("latestAnalysisId") != body.analysis_id
        or case["version"] != body.expected_case_version
        or report["reviewVersion"] != body.expected_review_version
        or case["reviewVersion"] != body.expected_review_version
        or report["processingStatus"] != "succeeded"
        or case["reviewStatus"] not in {"pending", "under_review"}
    ):
        raise conflict()
    return AnalysisCandidate.model_validate(data)


def begin(
    database: Database,
    account: Account,
    report_id: str,
    body: BeginReviewRequest,
    key: str,
    request_id: str,
) -> CaseSummary:
    index = scoped_key(account.hospital_id, account.uid, report_id, "begin", key)
    fingerprint = scoped_key(body.model_dump_json())
    event_id = uuid4().hex

    def change(tx: Transaction) -> CaseSummary:
        case, report = review_access(tx, account, report_id)
        previous = tx.get("beginReviewKeys", index)
        if previous:
            if previous["fingerprint"] != fingerprint:
                raise conflict()
            return CaseSummary.model_validate(previous["response"])
        current_candidate(tx, case, report, body)
        if case["reviewStatus"] != "pending":
            raise conflict()
        case.update(reviewStatus="under_review", version=case["version"] + 1)
        report.update(reviewStatus="under_review", caseVersion=case["version"])
        response = summary(report["caseId"], case, report)
        tx.put("cases", report["caseId"], case)
        tx.put("reports", report_id, report)
        tx.put(
            "beginReviewKeys",
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
            report_id,
            "review_begun",
            request_id,
            analysisId=body.analysis_id,
            caseVersion=case["version"],
        )
        return response

    return database.run(change)


def decide(
    database: Database,
    account: Account,
    report_id: str,
    body: ReviewRequest,
    key: str,
    request_id: str,
    storage_limit_bytes: int = STORAGE_LIMIT_BYTES,
) -> ReviewRecord:
    index = scoped_key(account.hospital_id, account.uid, report_id, "review", key)
    fingerprint = scoped_key(body.model_dump_json())
    review_id = uuid4().hex

    def change(tx: Transaction) -> ReviewRecord:
        case, report = review_access(tx, account, report_id)
        previous = tx.get("reviewKeys", index)
        if previous:
            if previous["fingerprint"] != fingerprint:
                raise conflict()
            return ReviewRecord.model_validate(tx.get("reviews", previous["reviewId"]))
        candidate = current_candidate(tx, case, report, body)
        record = ReviewRecord(
            review_id=review_id,
            version=report["reviewVersion"] + 1,
            report_id=report_id,
            reviewer_id=account.uid,
            reviewed_at=datetime.now(UTC),
            request=body,
            original_rows=tuple(
                row
                for row in candidate.rows
                if row.row_id in {item.row_id for item in body.corrections}
            ),
        )
        if body.decision == ReviewDecision.APPROVED:
            snapshot = ApprovedResult(
                report_id=report_id,
                analysis_id=candidate.analysis_id,
                analysis_version=candidate.version,
                review_id=review_id,
                reviewer_id=account.uid,
                reviewed_at=record.reviewed_at,
                rows=approved_rows(candidate, body),
                unresolved_acknowledgements=body.unresolved_acknowledgements,
                corrected_row_ids=tuple(item.row_id for item in body.corrections),
                summary=f"{len(candidate.rows)} laboratory rows reviewed.",
                provenance=candidate.provenance,
            )
            store_payload(
                tx,
                "approvedResults",
                report_id,
                snapshot.model_dump(mode="json", by_alias=True),
                account.hospital_id,
                report_id,
                storage_limit_bytes,
            )
            report["approvedAnalysisId"] = candidate.analysis_id
        case.update(
            reviewVersion=record.version,
            reviewStatus=body.decision.value,
            version=case["version"] + 1,
        )
        report.update(
            reviewVersion=record.version,
            reviewStatus=body.decision.value,
            caseVersion=case["version"],
        )
        tx.put("cases", report["caseId"], case)
        tx.put("reports", report_id, report)
        store_payload(
            tx,
            "reviews",
            review_id,
            record.model_dump(mode="json", by_alias=True),
            account.hospital_id,
            report_id,
            storage_limit_bytes,
        )
        tx.put("reviewIndex", review_id, {"hospitalId": account.hospital_id, "reportId": report_id})
        tx.put(
            "reviewKeys",
            index,
            {
                "fingerprint": fingerprint,
                "reviewId": review_id,
                "expiresAt": report.get("expiresAt"),
            },
        )
        audit(
            tx,
            review_id,
            account,
            report_id,
            "review_" + body.decision.value,
            request_id,
            analysisId=candidate.analysis_id,
            analysisVersion=candidate.version,
            reviewVersion=record.version,
            correctionCount=len(body.corrections),
            unresolvedCount=len(body.unresolved_acknowledgements),
        )
        return record

    return database.run(change)


def history(
    database: Database, account: Account, report_id: str, cursor: str | None, limit: int
) -> ReviewPage:
    database.run(lambda tx: review_access(tx, account, report_id))
    scope = page_scope(account, "reviews", report_id)
    page = database.scoped_page(
        "reviewIndex",
        {"hospitalId": account.hospital_id, "reportId": report_id},
        decode_cursor(cursor, scope),
        limit + 1,
    )

    def read(tx: Transaction) -> ReviewPage:
        review_access(tx, account, report_id)
        items = tuple(
            ReviewRecord.model_validate(tx.get("reviews", uid)) for uid, _ in page[:limit]
        )
        return ReviewPage(items=items, next_cursor=next_cursor(page, limit, scope))

    return database.run(read)
