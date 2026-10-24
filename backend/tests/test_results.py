"""Result/evidence behavior through authenticated HTTP, with storage-boundary fixtures."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from test_uploads import headers, laboratory_pdf, register, setup_uploads  # noqa: F401


@pytest.fixture
def result_setup(request):
    client, uploads, identities, _ = request.getfixturevalue("setup_uploads")
    report = register(client, laboratory_pdf()).json()["report"]
    candidate = json.loads(
        (Path(__file__).parents[2] / "contracts/examples/analysis.json").read_text()
    )
    candidate["reportId"] = report["reportId"]
    report.update(
        assignedDoctorId="doctor_a", latestAnalysisId=candidate["analysisId"], pageCount=1
    )

    def seed(tx):
        tx.put("reports", report["reportId"], report)
        case = tx.get("cases", report["caseId"])
        case["assignedDoctorId"] = "doctor_a"
        tx.put("cases", report["caseId"], case)
        tx.put("analyses", candidate["analysisId"], candidate)

    uploads.database.run(seed)
    return client, uploads, identities, report, candidate


def test_assigned_doctor_reads_candidate_but_patient_never_receives_draft(result_setup):
    client, _, _, report, candidate = result_setup
    path = f"/api/v1/reports/{report['reportId']}/result"
    response = client.get(path, headers=headers("doctor_a"))
    assert response.status_code == 200
    assert response.json()["kind"] == "draft"
    assert response.json()["draft"] == candidate
    assert response.json()["approved"] is None
    assert response.headers["cache-control"] == "no-store"
    for uid in ("patient_a", "patient_b", "admin"):
        denied = client.get(path + "?kind=draft", headers=headers(uid))
        assert denied.status_code == 403
        assert "Synthetic Marker" not in denied.text
    assert client.get(path, headers=headers()).status_code == 409


def test_patient_gets_persisted_corrected_snapshot_during_replacement_processing(result_setup):
    client, uploads, _, report, candidate = result_setup
    snapshot = json.loads(
        (Path(__file__).parents[2] / "contracts/examples/approved-result.json").read_text()
    )["approved"]
    snapshot.update(
        reportId=report["reportId"],
        correctedRowIds=["row_1"],
        provenance=candidate["provenance"],
        unresolvedAcknowledgements=[{"issueId": "unresolved_1", "reason": "Unit is unreadable"}],
    )
    snapshot["rows"][0]["result"] = "<0.60"
    report.update(
        approvedAnalysisId="analysis_1", latestAnalysisId="replacement", reviewStatus="pending"
    )
    uploads.database.run(lambda tx: tx.put("reports", report["reportId"], report))
    uploads.database.run(lambda tx: tx.put("approvedResults", report["reportId"], snapshot))
    response = client.get(f"/api/v1/reports/{report['reportId']}/result", headers=headers())
    assert response.status_code == 200
    assert response.json()["approved"] == snapshot
    assert response.json()["draft"] is None
    assert "providerOutput" not in response.text


@pytest.mark.parametrize("action", ["expired", "reassigned", "wrong_hospital"])
def test_result_access_uses_current_case_and_retention(result_setup, action):
    client, uploads, _, report, _ = result_setup
    path = f"/api/v1/reports/{report['reportId']}/result"
    assert client.get(path, headers=headers("doctor_a")).status_code == 200

    def change(tx):
        if action == "expired":
            report.update(
                createdAt=(datetime.now(UTC) - timedelta(days=31)).isoformat(),
                expiresAt=(datetime.now(UTC) - timedelta(seconds=1)).isoformat(),
            )
            tx.put("reports", report["reportId"], report)
        else:
            case = tx.get("cases", report["caseId"])
            case["assignedDoctorId" if action == "reassigned" else "hospitalId"] = "other"
            tx.put("cases", report["caseId"], case)

    uploads.database.run(change)
    response = client.get(path, headers=headers("doctor_a"))
    assert response.status_code == (410 if action == "expired" else 403)
    assert "Synthetic Marker" not in response.text


def test_copied_document_path_requires_fresh_auth_and_assignment(result_setup):
    client, uploads, _, report, _ = result_setup
    path = f"/api/v1/reports/{report['reportId']}/document"
    assert client.get(path).status_code == 401
    report["assignedDoctorId"] = "other"
    uploads.database.run(lambda tx: tx.put("reports", report["reportId"], report))
    assert client.get(path, headers=headers("doctor_a")).status_code == 403
