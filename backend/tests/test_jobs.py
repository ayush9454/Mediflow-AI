"""Durable job behavior at the coordinator boundary, using storage/clock fakes."""

from datetime import timedelta

import pytest
from test_uploads import complete, laboratory_pdf, register, setup_uploads, upload  # noqa: F401

from mediflow.jobs import Jobs


class Queue:
    def __init__(self):
        self.sent = []
        self.fail = False

    def send(self, job_id):
        self.sent.append(job_id)
        if self.fail:
            raise OSError("uncertain queue send")


@pytest.fixture(name="accepted")
def accepted_job(request):
    setup = request.getfixturevalue("setup_uploads")
    client, uploads, identities, documents = setup
    source = laboratory_pdf()
    session = register(client, source).json()
    assert upload(client, session, source).status_code == 204
    response = complete(client, session)
    assert response.status_code == 202
    queue = Queue()
    now = [uploads.clock()]
    uploads.clock = lambda: now[0]
    jobs = Jobs(uploads.database, queue, clock=lambda: now[0])
    return jobs, queue, now, response.json(), setup


def test_uncertain_dispatch_recovers_after_restart_without_losing_accepted_job(accepted):
    jobs, queue, now, job, _ = accepted
    queue.fail = True
    assert jobs.reconcile() == 0
    assert jobs.get(job["jobId"]).status == "queued"
    queue.fail = False
    now[0] += timedelta(seconds=61)
    restarted = Jobs(jobs.database, queue, clock=lambda: now[0])
    assert restarted.reconcile() == 1
    assert queue.sent == [job["jobId"], job["jobId"]]
    lease = restarted.claim(job["jobId"])
    assert lease is not None
    assert restarted.claim(job["jobId"]) is None
    assert restarted.get(job["jobId"]).attempt_count == 1


def test_transient_failures_use_backoff_and_stop_after_three_attempts(accepted):
    from mediflow.contracts import ErrorCode

    jobs, _, now, job, _ = accepted
    for delay in (30, 120, None):
        lease = jobs.claim(job["jobId"])
        assert lease is not None
        assert jobs.fail(lease, ErrorCode.TEMPORARILY_UNAVAILABLE, transient=True)
        assert jobs.claim(job["jobId"]) is None
        if delay:
            now[0] += timedelta(seconds=delay)
    assert jobs.get(job["jobId"]).status == "failed"
    assert jobs.get(job["jobId"]).attempt_count == 3
    assert jobs.reconcile() == 0


def candidate(lease, now):
    from mediflow.contracts import AnalysisCandidate, AnalysisProvenance

    return AnalysisCandidate(
        analysis_id=lease.analysis_id,
        report_id=lease.report_id,
        job_id=lease.job_id,
        version=lease.analysis_version,
        rows=(),
        created_at=now,
        provenance=AnalysisProvenance(
            pipeline_version=lease.pipeline_version,
            prompt_version="test-only",
            model_provider="test-only",
            model_version="test-only",
        ),
    )


def test_crashed_attempt_is_fenced_and_restart_commits_one_immutable_candidate(accepted):
    jobs, queue, now, job, _ = accepted
    old = jobs.claim(job["jobId"])
    now[0] += timedelta(seconds=331)
    restarted = Jobs(jobs.database, queue, clock=lambda: now[0])
    assert restarted.reconcile() == 0
    assert restarted.get(job["jobId"]).status == "queued"
    now[0] += timedelta(seconds=30)
    current = restarted.claim(job["jobId"])
    assert current is not None
    assert current.analysis_id == old.analysis_id
    assert not jobs.finish(old, candidate(old, now[0]))
    assert restarted.finish(current, candidate(current, now[0]))
    assert not restarted.finish(current, candidate(current, now[0]))
    assert restarted.candidate(job["jobId"]).analysis_id == current.analysis_id
    assert restarted.get(job["jobId"]).attempt_count == 2
    assert restarted.claim(job["jobId"]) is None


