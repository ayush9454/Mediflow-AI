"""Assignment and review behavior through authenticated HTTP and real transactions."""

import json
from pathlib import Path

import pytest
from test_uploads import headers, laboratory_pdf, register, setup_uploads  # noqa: F401


@pytest.fixture
def review_setup(request):
    client, uploads, identities, _ = request.getfixturevalue("setup_uploads")
    report = register(client, laboratory_pdf()).json()["report"]
    candidate = json.loads(
        (Path(__file__).parents[2] / "contracts/examples/analysis.json").read_text()
    )
    candidate["reportId"] = report["reportId"]
    candidate["sourcePages"] = [
        {
            "page": 1,
            "extractionMethod": "native",
            "originalText": (
                "Synthetic Marker <0.50 SYN-U 0.00–1.00\nSynthetic Marker <0.60 SYN-U 0.00–1.00"
            ),
            "nativeText": (
                "Synthetic Marker <0.50 SYN-U 0.00–1.00\nSynthetic Marker <0.60 SYN-U 0.00–1.00"
            ),
            "flags": [],
        }
    ]
    from datetime import UTC, datetime, timedelta

    report["expiresAt"] = (datetime.now(UTC) + timedelta(days=30)).isoformat()
    report.update(
        latestAnalysisId=candidate["analysisId"],
        pageCount=1,
        processingStatus="succeeded",
        reviewStatus="pending",
    )
    identities.accounts["doctor_b"] = identities.accounts["doctor_a"].model_copy(
        update={"uid": "doctor_b", "display_name": "Second doctor"}
    )

    def seed(tx):
        for account in identities.accounts.values():
            tx.put("users", account.uid, account.model_dump(mode="json", by_alias=True))
        tx.put("hospitals", "hospital_1", {"active": True})
        for uid in ("doctor_a", "doctor_b"):
            tx.put(
                "doctors",
                uid,
                {"hospitalId": "hospital_1", "active": True, "department": "Laboratory"},
            )
        tx.put("reports", report["reportId"], report)
        case = tx.get("cases", report["caseId"])
        case.update(processingStatus="succeeded", reviewStatus="pending")
        tx.put("cases", report["caseId"], case)
        tx.put("analyses", candidate["analysisId"], candidate)

    uploads.database.run(seed)
    return client, uploads, identities, report, candidate


def assign(client, report, doctor="doctor_a", version=1, key="assign"):
    return client.post(
        f"/api/v1/cases/{report['caseId']}/assignment",
        headers=headers("admin", key),
        json={"doctorId": doctor, "expectedCaseVersion": version},
    )


def test_administrator_lists_eligible_doctors_assigns_and_reassigns_without_clinical_access(
    review_setup,
):
    client, _, _, report, _ = review_setup
    page = client.get("/api/v1/cases?limit=1", headers=headers("admin"))
    assert page.status_code == 200
    assert page.json()["items"][0]["reportId"] == report["reportId"]
    doctors = client.get("/api/v1/doctors?limit=1", headers=headers("admin")).json()
    assert doctors["items"][0]["doctorId"] == "doctor_a"
    assert doctors["nextCursor"]
    assigned = assign(client, report)
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()["version"] == 2
    assert assign(client, report).json() == assigned.json()
    assert (
        client.get("/api/v1/cases", headers=headers("doctor_a")).json()["items"][0][
            "assignedDoctorId"
        ]
        == "doctor_a"
    )
    assert assign(client, report, "doctor_b", 2, "reassign").status_code == 200
    assert client.get("/api/v1/cases", headers=headers("doctor_a")).json()["items"] == []
    for suffix in ("result", "document", "reviews"):
        assert (
            client.get(
                f"/api/v1/reports/{report['reportId']}/{suffix}", headers=headers("admin")
            ).status_code
            == 403
        )
    assert "Synthetic Marker" not in page.text + assigned.text


def decision_body(candidate, case_version=2, review_version=0, **changes):
    return {
        "analysisId": candidate["analysisId"],
        "expectedAnalysisVersion": candidate["version"],
        "expectedCaseVersion": case_version,
        "expectedReviewVersion": review_version,
        "decision": "approved",
        **changes,
    }


