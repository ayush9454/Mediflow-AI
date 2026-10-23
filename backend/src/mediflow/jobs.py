"""Firestore-authoritative logical runs; queue delivery never owns execution state."""

from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from mediflow.authorization import AuditEvent
from mediflow.contracts import (
    Account,
    AnalysisCandidate,
    ErrorCode,
    ProcessingJob,
    ReprocessingRequest,
    Role,
)
from mediflow.job_queue import Queue
from mediflow.uploads import fail, scoped_key
from mediflow.uploads.database import Database, Record, Transaction

TERMINAL = {"succeeded", "failed", "rejected"}


def save_run(tx: Transaction, job: ProcessingJob, report: Record, version: int = 1) -> None:
    """Part of the accepting transaction, including the initial upload quota charge."""
    now = job.created_at.isoformat()
    tx.put("processingJobs", job.job_id, job.model_dump(mode="json", by_alias=True))
    tx.put(
        "jobDispatches",
        job.job_id,
        {
            "jobId": job.job_id,
            "reportId": job.report_id,
            "hospitalId": report["hospitalId"],
            "patientId": report["patientId"],
            "dispatchPending": True,
            "createdAt": now,
            "nextDispatchAt": now,
            "nextAttemptAt": now,
            "expiresAt": report["expiresAt"],
            "pipelineVersion": "laboratory-v1",
            "configVersion": "jobs-v1",
            "analysisId": uuid4().hex,
            "analysisVersion": version,
        },
    )
    tx.put("jobHeads", job.report_id, {"jobId": job.job_id, "analysisVersion": version})


@dataclass(frozen=True)
class Lease:
    job_id: str
    report_id: str
    attempt_id: str
    analysis_id: str
    analysis_version: int
    pipeline_version: str
    config_version: str
    deadline: datetime