def test_reprocess_http_is_authorized_idempotent_and_keeps_approved_snapshot(accepted):
    from test_uploads import headers

    from mediflow.contracts import ErrorCode

    jobs, _, now, job, (client, uploads, _, _) = accepted
    lease = jobs.claim(job["jobId"])
    assert jobs.finish(lease, candidate(lease, now[0]))

    def assign_and_approve(tx):
        report = tx.get("reports", job["reportId"])
        report.update(
            assignedDoctorId="doctor_a",
            approvedAnalysisId=lease.analysis_id,
            reviewStatus="approved",
        )
        case = tx.get("cases", report["caseId"])
        case.update(assignedDoctorId="doctor_a", reviewStatus="approved")
        tx.put("cases", report["caseId"], case)
        tx.put("reports", job["reportId"], report)
        tx.put("approvedSnapshots", job["reportId"], {"analysisId": lease.analysis_id})

    uploads.database.run(assign_and_approve)
    client.app.state.jobs = jobs
    path = "/api/v1/reports/" + job["reportId"] + "/reprocess"
    body = {"expectedLatestAnalysisId": lease.analysis_id, "reason": "Check extraction again"}
    for uid in ("patient_a", "patient_b", "admin"):
        assert client.post(path, headers=headers(uid), json=body).status_code == 403
    response = client.post(path, headers=headers("doctor_a"), json=body)
    assert response.status_code == 202, response.text
    replacement = response.json()
    assert replacement["jobId"] != job["jobId"]
    assert client.post(path, headers=headers("doctor_a"), json=body).json() == replacement
    other = jobs.claim(replacement["jobId"])
    assert other.analysis_id != lease.analysis_id
    assert jobs.fail(other, ErrorCode.INVALID_UPLOAD)
    report = client.get("/api/v1/reports/" + job["reportId"], headers=headers()).json()
    assert report["approvedAnalysisId"] == lease.analysis_id
    assert report["reviewStatus"] == "approved"
    assert (
        client.post(
            path, headers=headers("doctor_a"), json={**body, "reason": "changed"}
        ).status_code
        == 409
    )


@pytest.mark.parametrize("during_processing", [False, True])
def test_expiry_is_terminal_and_stale_completion_cannot_regenerate_content(
    accepted, during_processing
):
    jobs, _, now, job, _ = accepted
    lease = jobs.claim(job["jobId"]) if during_processing else None
    now[0] += timedelta(days=31)
    if lease:
        assert not jobs.finish(lease, candidate(lease, now[0]))
    else:
        assert jobs.reconcile() == 0
    assert jobs.get(job["jobId"]).failure_code == "expired"
    assert jobs.claim(job["jobId"]) is None
    assert jobs.candidate(job["jobId"]) is None


def test_permanent_rejection_never_retries_and_failed_initial_run_can_be_reprocessed(accepted):
    from mediflow.contracts import ErrorCode, ReprocessingRequest

    jobs, _, now, job, (_, uploads, identities, _) = accepted
    lease = jobs.claim(job["jobId"])
    assert jobs.fail(lease, ErrorCode.INVALID_UPLOAD)
    assert jobs.get(job["jobId"]).status == "rejected"
    now[0] += timedelta(hours=1)
    assert jobs.reconcile() == 0
    assert jobs.claim(job["jobId"]) is None

    def assign(tx):
        report = tx.get("reports", job["reportId"])
        case = tx.get("cases", report["caseId"])
        case["assignedDoctorId"] = "doctor_a"
        tx.put("cases", report["caseId"], case)

    uploads.database.run(assign)
    body = ReprocessingRequest(expected_latest_analysis_id=None, reason="Retry failed initial run")
    replacement = jobs.reprocess(identities.accounts["doctor_a"], job["reportId"], body, "manual")
    assert replacement.job_id != job["jobId"]
    assert replacement.attempt_count == 0
    assert jobs.claim(replacement.job_id).analysis_version == 2