def test_pending_and_reviewed_lists_follow_current_assignment_and_decisions(review_setup):
    client, _, _, report, candidate = review_setup
    assert assign(client, report).status_code == 200
    pending = client.get("/api/v1/cases?view=pending", headers=headers("doctor_a"))
    assert [item["reportId"] for item in pending.json()["items"]] == [report["reportId"]]
    assert (
        client.get("/api/v1/cases?view=reviewed", headers=headers("doctor_a")).json()["items"] == []
    )
    approved = client.post(
        f"/api/v1/reports/{report['reportId']}/review",
        headers=headers("doctor_a", "approve"),
        json=decision_body(candidate),
    )
    assert approved.status_code == 201, approved.text
    assert (
        client.get("/api/v1/cases?view=pending", headers=headers("doctor_a")).json()["items"] == []
    )
    assert (
        len(client.get("/api/v1/cases?view=reviewed", headers=headers("doctor_a")).json()["items"])
        == 1
    )
    assert (
        client.get("/api/v1/cases?view=unassigned", headers=headers("admin")).json()["items"] == []
    )
    assert (
        len(client.get("/api/v1/cases?view=assigned", headers=headers("admin")).json()["items"])
        == 1
    )
    assert assign(client, report, "doctor_b", 3, "reassign").status_code == 200
    assert (
        client.get("/api/v1/cases?view=reviewed", headers=headers("doctor_a")).json()["items"] == []
    )
    assert (
        len(client.get("/api/v1/cases?view=reviewed", headers=headers("doctor_b")).json()["items"])
        == 1
    )


def test_begin_review_and_duplicate_approval_create_one_attributed_snapshot_and_history(
    review_setup,
):
    from concurrent.futures import ThreadPoolExecutor

    client, _, _, report, candidate = review_setup
    assert assign(client, report).status_code == 200
    path = f"/api/v1/reports/{report['reportId']}"
    begin = {k: v for k, v in decision_body(candidate).items() if k != "decision"}
    started = client.post(path + "/begin-review", headers=headers("doctor_a", "begin"), json=begin)
    assert started.status_code == 200, started.text
    assert started.json()["reviewStatus"] == "under_review"
    assert started.json()["version"] == 3
    assert (
        client.post(path + "/begin-review", headers=headers("doctor_a", "begin"), json=begin).json()
        == started.json()
    )
    body = decision_body(candidate, case_version=3)
    with ThreadPoolExecutor(2) as pool:
        responses = list(
            pool.map(
                lambda _: client.post(
                    path + "/review", headers=headers("doctor_a", "approve"), json=body
                ),
                range(2),
            )
        )
    assert [r.status_code for r in responses] == [201, 201]
    assert responses[0].json() == responses[1].json()
    record = responses[0].json()
    assert record["reviewerId"] == "doctor_a" and record["version"] == 1
    result = client.get(path + "/result", headers=headers()).json()["approved"]
    assert result["reviewId"] == record["reviewId"]
    assert result["rows"] == candidate["rows"]
    history = client.get(path + "/reviews", headers=headers("doctor_a")).json()
    assert history["items"] == [record]
    assert (
        client.get(path + "/result?kind=draft", headers=headers("doctor_a")).json()["draft"]
        == candidate
    )
    stale = client.post(path + "/review", headers=headers("doctor_a", "different"), json=body)
    assert stale.status_code == 409


def test_blockers_need_real_field_correction_or_explicit_unresolved_reason(review_setup):
    from copy import deepcopy

    client, uploads, _, report, candidate = review_setup
    candidate["rows"][0]["issues"] = [
        {
            "issueId": "result_check",
            "field": "result",
            "code": "field_not_in_evidence",
            "severity": "blocking",
            "message": "Check printed value",
        }
    ]
    uploads.database.run(lambda tx: tx.put("analyses", candidate["analysisId"], candidate))
    assert assign(client, report).status_code == 200
    path = f"/api/v1/reports/{report['reportId']}"
    body = decision_body(candidate)
    silent = client.post(path + "/review", headers=headers("doctor_a", "silent"), json=body)
    assert silent.status_code == 422
    # Clearing the issue list alone cannot turn flagged data into corrected data.
    row = deepcopy(candidate["rows"][0])
    row["issues"] = []
    correction = {"rowId": "row_1", "correctedRow": row, "reason": "Checked source"}
    assert (
        client.post(
            path + "/review",
            headers=headers("doctor_a", "fake"),
            json={**body, "corrections": [correction]},
        ).status_code
        == 422
    )
    correction["correctedRow"]["result"] = "<0.60"
    assert (
        client.post(
            path + "/review",
            headers=headers("doctor_a", "unsupported"),
            json={**body, "corrections": [correction]},
        ).status_code
        == 422
    )
    correction["correctedRow"]["evidence"][0]["quotation"] = (
        "Synthetic Marker <0.60 SYN-U 0.00–1.00"
    )
    approved = client.post(
        path + "/review",
        headers=headers("doctor_a", "correct"),
        json={**body, "corrections": [correction]},
    )
    assert approved.status_code == 201, approved.text
    assert approved.json()["request"]["corrections"][0] == correction
    snapshot = client.get(path + "/result", headers=headers()).json()["approved"]
    assert snapshot["rows"][0]["result"] == "<0.60"
    assert snapshot["correctedRowIds"] == ["row_1"]
    assert snapshot["unresolvedAcknowledgements"] == []
    original = client.get(path + "/result?kind=draft", headers=headers("doctor_a")).json()["draft"]
    assert original == candidate


