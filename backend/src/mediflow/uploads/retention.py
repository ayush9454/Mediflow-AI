"""Resumable deletion of expired content; all writers independently fence expiry."""

from dataclasses import asdict
from datetime import datetime, timedelta
from typing import TYPE_CHECKING
from uuid import uuid4

from mediflow.authorization import AuditEvent
from mediflow.uploads.audit import record_audit
from mediflow.uploads.capacity import delete_payload
from mediflow.uploads.database import Record, Transaction

if TYPE_CHECKING:
    from mediflow.uploads import Uploads


class Retention:
    def __init__(self, uploads: "Uploads") -> None:
        self.uploads = uploads
        self.database = uploads.database

    def sweep(self, limit: int) -> int:
        now = self.uploads.clock()
        completed = 0
        marker = self.database.run(lambda tx: tx.get("retentionScans", "reports")) or {}
        page = self.database.page("reports", marker.get("after"), limit + 1)

        # Advance even after a storage failure so one object cannot starve the rest.
        def checkpoint_scan(tx: Transaction) -> None:
            current = tx.get("retentionScans", "reports") or {}
            if current == marker:
                tx.put(
                    "retentionScans",
                    "reports",
                    {"after": page[limit - 1][0] if len(page) > limit else None},
                )

        self.database.run(checkpoint_scan)
        for report_id, _ in page[:limit]:
            token = uuid4().hex

            def claim(
                tx: Transaction, report_id: str = report_id, token: str = token
            ) -> Record | None:
                report = tx.get("reports", report_id)
                if (
                    not report
                    or not report.get("expiresAt")
                    or report["expiresAt"] > now.isoformat()
                ):
                    return None
                task = tx.get("retentionTasks", report_id) or {"phase": 0}
                if task.get("leaseUntil", "") > now.isoformat():
                    return None
                task.update(token=token, leaseUntil=(now + timedelta(seconds=120)).isoformat())
                tx.put("retentionTasks", report_id, task)
                return {**report, "phase": task["phase"]}

            report = self.database.run(claim)
            if report is None:
                continue
            completed += self._step(report_id, report, token, now)
        for collection in (
            "reviewKeys",
            "beginReviewKeys",
            "assignmentKeys",
            "reprocessKeys",
            "reprocessQuotas",
            "reprocessRates",
            "uploadQuotas",
            "auditBudgets",
        ):
            for key in self.database.due(collection, "expiresAt", now.isoformat(), limit):

                def remove_expired(
                    tx: Transaction, collection: str = collection, key: str = key
                ) -> None:
                    data = tx.get(collection, key)
                    if data and data.get("expiresAt") and data["expiresAt"] <= now.isoformat():
                        tx.delete(collection, key)

                self.database.run(remove_expired)
        for key in self.database.due("auditEvents", "expires_at", now, limit):

            def remove_audit(tx: Transaction, key: str = key) -> None:
                data = tx.get("auditEvents", key)
                if data and data["expires_at"] <= now:
                    tx.delete("auditEvents", key)

            self.database.run(remove_audit)
        return completed

    def _owns(self, tx: Transaction, report_id: str, token: str) -> bool:
        task = tx.get("retentionTasks", report_id)
        return bool(task and task.get("token") == token)

    def _step(self, report_id: str, report: Record, token: str, now: datetime) -> bool:
        phase = report["phase"]
        collections = (
            "analyses",
            "reviews",
            "reviewIndex",
            "jobDispatches",
            "processingJobs",
            "uploadHashes",
        )
        if phase == 0:
            session = self.database.run(lambda tx: tx.get("uploadSessions", report_id)) or {}
            artifact = self.database.run(lambda tx: tx.get("sourceArtifacts", report_id)) or {}
            keys = set(session.get("attemptKeys", []))
            if artifact.get("objectKey"):
                keys.add(artifact["objectKey"])
            keys.update(self.uploads.documents.keys("reports/" + report_id + "/"))
            for key in keys:
                self.uploads.documents.delete(key)
        if phase < len(collections):
            collection = collections[phase]
            page = self.database.scoped_page(collection, {"reportId": report_id}, None, 100)
            for key, data in page:
                attempts = (
                    self.database.scoped_page("jobAttempts", {"jobId": key}, None, 4)
                    if collection in {"jobDispatches", "processingJobs"}
                    else []
                )

                def remove(
                    tx: Transaction,
                    key: str = key,
                    data: Record = data,
                    attempts: list[tuple[str, Record]] = attempts,
                ) -> None:
                    if not self._owns(tx, report_id, token):
                        return
                    delete_payload(tx, collection, key)
                    if collection == "analyses":
                        tx.delete("analysisCommits", key)
                    if collection in {"jobDispatches", "processingJobs"}:
                        for attempt_id, _ in attempts:
                            tx.delete("jobAttempts", attempt_id)
                        slot = tx.get("jobWorkerSlots", report["hospitalId"])
                        if slot and slot.get("jobId") == key:
                            tx.delete("jobWorkerSlots", report["hospitalId"])
                        tx.delete("processingJobs", key)
                        tx.delete("jobDispatches", key)
                        if data.get("analysisId"):
                            tx.delete("analysisCommits", data["analysisId"])

                self.database.run(remove)

            def checkpoint(tx: Transaction) -> None:
                if self._owns(tx, report_id, token):
                    tx.put("retentionTasks", report_id, {"phase": phase + (len(page) < 100)})

            self.database.run(checkpoint)
            return False

        def finish(tx: Transaction) -> bool:
            if not self._owns(tx, report_id, token):
                return False
            session = tx.get("uploadSessions", report_id)
            if session:
                capacity = tx.get("storageCapacity", report["hospitalId"])
                if capacity:
                    capacity["reservedBytes"] -= session.get("storageCharge", 0)
                    tx.put("storageCapacity", report["hospitalId"], capacity)
                tx.delete("uploadKeys", session["indexKey"])
            for collection, key in (
                ("reports", report_id),
                ("cases", report["caseId"]),
                ("sourceArtifacts", report_id),
                ("approvedResults", report_id),
                ("approvedSnapshots", report_id),
                ("jobHeads", report_id),
                ("uploadSessions", report_id),
                ("uploadGarbage", report_id),
                ("reprocessRates", report_id),
                ("retentionTasks", report_id),
            ):
                delete_payload(tx, collection, key)
            record_audit(
                tx,
                "report_expired_" + report_id,
                asdict(
                    AuditEvent(
                        None,
                        report["hospitalId"],
                        report_id,
                        "report_expired",
                        "deleted",
                        report_id,
                        occurred_at=now,
                        expires_at=now + timedelta(days=30),
                    )
                ),
            )
            return True

        return self.database.run(finish)
