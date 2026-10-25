"""Private upload lifecycle: verified originals, atomic quotas and durable job intent."""

import asyncio
import hashlib
import json
import tempfile
from collections.abc import AsyncIterator, Callable
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from threading import BoundedSemaphore
from typing import BinaryIO, Protocol
from uuid import uuid4

from starlette.concurrency import run_in_threadpool

from mediflow.authorization import AuditEvent
from mediflow.contracts import (
    Account,
    ErrorCode,
    ProcessingJob,
    ReportMetadata,
    ReportRegistration,
    UploadSession,
)
from mediflow.errors import ApplicationError
from mediflow.processing import process_pdf
from mediflow.uploads.audit import record_audit
from mediflow.uploads.capacity import ensure_capacity_ready
from mediflow.uploads.database import Database, MemoryDatabase, Record, Transaction

__all__ = ["Uploads", "MemoryDatabase", "MemoryDocuments"]
MAX_BYTES = 10_000_000
STORAGE_LIMIT_BYTES = 1_000_000_000


def scoped_key(*parts: str) -> str:
    return hashlib.sha256(json.dumps(parts).encode()).hexdigest()


def fail(code: ErrorCode, status: int, message: str) -> ApplicationError:
    return ApplicationError(code, status, message)


def live(session: Record, now: datetime) -> None:
    if datetime.fromisoformat(session["expiresAt"]) <= now:
        raise fail(ErrorCode.EXPIRED, 410, "This upload has expired. Start a new upload.")