def test_qualified_approval_preserves_flag_and_reason_without_claiming_correction(review_setup):
    client, uploads, _, report, candidate = review_setup
    candidate["issues"] = [
        {
            "issueId": "quality",
            "field": "document",
            "code": "quality",
            "severity": "blocking",
            "message": "Scan is unclear",
        }
    ]
    uploads.database.run(lambda tx: tx.put("analyses", candidate["analysisId"], candidate))
    assert assign(client, report).status_code == 200
    path = f"/api/v1/reports/{report['reportId']}"
    body = decision_body(
        candidate,
        unresolvedAcknowledgements=[
            {
                "issueId": "quality",
                "reason": "Original scan remains unclear; simulated qualification",
            }
        ],
    )
    assert client.post(path + "/review", headers=headers("doctor_a"), json=body).status_code == 201
    snapshot = client.get(path + "/result", headers=headers()).json()["approved"]
    assert snapshot["unresolvedAcknowledgements"] == body["unresolvedAcknowledgements"]
    assert snapshot["correctedRowIds"] == []


@pytest.mark.parametrize(
    "change",
    [
        "inactive",
        "ineligible",
        "other_hospital",
        "role_changed",
        "expired",
        "reassigned",
        "new_analysis",
        "processing",
    ],
)
def test_stale_or_ineligible_review_cannot_write_even_after_prior_authorization(
    review_setup, change
):
    from datetime import UTC, datetime, timedelta

    client, uploads, _, report, candidate = review_setup
    assert assign(client, report).status_code == 200

    def mutate(tx):
        if change in {"inactive", "other_hospital", "role_changed"}:
            user = tx.get("users", "doctor_a")
            user[
                {"inactive": "active", "other_hospital": "hospitalId", "role_changed": "role"}[
                    change
                ]
            ] = {
                "inactive": False,
                "other_hospital": "hospital_other",
                "role_changed": "administrator",
            }[change]
            tx.put("users", "doctor_a", user)
        elif change == "ineligible":
            tx.put("doctors", "doctor_a", {"hospitalId": "hospital_1", "active": False})
        else:
            data = tx.get("reports", report["reportId"])
            case = tx.get("cases", report["caseId"])
            if change == "expired":
                data["createdAt"] = (datetime.now(UTC) - timedelta(days=2)).isoformat()
                data["expiresAt"] = (datetime.now(UTC) - timedelta(days=1)).isoformat()
            elif change == "reassigned":
                case["assignedDoctorId"] = "doctor_b"
                tx.put("cases", report["caseId"], case)
            elif change == "new_analysis":
                data["latestAnalysisId"] = "replacement"
            else:
                data["processingStatus"] = "processing"
            tx.put("reports", report["reportId"], data)

    uploads.database.run(mutate)
    response = client.post(
        f"/api/v1/reports/{report['reportId']}/review",
        headers=headers("doctor_a"),
        json=decision_body(candidate),
    )
    expected = (
        410 if change == "expired" else 409 if change in {"new_analysis", "processing"} else 403
    )
    assert response.status_code == expected
    assert client.get(
        f"/api/v1/reports/{report['reportId']}/result", headers=headers()
    ).status_code in {409, 410}


