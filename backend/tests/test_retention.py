"""Retention through trusted cleanup, HTTP and durable worker boundaries."""

from datetime import timedelta

import pytest
from test_jobs import accepted_job, candidate  # noqa: F401
from test_reviews import review_setup  # noqa: F401
from test_uploads import headers, setup_uploads  # noqa: F401


@pytest.mark.parametrize("state", ["succeeded", "queued", "processing", "retrying"])
def test_cleanup_removes_verified_source_and_analysis_without_restoring_stale_work(accepted, state):
    from mediflow.contracts import ErrorCode

    jobs, queue, now, job, (client, uploads, _, documents) = accepted
    lease = jobs.claim(job["jobId"]) if state != "queued" else None
    if state == "succeeded":
        assert jobs.finish(lease, candidate(lease, now[0]))
    elif state == "retrying":
        assert jobs.fail(lease, ErrorCode.TEMPORARILY_UNAVAILABLE, transient=True)
    now[0] += timedelta(days=31)
    for _ in range(20):
        uploads.cleanup(limit=1)
    assert not documents.objects
    assert jobs.candidate(job["jobId"]) is None
    assert jobs.claim(job["jobId"]) is None
    if lease:
        assert not jobs.finish(lease, candidate(lease, now[0]))
    assert jobs.reconcile() == 0
    assert client.get("/api/v1/reports/" + job["reportId"], headers=headers()).status_code == 403
    for collection in (
        "reports",
        "cases",
        "sourceArtifacts",
        "analyses",
        "analysisCommits",
        "processingJobs",
        "jobDispatches",
        "jobAttempts",
        "jobHeads",
        "uploadSessions",
        "uploadKeys",
        "uploadHashes",
        "payloadCharges",
    ):
        assert uploads.database.page(collection, None, 100) == [], collection


def test_cleanup_removes_approved_reviews_and_retry_copies_but_preserves_minimal_audit(accepted):
    jobs, _, now, job, (client, uploads, _, _) = accepted
    client.app.state.jobs = jobs
    lease = jobs.claim(job["jobId"])
    assert jobs.finish(lease, candidate(lease, now[0]))
    report = client.get("/api/v1/reports/" + job["reportId"], headers=headers()).json()
    assert (
        client.post(
            f"/api/v1/cases/{report['caseId']}/assignment",
            headers=headers("admin"),
            json={"doctorId": "doctor_a", "expectedCaseVersion": 1},
        ).status_code
        == 200
    )
    body = {
        "analysisId": lease.analysis_id,
        "expectedAnalysisVersion": 1,
        "expectedCaseVersion": 2,
        "expectedReviewVersion": 0,
    }
    begun = client.post(
        f"/api/v1/reports/{job['reportId']}/begin-review",
        headers=headers("doctor_a"),
        json=body,
    )
    assert begun.status_code == 200, begun.text
    decision = client.post(
        f"/api/v1/reports/{job['reportId']}/review",
        headers=headers("doctor_a"),
        json={
            **body,
            "expectedCaseVersion": 3,
            "decision": "approved",
            "comment": "PRIVATE_REVIEW",
        },
    )
    assert decision.status_code == 201, decision.text
    assert (
        client.get(f"/api/v1/reports/{job['reportId']}/result", headers=headers()).status_code
        == 200
    )
    now[0] += timedelta(days=31)
    for _ in range(20):
        uploads.cleanup(limit=1)
    for collection in (
        "approvedResults",
        "reviews",
        "reviewIndex",
        "reviewKeys",
        "beginReviewKeys",
        "assignmentKeys",
    ):
        assert uploads.database.page(collection, None, 100) == [], collection
    events = uploads.database.page("auditEvents", None, 100)
    assert len(events) == 1
    assert events[0][1]["action"] == "report_expired"
    assert "PRIVATE_REVIEW" not in str(events)