def test_reprocess_rechecks_assignment_and_bounds_cooldown_and_daily_runs(accepted):
    from mediflow.contracts import ErrorCode, ReprocessingRequest
    from mediflow.errors import ApplicationError

    jobs, _, now, job, (_, uploads, identities, _) = accepted
    doctor = identities.accounts["doctor_a"]
    body = ReprocessingRequest(
        expected_latest_analysis_id=None, reason="Retry unavailable provider"
    )
    assert jobs.fail(jobs.claim(job["jobId"]), ErrorCode.INTEGRATION_NOT_CONFIGURED)

    def assign(tx, uid="doctor_a"):
        report = tx.get("reports", job["reportId"])
        case = tx.get("cases", report["caseId"])
        case["assignedDoctorId"] = uid
        tx.put("cases", report["caseId"], case)

    uploads.database.run(assign)
    first = jobs.reprocess(doctor, job["reportId"], body, "first")
    assert jobs.fail(jobs.claim(first.job_id), ErrorCode.INVALID_UPLOAD)
    with pytest.raises(ApplicationError) as error:
        jobs.reprocess(doctor, job["reportId"], body, "too_soon")
    assert error.value.status_code == 429
    now[0] += timedelta(seconds=60)
    second = jobs.reprocess(doctor, job["reportId"], body, "second")
    assert jobs.fail(jobs.claim(second.job_id), ErrorCode.INVALID_UPLOAD)
    now[0] += timedelta(seconds=60)
    with pytest.raises(ApplicationError) as error:
        jobs.reprocess(doctor, job["reportId"], body, "daily_limit")
    assert error.value.status_code == 429
    uploads.database.run(lambda tx: assign(tx, "doctor_b"))
    with pytest.raises(ApplicationError) as error:
        jobs.reprocess(doctor, job["reportId"], body, "first")
    assert error.value.status_code == 403


def test_duplicate_completion_race_has_one_durable_candidate_and_audit_transition(accepted):
    from concurrent.futures import ThreadPoolExecutor

    jobs, _, now, job, _ = accepted
    lease = jobs.claim(job["jobId"])
    result = candidate(lease, now[0])
    with ThreadPoolExecutor(4) as pool:
        assert sum(pool.map(lambda _: jobs.finish(lease, result), range(4))) == 1
    assert jobs.candidate(job["jobId"]) == result
    assert jobs.get(job["jobId"]).status == "succeeded"


def test_configured_deadline_rejects_late_result_before_recovery_lease(accepted):
    jobs, queue, now, job, _ = accepted
    bounded = Jobs(jobs.database, queue, clock=lambda: now[0], deadline_seconds=1)
    lease = bounded.claim(job["jobId"])
    now[0] += timedelta(seconds=2)
    assert not bounded.finish(lease, candidate(lease, now[0]))
    assert bounded.get(job["jobId"]).status == "queued"
    assert bounded.get(job["jobId"]).attempt_count == 1


def test_legacy_accepted_intent_is_adopted_by_bounded_reconciliation(accepted):
    jobs, _, _, job, _ = accepted

    def legacy(tx):
        run = tx.get("jobDispatches", job["jobId"])
        tx.put(
            "jobDispatches",
            job["jobId"],
            {
                key: run[key]
                for key in (
                    "jobId",
                    "reportId",
                    "dispatchPending",
                    "createdAt",
                    "expiresAt",
                    "pipelineVersion",
                )
            },
        )
        tx.delete("jobHeads", job["reportId"])

    jobs.database.run(legacy)
    assert jobs.reconcile(limit=1) == 1
    lease = jobs.claim(job["jobId"])
    assert lease is not None
    assert lease.analysis_version == 1


def test_late_permanent_failure_is_fenced_by_the_persisted_deadline(accepted):
    from mediflow.contracts import ErrorCode

    jobs, _, now, job, _ = accepted
    lease = jobs.claim(job["jobId"])
    now[0] += timedelta(seconds=331)
    assert not jobs.fail(lease, ErrorCode.INVALID_UPLOAD)
    assert jobs.get(job["jobId"]).status == "queued"
    assert jobs.get(job["jobId"]).failure_code == "temporarily_unavailable"