def test_assignment_and_review_race_never_lets_stale_doctor_overwrite(review_setup):
    from concurrent.futures import ThreadPoolExecutor

    client, _, _, report, candidate = review_setup
    assert assign(client, report).status_code == 200
    with ThreadPoolExecutor(2) as pool:
        assignment = pool.submit(assign, client, report, "doctor_b", 2, "reassign")
        review = pool.submit(
            client.post,
            f"/api/v1/reports/{report['reportId']}/review",
            headers=headers("doctor_a"),
            json=decision_body(candidate),
        )
    codes = (assignment.result().status_code, review.result().status_code)
    assert codes in {(200, 403), (200, 409), (409, 201)}
    if codes[0] == 200:
        assert (
            client.get(
                f"/api/v1/reports/{report['reportId']}/result", headers=headers()
            ).status_code
            == 409
        )


def test_rejected_and_failed_replacements_keep_previous_approval_until_fresh_approval(review_setup):
    from datetime import UTC, datetime, timedelta

    from test_jobs import Queue
    from test_jobs import candidate as job_candidate

    from mediflow.contracts import ErrorCode
    from mediflow.jobs import Jobs

    client, uploads, _, report, candidate = review_setup
    assert assign(client, report).status_code == 200
    path = f"/api/v1/reports/{report['reportId']}"
    approved = client.post(
        path + "/review", headers=headers("doctor_a", "original"), json=decision_body(candidate)
    )
    assert approved.status_code == 201
    original = client.get(path + "/result", headers=headers()).json()
    # Synthetic source already resides at the document boundary for reprocessing.
    uploads.database.run(
        lambda tx: tx.put(
            "sourceArtifacts", report["reportId"], {"objectKey": "synthetic", "byteCount": 100}
        )
    )
    now = [datetime.now(UTC)]
    jobs = Jobs(uploads.database, Queue(), clock=lambda: now[0])
    client.app.state.jobs = jobs
    current = candidate["analysisId"]
    for iteration in range(2):
        response = client.post(
            path + "/reprocess",
            headers=headers("doctor_a", f"retry_{iteration}"),
            json={"expectedLatestAnalysisId": current, "reason": "Verify replacement"},
        )
        assert response.status_code == 202, response.text
        lease = jobs.claim(response.json()["jobId"])
        if iteration == 0:
            assert jobs.finish(lease, job_candidate(lease, now[0]))
            metadata = client.get(path, headers=headers("doctor_a")).json()
            rejected = client.post(
                path + "/review",
                headers=headers("doctor_a", "reject"),
                json={
                    "analysisId": lease.analysis_id,
                    "expectedAnalysisVersion": lease.analysis_version,
                    "expectedCaseVersion": metadata["caseVersion"],
                    "expectedReviewVersion": 1,
                    "decision": "rejected",
                    "comment": "Replacement is not supported",
                },
            )
            assert rejected.status_code == 201, rejected.text
            current = lease.analysis_id
        else:
            assert jobs.fail(lease, ErrorCode.INVALID_UPLOAD)
        assert client.get(path + "/result", headers=headers()).json() == original
        now[0] += timedelta(seconds=61)
    history = client.get(path + "/reviews?limit=1", headers=headers("doctor_a")).json()
    assert len(history["items"]) == 1 and history["nextCursor"]
    following = client.get(
        path + "/reviews", params={"cursor": history["nextCursor"]}, headers=headers("doctor_a")
    ).json()
    assert {
        history["items"][0]["request"]["decision"],
        following["items"][0]["request"]["decision"],
    } == {"approved", "rejected"}


@pytest.mark.parametrize("change", ["inactive", "wrong_hospital", "not_doctor", "ineligible"])
def test_assignment_only_accepts_current_active_eligible_doctors(review_setup, change):
    client, uploads, _, report, _ = review_setup

    def mutate(tx):
        user = tx.get("users", "doctor_a")
        if change == "inactive":
            user["active"] = False
        elif change == "wrong_hospital":
            user["hospitalId"] = "other"
        elif change == "not_doctor":
            user["role"] = "patient"
        else:
            tx.put("doctors", "doctor_a", {"hospitalId": "hospital_1", "active": False})
        tx.put("users", "doctor_a", user)

    uploads.database.run(mutate)
    assert assign(client, report).status_code == 403
    assert "doctor_a" not in client.get("/api/v1/doctors", headers=headers("admin")).text