def test_cleanup_resumes_after_partial_blob_failure_without_releasing_capacity_early(
    accepted, monkeypatch
):
    jobs, _, now, job, (client, uploads, _, documents) = accepted
    now[0] += timedelta(days=31)
    original_delete = documents.delete
    failed = False

    def uncertain_delete(key):
        nonlocal failed
        original_delete(key)
        if not failed:
            failed = True
            raise OSError("PRIVATE_CLOUD_EXCEPTION")

    monkeypatch.setattr(documents, "delete", uncertain_delete)
    uploads.cleanup(limit=1)
    assert uploads.cleanup_failures == 1
    capacity = uploads.database.run(lambda tx: tx.get("storageCapacity", "hospital_1"))
    assert capacity["reservedBytes"] > 0
    now[0] += timedelta(minutes=3)
    for _ in range(20):
        uploads.cleanup(limit=1)
    assert not documents.objects
    assert (
        uploads.database.run(lambda tx: tx.get("storageCapacity", "hospital_1"))["reservedBytes"]
        == 0
    )
    assert not jobs.claim(job["jobId"])


def test_orphan_capacity_stays_reserved_for_late_writes_and_is_eventually_released(request):
    from io import BytesIO

    from test_uploads import laboratory_pdf, register, upload

    from mediflow.uploads import Uploads

    client, original, _, documents = request.getfixturevalue("setup_uploads")
    source = laboratory_pdf()
    now = [original.clock()]
    uploads = Uploads(
        original.database, documents, clock=lambda: now[0], storage_limit_bytes=3 * len(source)
    )
    client.app.state.uploads = uploads
    session = register(client, source).json()
    assert upload(client, session, source).status_code == 204
    key = documents.keys("reports/")[0]
    now[0] += timedelta(hours=2)
    assert uploads.cleanup() == 1
    assert register(client, source, key="blocked").status_code == 429
    documents.put(key, BytesIO(source), len(source))
    now[0] += timedelta(days=32)
    uploads.cleanup()
    assert not documents.objects
    assert register(client, source, key="released").status_code == 201


def test_analysis_payloads_share_the_source_storage_ceiling_and_fail_safely(accepted):
    from mediflow.jobs import Jobs

    original, queue, now, job, (_, uploads, _, _) = accepted
    reserved = uploads.database.run(lambda tx: tx.get("storageCapacity", "hospital_1"))[
        "reservedBytes"
    ]
    jobs = Jobs(original.database, queue, clock=lambda: now[0], storage_limit_bytes=reserved)
    lease = jobs.claim(job["jobId"])
    assert not jobs.finish(lease, candidate(lease, now[0]))
    assert jobs.get(job["jobId"]).failure_code == "quota_exhausted"
    assert jobs.candidate(job["jobId"]) is None


def test_approval_cannot_bypass_storage_capacity_or_partially_publish_a_result(request):
    from test_reviews import assign, decision_body

    client, uploads, _, report, analysis = request.getfixturevalue("review_setup")
    assert assign(client, report).status_code == 200
    reserved = uploads.database.run(lambda tx: tx.get("storageCapacity", "hospital_1"))[
        "reservedBytes"
    ]
    uploads.storage_limit_bytes = reserved
    response = client.post(
        f"/api/v1/reports/{report['reportId']}/review",
        headers=headers("doctor_a"),
        json=decision_body(analysis),
    )
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "quota_exhausted"
    assert (
        client.get(f"/api/v1/reports/{report['reportId']}/result", headers=headers()).status_code
        == 409
    )
    assert (
        client.get(
            f"/api/v1/reports/{report['reportId']}/reviews", headers=headers("doctor_a")
        ).json()["items"]
        == []
    )