def test_legacy_adoption_pages_past_current_intents_without_overwriting_heads(accepted):
    jobs, _, _, first, (client, _, _, _) = accepted
    source = laboratory_pdf("second report")
    session = register(client, source, key="second").json()
    assert upload(client, session, source).status_code == 204
    second = complete(client, session).json()
    target = max((first, second), key=lambda job: job["jobId"])

    def legacy(tx):
        run = tx.get("jobDispatches", target["jobId"])
        for key in (
            "analysisId",
            "analysisVersion",
            "configVersion",
            "nextDispatchAt",
            "nextAttemptAt",
        ):
            run.pop(key)
        tx.put("jobDispatches", target["jobId"], run)
        tx.delete("jobHeads", target["reportId"])

    jobs.database.run(legacy)
    assert jobs.migrate_legacy(limit=1) == 0
    assert jobs.migrate_legacy(limit=1) == 1
    assert jobs.migrate_legacy(limit=1) == 0
    assert jobs.claim(target["jobId"]) is not None


def test_processing_capacity_is_bounded_across_distinct_jobs(accepted):
    jobs, _, now, first, (client, _, _, _) = accepted
    source = laboratory_pdf("another report")
    session = register(client, source, key="second").json()
    assert upload(client, session, source).status_code == 204
    second = complete(client, session).json()
    lease = jobs.claim(first["jobId"])
    assert jobs.claim(second["jobId"]) is None
    assert jobs.get(second["jobId"]).attempt_count == 0
    assert jobs.finish(lease, candidate(lease, now[0]))
    assert jobs.claim(second["jobId"]) is not None


def test_execution_deadline_never_extends_beyond_source_retention(accepted):
    from datetime import datetime

    jobs, _, now, job, (_, uploads, _, _) = accepted
    expires = uploads.database.run(lambda tx: tx.get("reports", job["reportId"]))["expiresAt"]
    now[0] = datetime.fromisoformat(expires) - timedelta(seconds=5)
    lease = jobs.claim(job["jobId"])
    assert lease.deadline == datetime.fromisoformat(expires)


def test_administrator_diagnostics_expose_only_safe_correlated_operational_fields(accepted):
    from test_uploads import headers

    from mediflow.contracts import ErrorCode

    jobs, _, _, job, (client, _, _, _) = accepted
    client.app.state.jobs = jobs
    lease = jobs.claim(job["jobId"])
    assert jobs.fail(lease, ErrorCode.QUOTA_EXHAUSTED)
    path = "/api/v1/reports/" + job["reportId"] + "/operations"
    response = client.get(path, headers=headers("admin"))
    assert response.status_code == 200
    data = response.json()
    assert data["jobId"] == job["jobId"]
    assert data["attemptId"] == lease.attempt_id
    assert data["attemptCount"] == 1
    assert data["failureCode"] == "quota_exhausted"
    assert data["requestId"] == response.headers["x-request-id"]
    assert set(data) == {
        "schemaVersion",
        "reportId",
        "jobId",
        "attemptId",
        "attemptCount",
        "status",
        "failureCode",
        "updatedAt",
        "deadline",
        "requestId",
        "storageReservedBytes",
        "storageLimitBytes",
    }
    for uid in ("patient_a", "patient_b", "doctor_a"):
        assert client.get(path, headers=headers(uid)).status_code == 403


def test_service_stop_blocks_new_work_and_preserves_existing_private_reads(accepted):
    from test_uploads import headers

    jobs, queue, now, job, (client, uploads, _, _) = accepted
    uploads.accept_new_work = False
    stopped = Jobs(jobs.database, queue, clock=lambda: now[0], accept_new_work=False)
    assert stopped.reconcile() == 0
    assert stopped.claim(job["jobId"]) is None
    response = client.post(
        "/api/v1/reports",
        headers=headers(key="stopped"),
        json={
            "fileName": "new.pdf",
            "byteCount": 100,
            "syntheticDataAcknowledged": True,
        },
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "temporarily_unavailable"
    assert (
        client.get(f"/api/v1/reports/{job['reportId']}/document", headers=headers()).status_code
        == 200
    )
    assert jobs.claim(job["jobId"]) is not None