def test_reprocess_rechecks_server_doctor_activity_inside_accepting_transaction(review_setup):
    from test_jobs import Queue

    from mediflow.jobs import Jobs

    client, uploads, _, report, candidate = review_setup
    assert assign(client, report).status_code == 200
    client.app.state.jobs = Jobs(uploads.database, Queue())

    def deactivate(tx):
        user = tx.get("users", "doctor_a")
        user["active"] = False
        tx.put("users", "doctor_a", user)
        tx.put("sourceArtifacts", report["reportId"], {"objectKey": "synthetic"})

    uploads.database.run(deactivate)
    response = client.post(
        f"/api/v1/reports/{report['reportId']}/reprocess",
        headers=headers("doctor_a"),
        json={"expectedLatestAnalysisId": candidate["analysisId"], "reason": "Recheck"},
    )
    assert response.status_code == 403


def test_successful_replacement_needs_new_decision_and_atomically_replaces_approved_snapshot(
    review_setup,
):
    client, uploads, _, report, candidate = review_setup
    assert assign(client, report).status_code == 200
    path = f"/api/v1/reports/{report['reportId']}"
    first = client.post(
        path + "/review", headers=headers("doctor_a", "first"), json=decision_body(candidate)
    )
    assert first.status_code == 201
    original = client.get(path + "/result", headers=headers()).json()
    replacement = {**candidate, "analysisId": "replacement", "version": 2}

    def replace(tx):
        data = tx.get("reports", report["reportId"])
        case = tx.get("cases", report["caseId"])
        data.update(latestAnalysisId="replacement", reviewStatus="pending")
        case.update(reviewStatus="pending")
        tx.put("reports", report["reportId"], data)
        tx.put("cases", report["caseId"], case)
        tx.put("analyses", "replacement", replacement)

    uploads.database.run(replace)
    assert client.get(path + "/result", headers=headers()).json() == original
    new_body = decision_body(replacement, case_version=3, review_version=1)
    second = client.post(path + "/review", headers=headers("doctor_a", "second"), json=new_body)
    assert second.status_code == 201
    assert second.json()["version"] == 2
    snapshot = client.get(path + "/result", headers=headers()).json()["approved"]
    assert snapshot["analysisId"] == "replacement"
    assert snapshot["reviewId"] == second.json()["reviewId"]
    assert len(client.get(path + "/reviews", headers=headers("doctor_a")).json()["items"]) == 2


def test_correction_can_coexist_with_explicitly_unresolved_unchanged_field(review_setup):
    from copy import deepcopy

    client, uploads, _, report, candidate = review_setup
    row = candidate["rows"][0]
    row["unit"] = "UNCLEAR"
    row["issues"] = [
        {
            "issueId": "result_check",
            "field": "result",
            "code": "field_not_in_evidence",
            "severity": "blocking",
            "message": "Check value",
        },
        {
            "issueId": "unit_check",
            "field": "unit",
            "code": "field_not_in_evidence",
            "severity": "blocking",
            "message": "Unit is unclear",
        },
    ]
    uploads.database.run(lambda tx: tx.put("analyses", candidate["analysisId"], candidate))
    assert assign(client, report).status_code == 200
    corrected = deepcopy(row)
    corrected["result"] = "<0.60"
    corrected["evidence"][0]["quotation"] = "Synthetic Marker <0.60 SYN-U 0.00–1.00"
    body = decision_body(
        candidate,
        corrections=[
            {"rowId": "row_1", "correctedRow": corrected, "reason": "Source value verified"}
        ],
        unresolvedAcknowledgements=[
            {"issueId": "unit_check", "reason": "Printed unit remains unclear"}
        ],
    )
    path = f"/api/v1/reports/{report['reportId']}"
    response = client.post(path + "/review", headers=headers("doctor_a"), json=body)
    assert response.status_code == 201, response.text
    snapshot = client.get(path + "/result", headers=headers()).json()["approved"]
    assert snapshot["rows"][0]["result"] == "<0.60"
    assert snapshot["rows"][0]["issues"] == [row["issues"][1]]
    assert snapshot["unresolvedAcknowledgements"] == body["unresolvedAcknowledgements"]
    assert response.json()["originalRows"] == candidate["rows"]


def test_long_correction_field_returns_safe_validation_error_instead_of_internal_failure(
    review_setup,
):
    from copy import deepcopy

    client, _, _, report, candidate = review_setup
    assert assign(client, report).status_code == 200
    corrected = deepcopy(candidate["rows"][0])
    corrected["analyte"] = "S" * 501
    response = client.post(
        f"/api/v1/reports/{report['reportId']}/review",
        headers=headers("doctor_a"),
        json=decision_body(
            candidate,
            corrections=[
                {"rowId": "row_1", "correctedRow": corrected, "reason": "Source correction"}
            ],
        ),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"