@pytest.mark.parametrize("limit", [1, 20])
def test_one_failing_report_does_not_starve_other_reports_in_small_cleanup_batches(
    accepted, monkeypatch, limit
):
    from test_uploads import complete, laboratory_pdf, register, upload

    _, _, now, first, (client, uploads, _, documents) = accepted
    source = laboratory_pdf("independent report")
    session = register(client, source, key="independent").json()
    assert upload(client, session, source).status_code == 204
    second = complete(client, session).json()
    bad, good = first["reportId"], second["reportId"]
    delete = documents.delete

    def fail_one_report(key):
        if key.startswith("reports/" + bad + "/"):
            raise OSError("one object is unavailable")
        delete(key)

    monkeypatch.setattr(documents, "delete", fail_one_report)
    now[0] += timedelta(days=31)
    from dataclasses import asdict

    from mediflow.authorization import AuditEvent

    def expired_audit_batch(tx):
        for number in range(70):
            tx.put(
                "auditEvents",
                f"expired_{number}",
                asdict(
                    AuditEvent(
                        None,
                        "hospital_1",
                        None,
                        "authenticate",
                        "denied",
                        f"audit_{number}",
                        occurred_at=now[0] - timedelta(days=31),
                        expires_at=now[0] - timedelta(days=1),
                    )
                ),
            )

    uploads.database.run(expired_audit_batch)
    for _ in range(30):
        uploads.cleanup(limit=limit)
        now[0] += timedelta(minutes=3)
    assert not documents.keys("reports/" + good + "/")
    assert documents.keys("reports/" + bad + "/")
    assert uploads.database.due("auditEvents", "expires_at", now[0], 100) == []


def test_cleanup_accepts_existing_seed_timestamps_and_continues_audit_expiry(accepted):
    _, _, now, job, (_, uploads, _, _) = accepted

    def seed(tx):
        report = tx.get("reports", job["reportId"])
        report.update(
            reportId="auth_fixture_report",
            caseId="auth_fixture_case",
            expiresAt=now[0] + timedelta(days=30),
        )
        tx.put("reports", "auth_fixture_report", report)

    uploads.database.run(seed)
    uploads.cleanup(limit=20)
    assert uploads.cleanup_failures == 0


def test_worker_rechecks_expiry_after_a_delayed_transaction_begins(accepted):
    from mediflow.jobs import Jobs

    jobs, queue, now, job, (_, uploads, _, _) = accepted
    lease = jobs.claim(job["jobId"])

    class DelayedDatabase:
        def run(self, operation):
            now[0] += timedelta(days=31)
            return uploads.database.run(operation)

    delayed = Jobs(DelayedDatabase(), queue, clock=lambda: now[0])
    assert not delayed.finish(lease, candidate(lease, now[0]))
    assert jobs.candidate(job["jobId"]) is None


@pytest.mark.parametrize("kind", ["orphan", "garbage", "mixed"])
def test_failed_orphan_or_prefix_does_not_starve_another_source_in_small_batches(
    request, monkeypatch, kind
):
    from io import BytesIO

    from test_uploads import laboratory_pdf, register, upload

    client, uploads, _, documents = request.getfixturevalue("setup_uploads")
    now = [uploads.clock()]
    uploads.clock = lambda: now[0]
    sources = []
    for number in range(2):
        source = laboratory_pdf(str(number))
        session = register(client, source, key=f"orphan_{number}").json()
        assert upload(client, session, source).status_code == 204
        prefix = f"reports/{session['report']['reportId']}/"
        sources.append((prefix, documents.keys(prefix)[0], source))
    now[0] += timedelta(hours=2)
    delete = documents.delete

    def unavailable(key):
        if key.startswith(sources[0][0]):
            raise OSError("isolated source unavailable")
        delete(key)

    monkeypatch.setattr(documents, "delete", unavailable)
    if kind in {"garbage", "mixed"}:
        if kind == "garbage":
            monkeypatch.setattr(documents, "delete", delete)
        assert uploads.cleanup(limit=20) == (2 if kind == "garbage" else 1)
        for _, key, source in sources if kind == "garbage" else sources[1:]:
            documents.put(key, BytesIO(source), len(source))
        now[0] += timedelta(days=32 if kind == "mixed" else 1)
        monkeypatch.setattr(documents, "delete", unavailable)
    for _ in range(10):
        uploads.cleanup(limit=1)
        now[0] += timedelta(minutes=5)
    assert documents.keys(sources[0][0])
    assert not documents.keys(sources[1][0])
    if kind == "mixed":
        assert uploads.database.run(lambda tx: tx.get("storageCapacity", "hospital_1"))[
            "reservedBytes"
        ] == 3 * len(sources[0][2])
