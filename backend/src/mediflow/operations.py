"""Trusted operational metadata without document, review or provider payloads."""

from mediflow.contracts import Account, OperationalStatus, Role
from mediflow.uploads.database import Database, Transaction
from mediflow.workflow import active_account, case_report, unexpired


def status(
    database: Database, account: Account, report_id: str, request_id: str, storage_limit: int
) -> OperationalStatus:
    def read(tx: Transaction) -> OperationalStatus:
        active_account(tx, account, Role.ADMINISTRATOR)
        _, report = case_report(tx, account, report_id)
        unexpired(report)
        head = tx.get("jobHeads", report_id)
        job = tx.get("processingJobs", head["jobId"]) if head else None
        run = tx.get("jobDispatches", head["jobId"]) if head else None
        capacity = tx.get("storageCapacity", account.hospital_id) or {"reservedBytes": 0}
        return OperationalStatus(
            report_id=report_id,
            job_id=job["jobId"] if job else None,
            attempt_id=run.get("attemptId") if run else None,
            attempt_count=job["attemptCount"] if job else 0,
            status=report["processingStatus"],
            failure_code=job.get("failureCode") if job else None,
            updated_at=job["updatedAt"] if job else None,
            deadline=run.get("deadline") if run else None,
            request_id=request_id,
            storage_reserved_bytes=capacity["reservedBytes"],
            storage_limit_bytes=storage_limit,
        )

    return database.run(read)