class Documents(Protocol):
    def put(self, key: str, source: BinaryIO, size: int) -> None: ...
    def read(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...
    def keys(self, prefix: str) -> list[str]: ...


class MemoryDocuments:
    """Explicit private object-store fake; never selected from environment settings."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put(self, key: str, source: BinaryIO, size: int) -> None:
        if key in self.objects:
            raise fail(ErrorCode.CONFLICT, 409, "The source already exists.")
        self.objects[key] = source.read(size)

    def read(self, key: str) -> bytes:
        return self.objects[key]

    def delete(self, key: str) -> None:
        self.objects.pop(key, None)

    def keys(self, prefix: str) -> list[str]:
        return [key for key in self.objects if key.startswith(prefix)][:3]


class Uploads:
    def __init__(
        self,
        database: Database,
        documents: Documents,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        storage_limit_bytes: int = STORAGE_LIMIT_BYTES,
        accept_new_work: bool = True,
    ) -> None:
        if not 1 <= storage_limit_bytes <= STORAGE_LIMIT_BYTES:
            raise ValueError("Storage capacity must be between 1 and 1,000,000,000 bytes.")
        self.database = database
        self.documents = documents
        self.clock = clock
        self.storage_limit_bytes = storage_limit_bytes
        self.accept_new_work = accept_new_work
        self.stream_slot = BoundedSemaphore(1)

    def register(
        self, account: Account, body: ReportRegistration, key: str, request_id: str
    ) -> UploadSession:
        ensure_capacity_ready(self.database)
        now = self.clock()
        report = ReportMetadata(
            report_id=uuid4().hex,
            case_id=uuid4().hex,
            case_version=1,
            review_version=0,
            patient_id=account.uid,
            hospital_id=account.hospital_id,
            file_name=body.file_name,
            processing_status="upload_pending",
            created_at=now,
        )
        index_key = scoped_key(account.hospital_id, account.uid, key)
        session: Record = {
            "reportId": report.report_id,
            "requestId": request_id,
            "patientId": account.uid,
            "hospitalId": account.hospital_id,
            "caseId": report.case_id,
            "byteCount": body.byte_count,
            "expiresAt": (now + timedelta(hours=1)).isoformat(),
            "cleanupAt": (now + timedelta(hours=1)).isoformat(),
            "indexKey": index_key,
            "state": "pending",
            "attempts": 0,
            "objectKey": None,
            "attemptKeys": [],
            # Three immutable attempts can remain after uncertain storage writes.
            "storageCharge": 3 * body.byte_count,
            "request": body.model_dump(mode="json", by_alias=True),
        }

        def operation(tx: Transaction) -> UploadSession:
            previous = tx.get("uploadKeys", index_key)
            if previous is not None:
                existing = tx.get("uploadSessions", previous["reportId"])
                assert existing is not None
                live(existing, now)
                if existing["request"] != session["request"]:
                    raise fail(ErrorCode.CONFLICT, 409, "Use a new key for a different upload.")
                record = tx.get("reports", existing["reportId"])
                assert record is not None
                return self._session_response(existing, ReportMetadata.model_validate(record))
            if not self.accept_new_work:
                raise fail(
                    ErrorCode.TEMPORARILY_UNAVAILABLE, 503, "New uploads are temporarily stopped."
                )
            capacity = tx.get("storageCapacity", account.hospital_id) or {"reservedBytes": 0}
            if capacity["reservedBytes"] + session["storageCharge"] > self.storage_limit_bytes:
                raise fail(
                    ErrorCode.QUOTA_EXHAUSTED, 429, "The storage capacity limit has been reached."
                )
            reservations = tx.get("uploadReservations", account.hospital_id) or {"items": {}}
            items = reservations["items"]
            if len(items) >= 20 or sum(uid == account.uid for uid in items.values()) >= 5:
                raise fail(
                    ErrorCode.QUOTA_EXHAUSTED, 429, "Finish pending uploads or try again later."
                )
            # Admission limits bound duplicate/invalid reservation and audit churn too.
            day = now.strftime("%Y-%m-%d")
            admission_keys = [
                scoped_key("admission", account.hospital_id, day),
                scoped_key("admission", account.hospital_id, account.uid, day),
            ]
            admissions = [tx.get("uploadQuotas", k) or {"count": 0} for k in admission_keys]
            if admissions[0]["count"] >= 100 or admissions[1]["count"] >= 20:
                raise fail(
                    ErrorCode.QUOTA_EXHAUSTED, 429, "The upload reservation limit has been reached."
                )
            for admission_key, admission in zip(admission_keys, admissions, strict=True):
                tx.put(
                    "uploadQuotas",
                    admission_key,
                    {
                        "count": admission["count"] + 1,
                        "expiresAt": (now + timedelta(days=31)).isoformat(),
                    },
                )
            items[report.report_id] = account.uid
            capacity["reservedBytes"] += session["storageCharge"]
            tx.put("storageCapacity", account.hospital_id, capacity)
            tx.put("uploadReservations", account.hospital_id, reservations)
            tx.put("uploadKeys", index_key, {"reportId": report.report_id})
            tx.put("reports", report.report_id, report.model_dump(mode="json", by_alias=True))
            tx.put(
                "cases",
                report.case_id,
                {
                    "reportId": report.report_id,
                    "hospitalId": account.hospital_id,
                    "patientId": account.uid,
                    "version": 1,
                    "reviewVersion": 0,
                    "processingStatus": "upload_pending",
                    "reviewStatus": "not_ready",
                    "assignedDoctorId": None,
                    "createdAt": now.isoformat(),
                },
            )
            tx.put("uploadSessions", report.report_id, session)
            tx.put(
                "uploadGarbage",
                report.report_id,
                {
                    "sweepAt": session["cleanupAt"],
                    "until": (now + timedelta(days=31)).isoformat(),
                    "hospitalId": account.hospital_id,
                    "storageCharge": session["storageCharge"],
                },
            )
            self._audit(tx, report.report_id, session, "upload_registered", now)
            return self._session_response(session, report)

        return self.database.run(operation)

    @staticmethod
    def _session_response(session: Record, report: ReportMetadata) -> UploadSession:
        return UploadSession(
            report=report,
            upload_path=f"/api/v1/reports/{session['reportId']}/file",
            expires_at=datetime.fromisoformat(session["expiresAt"]),
        )

    def session(self, report_id: str) -> Record:
        data = self.database.run(lambda tx: tx.get("uploadSessions", report_id))
        if data is None:
            raise fail(ErrorCode.PERMISSION_DENIED, 403, "Access is denied.")
        return data

    def resolve(self, report_id: str) -> str:
        return str(self.session(report_id)["reportId"])

    def _claim(self, report_id: str, state: str, token: str) -> Record:
        now = self.clock()

        def operation(tx: Transaction) -> Record:
            session = tx.get("uploadSessions", report_id)
            if session is None:
                raise fail(ErrorCode.PERMISSION_DENIED, 403, "Access is denied.")
            live(session, now)
            if session["state"] in {"writing", "validating", "cleaning"}:
                if datetime.fromisoformat(session["leaseUntil"]) > now:
                    raise fail(ErrorCode.CONFLICT, 409, "This upload is busy. Try again shortly.")
                session["state"] = "uploaded" if session["state"] == "validating" else "pending"
            if session["state"] == "completed":
                return session
            if not self.accept_new_work:
                raise fail(
                    ErrorCode.TEMPORARILY_UNAVAILABLE, 503, "New uploads are temporarily stopped."
                )
            if state == "writing" and session["state"] == "uploaded":
                return session
            if state == "validating" and session["state"] != "uploaded":
                if session["state"] == "rejected":
                    raise fail(ErrorCode.INVALID_UPLOAD, 422, "The PDF is invalid or unsupported.")
                raise fail(ErrorCode.CONFLICT, 409, "Finish uploading the PDF first.")
            if state == "validating":
                if session.get("verificationAttempts", 0) >= 3:
                    raise fail(
                        ErrorCode.CONFLICT,
                        409,
                        "Start a new upload after three verification attempts.",
                    )
                session["verificationAttempts"] = session.get("verificationAttempts", 0) + 1
            if state == "writing":
                if session["attempts"] >= 3:
                    raise fail(ErrorCode.CONFLICT, 409, "Start a new upload after three attempts.")
                session["attempts"] += 1
            session.update(
                state=state, token=token, leaseUntil=(now + timedelta(seconds=360)).isoformat()
            )
            tx.put("uploadSessions", report_id, session)
            self._status(tx, report_id, "validating" if state == "validating" else "upload_pending")
            return session

        return self.database.run(operation)

    async def upload(self, report_id: str, chunks: AsyncIterator[bytes], content_type: str) -> None:
        if content_type.split(";", 1)[0].lower().strip() != "application/pdf":
            raise fail(ErrorCode.INVALID_UPLOAD, 422, "Upload an application/pdf document.")
        if not self.stream_slot.acquire(blocking=False):
            raise fail(
                ErrorCode.TEMPORARILY_UNAVAILABLE,
                503,
                "Another upload is active. Try again shortly.",
            )
        token = uuid4().hex
        claimed = False
        try:
            session = await run_in_threadpool(self.session, report_id)
            live(session, self.clock())
            count = 0
            with tempfile.TemporaryFile() as source:
                try:
                    async with asyncio.timeout(60):
                        async for chunk in chunks:
                            count += len(chunk)
                            if count > min(MAX_BYTES, session["byteCount"]):
                                raise fail(
                                    ErrorCode.INVALID_UPLOAD,
                                    413,
                                    "The PDF exceeds the upload limit.",
                                )
                            source.write(chunk)
                except TimeoutError:
                    raise fail(
                        ErrorCode.INVALID_UPLOAD, 408, "The upload timed out. Try again."
                    ) from None
                if count != session["byteCount"]:
                    raise fail(
                        ErrorCode.INVALID_UPLOAD, 422, "The upload is incomplete. Try again."
                    )
                session = await run_in_threadpool(self._claim, report_id, "writing", token)
                source.seek(0)
                if session["state"] in {"uploaded", "completed"}:
                    existing = await run_in_threadpool(
                        self.document
                        if session["state"] == "completed"
                        else lambda rid: self.documents.read(self.session(rid)["objectKey"]),
                        session["reportId"] if session["state"] == "completed" else report_id,
                    )
                    if hashlib.sha256(source.read()).digest() != hashlib.sha256(existing).digest():
                        raise fail(ErrorCode.CONFLICT, 409, "The uploaded PDF cannot be replaced.")
                    return
                claimed = True
                # The claim fences writers; retry removes any prior uncertain write first.
                if session["objectKey"]:
                    await run_in_threadpool(self.documents.delete, session["objectKey"])
                object_key = "reports/" + report_id + "/" + token + ".pdf"

                def store_path(tx: Transaction) -> None:
                    current = tx.get("uploadSessions", report_id)
                    if current is None or current.get("token") != token:
                        raise fail(ErrorCode.CONFLICT, 409, "The upload changed. Try again.")
                    current["objectKey"] = object_key
                    current["attemptKeys"].append(object_key)
                    garbage = tx.get("uploadGarbage", report_id)
                    if garbage is None:
                        tx.put(
                            "uploadGarbage",
                            report_id,
                            {
                                "sweepAt": current["cleanupAt"],
                                "until": (self.clock() + timedelta(days=30)).isoformat(),
                            },
                        )
                    tx.put("uploadSessions", report_id, current)

                await run_in_threadpool(self.database.run, store_path)
                await run_in_threadpool(self.documents.put, object_key, source, count)
                await run_in_threadpool(self._finish_claim, report_id, token, "uploaded")
        finally:
            try:
                if claimed:
                    await run_in_threadpool(
                        self._release_claim, report_id, token, "writing", "pending"
                    )
            finally:
                self.stream_slot.release()

    def _finish_claim(self, report_id: str, token: str, state: str) -> None:
        def operation(tx: Transaction) -> None:
            current = tx.get("uploadSessions", report_id)
            if current is None or current.get("token") != token:
                raise fail(ErrorCode.CONFLICT, 409, "The upload changed. Try again.")
            live(current, self.clock())
            current["state"] = state
            tx.put("uploadSessions", report_id, current)

        self.database.run(operation)

    def _release_claim(self, report_id: str, token: str, expected: str, state: str) -> None:
        def operation(tx: Transaction) -> None:
            current = tx.get("uploadSessions", report_id)
            if current and current.get("token") == token and current["state"] == expected:
                current["state"] = state
                tx.put("uploadSessions", report_id, current)
                self._status(tx, report_id, "upload_pending")

        self.database.run(operation)

    def complete(self, report_id: str, request_id: str) -> ProcessingJob:
        token = uuid4().hex
        session = self._claim(report_id, "validating", token)
        if session["state"] == "completed":
            return self._job(session["jobId"])
        try:
            source = self.documents.read(session["objectKey"])
            if len(source) != session["byteCount"] or len(source) > MAX_BYTES:
                raise fail(ErrorCode.INVALID_UPLOAD, 422, "The stored PDF size is invalid.")
            result = process_pdf(source)
            if result.outcome != "succeeded":
                if result.outcome == "failed":
                    raise fail(
                        ErrorCode.TEMPORARILY_UNAVAILABLE,
                        503,
                        "PDF verification is unavailable. Try again later.",
                    )

                def reject(tx: Transaction) -> None:
                    current = tx.get("uploadSessions", report_id)
                    if current is None or current.get("token") != token:
                        raise fail(ErrorCode.CONFLICT, 409, "The upload changed. Try again.")
                    current.update(state="rejected", requestId=request_id)
                    tx.put("uploadSessions", report_id, current)
                    self._status(tx, report_id, "rejected")
                    self._audit(tx, report_id, current, "upload_rejected", self.clock())

                self.database.run(reject)
                raise fail(
                    ErrorCode.INVALID_UPLOAD,
                    422,
                    "The PDF is invalid or unsupported: " + str(result.reason),
                )
            now = self.clock()
            job = ProcessingJob(
                job_id=uuid4().hex,
                report_id=report_id,
                status="queued",
                created_at=now,
                updated_at=now,
            )

            def operation(tx: Transaction) -> ProcessingJob:
                current = tx.get("uploadSessions", report_id)
                if (
                    current is None
                    or current.get("token") != token
                    or current["state"] != "validating"
                ):
                    raise fail(ErrorCode.CONFLICT, 409, "The upload changed. Try again.")
                live(current, now)
                report = tx.get("reports", report_id)
                assert report is not None
                hash_key = scoped_key(
                    report["hospitalId"], report["patientId"], result.source_sha256
                )
                duplicate = tx.get("uploadHashes", hash_key)
                if duplicate is not None:
                    existing = tx.get("reports", duplicate["reportId"])
                    if existing is not None and datetime.fromisoformat(existing["expiresAt"]) > now:
                        existing_job = ProcessingJob.model_validate(
                            tx.get("processingJobs", duplicate["jobId"])
                        )
                        current.update(
                            requestId=request_id,
                            state="completed",
                            reportId=existing_job.report_id,
                            jobId=existing_job.job_id,
                            duplicate=True,
                        )
                        tx.put("uploadSessions", report_id, current)
                        tx.delete("reports", report_id)
                        tx.delete("cases", report["caseId"])
                        self._audit(tx, report_id, current, "upload_duplicate", now)
                        return existing_job
                day = now.strftime("%Y-%m-%d")
                patient_key = scoped_key(report["hospitalId"], report["patientId"], day)
                hospital_key = scoped_key(report["hospitalId"], day)
                patient_quota = tx.get("uploadQuotas", patient_key) or {"count": 0}
                hospital_quota = tx.get("uploadQuotas", hospital_key) or {"count": 0}
                if patient_quota["count"] >= 5 or hospital_quota["count"] >= 20:
                    raise fail(
                        ErrorCode.QUOTA_EXHAUSTED, 429, "The daily upload limit has been reached."
                    )
                reservations = tx.get("uploadReservations", report["hospitalId"])
                assert reservations is not None
                reservations["items"].pop(report_id, None)
                tx.put("uploadReservations", report["hospitalId"], reservations)
                for quota_key, quota in [
                    (patient_key, patient_quota),
                    (hospital_key, hospital_quota),
                ]:
                    tx.put(
                        "uploadQuotas",
                        quota_key,
                        {
                            "count": quota["count"] + 1,
                            "expiresAt": (now + timedelta(days=31)).isoformat(),
                        },
                    )
                report.update(
                    pageCount=len(result.pages),
                    processingStatus="queued",
                    expiresAt=(now + timedelta(days=30)).isoformat(),
                )
                case = tx.get("cases", report["caseId"])
                assert case is not None
                case["processingStatus"] = "queued"
                tx.put("cases", report["caseId"], case)
                tx.put("reports", report_id, report)
                from mediflow.jobs import save_run

                save_run(tx, job, report)
                tx.put("uploadHashes", hash_key, {"reportId": report_id, "jobId": job.job_id})
                tx.put(
                    "sourceArtifacts",
                    report_id,
                    {
                        "objectKey": session["objectKey"],
                        "sha256": result.source_sha256,
                        "byteCount": len(source),
                    },
                )
                current.update(state="completed", jobId=job.job_id, expiresAt=report["expiresAt"])
                current.pop("cleanupAt", None)
                tx.put("uploadSessions", report_id, current)
                self._audit(tx, report_id, current, "upload_verified", now)
                return job

            completed = self.database.run(operation)
            if completed.report_id != report_id:
                # Keep the reservation occupied until duplicate bytes really are removed.
                self._discard_duplicate(report_id)
            return completed
        finally:
            self._release_claim(report_id, token, "validating", "uploaded")

    def _job(self, job_id: str) -> ProcessingJob:
        return ProcessingJob.model_validate(
            self.database.run(lambda tx: tx.get("processingJobs", job_id))
        )

    def document(self, report_id: str) -> bytes:
        def operation(tx: Transaction) -> Record:
            report = tx.get("reports", report_id)
            if report is None or report.get("expiresAt") is None:
                raise fail(ErrorCode.CONFLICT, 409, "The document is not verified yet.")
            live(report, self.clock())
            artifact = tx.get("sourceArtifacts", report_id)
            assert artifact is not None
            return artifact

        artifact = self.database.run(operation)
        source = self.documents.read(artifact["objectKey"])
        # A slow storage read must not carry content across the retention boundary.
        self.database.run(operation)
        if (
            len(source) != artifact["byteCount"]
            or hashlib.sha256(source).hexdigest() != artifact["sha256"]
        ):
            raise fail(
                ErrorCode.TEMPORARILY_UNAVAILABLE, 503, "Document integrity verification failed."
            )
        return source

    def _discard_duplicate(self, report_id: str) -> None:
        session = self.session(report_id)
        if session["objectKey"]:
            self.documents.delete(session["objectKey"])

        def operation(tx: Transaction) -> None:
            current = tx.get("uploadSessions", report_id)
            assert current is not None
            reservations = tx.get("uploadReservations", current["hospitalId"])
            assert reservations is not None
            reservations["items"].pop(report_id, None)
            current["objectKey"] = None
            tx.put("uploadReservations", current["hospitalId"], reservations)
            tx.put("uploadSessions", report_id, current)

        self.database.run(operation)

    def cleanup(self, limit: int = 100) -> int:
        if not 1 <= limit <= 100:
            raise ValueError("Cleanup limit must be between 1 and 100.")
        now = self.clock()
        count = 0
        for report_id in self.database.due("uploadSessions", "cleanupAt", now.isoformat(), limit):
            token = uuid4().hex

            def claim(
                tx: Transaction, report_id: str = report_id, token: str = token
            ) -> Record | None:
                session = tx.get("uploadSessions", report_id)
                if session is None or session.get("cleanupAt", now.isoformat()) > now.isoformat():
                    return None
                if session["state"] == "completed" and not session.get("duplicate"):
                    return None
                if (
                    session.get("leaseUntil")
                    and datetime.fromisoformat(session["leaseUntil"]) > now
                ):
                    return None
                session.update(
                    state="cleaning",
                    token=token,
                    leaseUntil=(now + timedelta(seconds=120)).isoformat(),
                )
                tx.put("uploadSessions", report_id, session)
                return session

            session = self.database.run(claim)
            if session is None:
                continue
            for object_key in session["attemptKeys"]:
                self.documents.delete(object_key)

            def remove(tx: Transaction, report_id: str = report_id, token: str = token) -> None:
                current = tx.get("uploadSessions", report_id)
                if current is None or current.get("token") != token:
                    raise fail(ErrorCode.CONFLICT, 409, "The upload changed. Try again.")
                reservations = tx.get("uploadReservations", current["hospitalId"])
                assert reservations is not None
                reservations["items"].pop(report_id, None)
                tx.put("uploadReservations", current["hospitalId"], reservations)
                tx.delete("uploadKeys", current["indexKey"])
                tx.delete("uploadSessions", report_id)
                if not current.get("duplicate"):
                    tx.delete("reports", report_id)
                    tx.delete("cases", current["caseId"])
                self._audit(tx, report_id, current, "upload_expired", now)

            self.database.run(remove)
            count += 1
        self._sweep_garbage(now, limit)
        from mediflow.uploads.retention import Retention

        return count + Retention(self).sweep(limit)

    def _sweep_garbage(self, now: datetime, limit: int) -> None:
        for report_id in self.database.due("uploadGarbage", "sweepAt", now.isoformat(), limit):

            def inspect(tx: Transaction, report_id: str = report_id) -> Record | None:
                session = tx.get("uploadSessions", report_id)
                if session is not None and session["state"] != "completed":
                    return None
                garbage = tx.get("uploadGarbage", report_id)
                if garbage is None:
                    return None
                artifact = tx.get("sourceArtifacts", report_id)
                return {**garbage, "keepKey": artifact["objectKey"] if artifact else None}

            record = self.database.run(inspect)
            if record is None:
                continue
            for object_key in self.documents.keys("reports/" + report_id + "/"):
                if object_key != record["keepKey"]:
                    self.documents.delete(object_key)

            sweep_record = record

            def reschedule(
                tx: Transaction, report_id: str = report_id, record: Record = sweep_record
            ) -> None:
                current = tx.get("uploadGarbage", report_id)
                if current is None:
                    return
                if (
                    datetime.fromisoformat(record["until"]) <= now
                    and tx.get("sourceArtifacts", report_id) is None
                    and tx.get("uploadSessions", report_id) is None
                ):
                    capacity = tx.get("storageCapacity", current.get("hospitalId", "legacy"))
                    if capacity:
                        capacity["reservedBytes"] -= current.get("storageCharge", 0)
                        tx.put("storageCapacity", current["hospitalId"], capacity)
                    tx.delete("uploadGarbage", report_id)
                else:
                    current["sweepAt"] = (now + timedelta(days=1)).isoformat()
                    tx.put(
                        "uploadGarbage",
                        report_id,
                        current,
                    )

            self.database.run(reschedule)

    @staticmethod
    def _status(tx: Transaction, report_id: str, status: str) -> None:
        report = tx.get("reports", report_id)
        assert report is not None
        case = tx.get("cases", report["caseId"])
        assert case is not None
        report["processingStatus"] = status
        case["processingStatus"] = status
        tx.put("reports", report_id, report)
        tx.put("cases", report["caseId"], case)

    @staticmethod
    def _audit(
        tx: Transaction, report_id: str, session: Record, action: str, now: datetime
    ) -> None:
        request_id = session["requestId"]
        record_audit(
            tx,
            action + "_" + report_id + "_" + request_id,
            asdict(
                AuditEvent(
                    actor_id=None if action == "upload_expired" else session["patientId"],
                    hospital_id=session["hospitalId"],
                    resource_id=report_id,
                    action=action,
                    outcome="allowed",
                    request_id=request_id,
                    occurred_at=now,
                    expires_at=now + timedelta(days=30),
                )
            ),
        )