class Jobs:
    def __init__(
        self,
        database: Database,
        queue: Queue,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        deadline_seconds: int = 270,
    ) -> None:
        if not 1 <= deadline_seconds <= 270:
            raise ValueError("The job deadline must be between 1 and 270 seconds.")
        self.database = database
        self.queue = queue
        self.clock = clock
        self.deadline_seconds = deadline_seconds

    def get(self, job_id: str) -> ProcessingJob:
        return ProcessingJob.model_validate(
            self.database.run(lambda tx: tx.get("processingJobs", job_id))
        )

    @staticmethod
    def _status(tx: Transaction, report: Record, status: str) -> None:
        case = tx.get("cases", report["caseId"])
        report["processingStatus"] = status
        tx.put("reports", report["reportId"], report)
        if case is not None:
            case["processingStatus"] = status
            tx.put("cases", report["caseId"], case)

    @staticmethod
    def _audit(tx: Transaction, run: Record, action: str, now: datetime) -> None:
        tx.put(
            "auditEvents",
            action + "_" + run["jobId"],
            asdict(
                AuditEvent(
                    run.get("actorId"),
                    run["hospitalId"],
                    run["reportId"],
                    action,
                    "allowed",
                    run["jobId"],
                    occurred_at=now,
                    expires_at=now + timedelta(days=30),
                )
            ),
        )

    def reconcile(self, limit: int = 20) -> int:
        if not 1 <= limit <= 100:
            raise ValueError("Reconciliation limit must be between 1 and 100.")
        dispatched = 0
        for job_id in self.database.due(
            "jobDispatches", "nextDispatchAt", self.clock().isoformat(), limit
        ):
            now = self.clock()
            token = uuid4().hex

            def reserve(
                tx: Transaction,
                job_id: str = job_id,
                now: datetime = now,
                token: str = token,
            ) -> bool:
                run = tx.get("jobDispatches", job_id)
                job = tx.get("processingJobs", job_id)
                if not run or not job or job["status"] in TERMINAL:
                    return False
                if run.get("nextDispatchAt", "9999") > now.isoformat():
                    return False
                report = tx.get("reports", run["reportId"])
                if self._expired(tx, job, run, report, now):
                    return False
                if job["status"] == "processing":
                    if run["leaseUntil"] <= now.isoformat():
                        self._failure(
                            tx, job, run, report, ErrorCode.TEMPORARILY_UNAVAILABLE, True, now
                        )
                    return False
                if job["status"] != "queued":
                    return False
                run.update(
                    dispatchToken=token,
                    dispatchPending=True,
                    nextDispatchAt=(now + timedelta(seconds=60)).isoformat(),
                )
                tx.put("jobDispatches", job_id, run)
                return True

            if not self.database.run(reserve):
                continue
            try:
                self.queue.send(job_id)
            except Exception:
                # The persisted claim expires even if sending succeeded before interruption.
                continue

            def sent(
                tx: Transaction,
                job_id: str = job_id,
                now: datetime = now,
                token: str = token,
            ) -> None:
                run = tx.get("jobDispatches", job_id)
                job = tx.get("processingJobs", job_id)
                if run and job and run.get("dispatchToken") == token and job["status"] == "queued":
                    run.update(
                        dispatchPending=False,
                        nextDispatchAt=(now + timedelta(seconds=300)).isoformat(),
                    )
                    tx.put("jobDispatches", job_id, run)

            self.database.run(sent)
            dispatched += 1
        return dispatched

    def claim(self, job_id: str) -> Lease | None:
        now = self.clock()

        def operation(tx: Transaction) -> Lease | None:
            run = tx.get("jobDispatches", job_id)
            job = tx.get("processingJobs", job_id)
            if not run or not job or job["status"] != "queued":
                return None
            if run["nextAttemptAt"] > now.isoformat():
                return None
            report = tx.get("reports", run["reportId"])
            if self._expired(tx, job, run, report, now):
                return None
            head = tx.get("jobHeads", run["reportId"])
            if not head or head["jobId"] != job_id or job["attemptCount"] >= 3:
                return None
            assert report is not None
            count = job["attemptCount"] + 1
            attempt_id = job_id + "_" + str(count)
            deadline = now + timedelta(seconds=self.deadline_seconds)
            run.update(
                attemptId=attempt_id,
                deadline=deadline.isoformat(),
                configVersion=f"jobs-v1-timeout-{self.deadline_seconds}",
                leaseUntil=(now + timedelta(seconds=330)).isoformat(),
                nextDispatchAt=(now + timedelta(seconds=330)).isoformat(),
            )
            job.update(status="processing", attemptCount=count, updatedAt=now.isoformat())
            tx.put(
                "jobAttempts",
                attempt_id,
                {
                    "jobId": job_id,
                    "attemptId": attempt_id,
                    "startedAt": now.isoformat(),
                    "deadline": deadline.isoformat(),
                    "status": "processing",
                    "pipelineVersion": run["pipelineVersion"],
                    "configVersion": run["configVersion"],
                },
            )
            tx.put("processingJobs", job_id, job)
            tx.put("jobDispatches", job_id, run)
            self._status(tx, report, "processing")
            return Lease(
                job_id,
                run["reportId"],
                attempt_id,
                run["analysisId"],
                run["analysisVersion"],
                run["pipelineVersion"],
                run["configVersion"],
                deadline,
            )

        return self.database.run(operation)

    def _expired(
        self,
        tx: Transaction,
        job: Record,
        run: Record,
        report: Record | None,
        now: datetime,
    ) -> bool:
        if (
            report is None
            or run["expiresAt"] <= now.isoformat()
            or not report.get("expiresAt")
            or report["expiresAt"] <= now.isoformat()
        ):
            self._failure(tx, job, run, report, ErrorCode.EXPIRED, False, now)
            return True
        return False

    def _failure(
        self,
        tx: Transaction,
        job: Record,
        run: Record,
        report: Record | None,
        code: ErrorCode,
        transient: bool,
        now: datetime,
    ) -> None:
        retry = transient and job["attemptCount"] < 3
        status = "queued" if retry else "rejected" if code == ErrorCode.INVALID_UPLOAD else "failed"
        job.update(status=status, failureCode=code.value, updatedAt=now.isoformat())
        attempt = tx.get("jobAttempts", run.get("attemptId", "missing"))
        if attempt:
            attempt.update(status="failed", finishedAt=now.isoformat(), failureCode=code.value)
            tx.put("jobAttempts", run["attemptId"], attempt)
        if retry:
            delay = (30, 120)[job["attemptCount"] - 1]
            run.update(
                dispatchPending=True,
                nextAttemptAt=(now + timedelta(seconds=delay)).isoformat(),
                nextDispatchAt=(now + timedelta(seconds=delay)).isoformat(),
            )
        else:
            run.pop("nextDispatchAt", None)
            run["dispatchPending"] = False
            self._audit(tx, run, "processing_" + status, now)
        tx.put("processingJobs", run["jobId"], job)
        tx.put("jobDispatches", run["jobId"], run)
        if report:
            self._status(tx, report, status)

    def fail(self, lease: Lease, code: ErrorCode, *, transient: bool = False) -> bool:
        now = self.clock()

        def operation(tx: Transaction) -> bool:
            run = tx.get("jobDispatches", lease.job_id)
            job = tx.get("processingJobs", lease.job_id)
            if (
                not run
                or not job
                or job["status"] != "processing"
                or run.get("attemptId") != lease.attempt_id
            ):
                return False
            report = tx.get("reports", lease.report_id)
            if self._expired(tx, job, run, report, now):
                return False
            self._failure(tx, job, run, report, code, transient, now)
            return True

        return self.database.run(operation)

    def finish(self, lease: Lease, candidate: AnalysisCandidate) -> bool:
        if (
            candidate.job_id != lease.job_id
            or candidate.report_id != lease.report_id
            or candidate.analysis_id != lease.analysis_id
            or candidate.version != lease.analysis_version
            or candidate.provenance.pipeline_version != lease.pipeline_version
        ):
            raise ValueError("Candidate does not belong to this logical run.")
        now = self.clock()

        def operation(tx: Transaction) -> bool:
            run = tx.get("jobDispatches", lease.job_id)
            job = tx.get("processingJobs", lease.job_id)
            if (
                not run
                or not job
                or job["status"] != "processing"
                or run.get("attemptId") != lease.attempt_id
            ):
                return False
            report = tx.get("reports", lease.report_id)
            if self._expired(tx, job, run, report, now):
                return False
            assert report is not None
            head = tx.get("jobHeads", lease.report_id)
            if not head or head["jobId"] != lease.job_id:
                return False
            if now >= datetime.fromisoformat(run["deadline"]):
                self._failure(tx, job, run, report, ErrorCode.TEMPORARILY_UNAVAILABLE, True, now)
                return False
            if tx.get("analyses", lease.analysis_id) is not None:
                return False
            tx.put("analyses", lease.analysis_id, candidate.model_dump(mode="json", by_alias=True))
            tx.put(
                "analysisCommits",
                lease.analysis_id,
                {
                    "jobId": lease.job_id,
                    "attemptId": lease.attempt_id,
                    "configVersion": lease.config_version,
                    "createdAt": now.isoformat(),
                },
            )
            job.update(status="succeeded", failureCode=None, updatedAt=now.isoformat())
            run.pop("nextDispatchAt", None)
            run["dispatchPending"] = False
            attempt = tx.get("jobAttempts", lease.attempt_id)
            assert attempt is not None
            attempt.update(status="succeeded", finishedAt=now.isoformat())
            tx.put("jobAttempts", lease.attempt_id, attempt)
            tx.put("processingJobs", lease.job_id, job)
            tx.put("jobDispatches", lease.job_id, run)
            report.update(latestAnalysisId=lease.analysis_id, reviewStatus="pending")
            case = tx.get("cases", report["caseId"])
            if case:
                case["reviewStatus"] = "pending"
                tx.put("cases", report["caseId"], case)
            self._status(tx, report, "succeeded")
            self._audit(tx, run, "processing_succeeded", now)
            return True

        return self.database.run(operation)

    def candidate(self, job_id: str) -> AnalysisCandidate | None:
        def operation(tx: Transaction) -> AnalysisCandidate | None:
            run = tx.get("jobDispatches", job_id)
            if run is None or datetime.fromisoformat(run["expiresAt"]) <= self.clock():
                return None
            data = tx.get("analyses", run["analysisId"])
            return AnalysisCandidate.model_validate(data) if data else None

        return self.database.run(operation)

    def reprocess(
        self,
        account: Account,
        report_id: str,
        body: ReprocessingRequest,
        key: str,
    ) -> ProcessingJob:
        now = self.clock()
        index = scoped_key(account.hospital_id, account.uid, report_id, key)
        fingerprint = scoped_key(body.model_dump_json())
        job_id = uuid4().hex

        def operation(tx: Transaction) -> ProcessingJob:
            report = tx.get("reports", report_id)
            case = tx.get("cases", report["caseId"]) if report else None
            if (
                not report
                or not case
                or not account.active
                or account.role != Role.DOCTOR
                or report["hospitalId"] != account.hospital_id
                or case.get("hospitalId") != account.hospital_id
                or case.get("reportId") != report_id
                or case.get("assignedDoctorId") != account.uid
            ):
                raise fail(ErrorCode.PERMISSION_DENIED, 403, "Access is denied.")
            if not report.get("expiresAt") or datetime.fromisoformat(report["expiresAt"]) <= now:
                raise fail(ErrorCode.EXPIRED, 410, "This source has expired.")
            previous = tx.get("reprocessKeys", index)
            if previous:
                if previous["fingerprint"] != fingerprint:
                    raise fail(ErrorCode.CONFLICT, 409, "Use a new key for a different operation.")
                return ProcessingJob.model_validate(tx.get("processingJobs", previous["jobId"]))
            if report.get("latestAnalysisId") != body.expected_latest_analysis_id:
                raise fail(
                    ErrorCode.CONFLICT, 409, "Refresh the latest analysis before reprocessing."
                )
            if tx.get("sourceArtifacts", report_id) is None:
                raise fail(ErrorCode.EXPIRED, 410, "This source is no longer available.")
            head = tx.get("jobHeads", report_id)
            if head:
                active = tx.get("processingJobs", head["jobId"])
                if active and active["status"] not in TERMINAL:
                    raise fail(ErrorCode.CONFLICT, 409, "Processing is already active.")
            quota_key = scoped_key(report_id, now.strftime("%Y-%m-%d"))
            quota = tx.get("reprocessQuotas", quota_key) or {"count": 0}
            rate = tx.get("reprocessRates", report_id)
            if quota["count"] >= 2 or (rate and datetime.fromisoformat(rate["nextAt"]) > now):
                raise fail(ErrorCode.QUOTA_EXHAUSTED, 429, "Try reprocessing again later.")
            job = ProcessingJob(
                job_id=job_id, report_id=report_id, status="queued", created_at=now, updated_at=now
            )
            save_run(tx, job, report, head["analysisVersion"] + 1 if head else 1)
            tx.put(
                "reprocessKeys",
                index,
                {"jobId": job_id, "fingerprint": fingerprint, "expiresAt": report["expiresAt"]},
            )
            tx.put(
                "reprocessQuotas",
                quota_key,
                {"count": quota["count"] + 1, "expiresAt": report["expiresAt"]},
            )
            tx.put(
                "reprocessRates",
                report_id,
                {
                    "nextAt": (now + timedelta(seconds=60)).isoformat(),
                    "expiresAt": report["expiresAt"],
                },
            )
            self._status(tx, report, "queued")
            self._audit(
                tx,
                {
                    "jobId": job_id,
                    "reportId": report_id,
                    "hospitalId": report["hospitalId"],
                    "actorId": account.uid,
                },
                "reprocess_requested",
                now,
            )
            return job

        return self.database.run(operation)
