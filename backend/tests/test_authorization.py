"""Behavior at the protected HTTP seam with trusted identity/store adapters."""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from mediflow.authorization import Authorization, MemoryIdentityStore
from mediflow.config import Settings
from mediflow.contracts import Account, ReportMetadata
from mediflow.main import create_app


class Tokens:
    def verify(self, token: str) -> str:
        if token == "invalid":
            raise ValueError("SECRET PROVIDER RESPONSE")
        return token


@pytest.fixture
def setup():
    store = MemoryIdentityStore()
    for uid, role, hospital, active in [
        ("patient_a", "patient", "hospital_1", True),
        ("patient_b", "patient", "hospital_1", True),
        ("doctor_a", "doctor", "hospital_1", True),
        ("doctor_b", "doctor", "hospital_1", True),
        ("admin", "administrator", "hospital_1", True),
        ("inactive", "patient", "hospital_1", False),
        ("outsider", "patient", "hospital_2", True),
    ]:
        store.accounts[uid] = Account(
            uid=uid, hospital_id=hospital, display_name=uid, role=role, active=active
        )
    store.hospitals.update({"hospital_1", "hospital_2"})
    store.reports["report_1"] = ReportMetadata(
        report_id="report_1",
        case_id="case_1",
        case_version=1,
        review_version=0,
        patient_id="patient_a",
        hospital_id="hospital_1",
        file_name="synthetic.pdf",
        processing_status="upload_pending",
        assigned_doctor_id="doctor_a",
        created_at=datetime.now(UTC),
    )
    app = create_app(Settings(environment="test"), authorization=Authorization(Tokens(), store))
    with TestClient(app) as client:
        yield client, store


def get(client, uid, path="/api/v1/me"):
    return client.get(path, headers={"Authorization": f"Bearer {uid}"})


def test_current_account_comes_from_trusted_records(setup):
    client, store = setup
    response = get(client, "patient_a")
    assert response.status_code == 200
    assert response.json()["role"] == "patient"
    assert response.headers["cache-control"] == "no-store"
    assert get(client, "invalid").status_code == 401
    assert get(client, "unseeded").status_code == 403
    assert get(client, "inactive").status_code == 403
    store.hospitals.remove("hospital_1")
    assert get(client, "patient_a").status_code == 403


@pytest.mark.parametrize(
    "uid,status",
    [
        ("patient_a", 200),
        ("patient_b", 403),
        ("doctor_a", 200),
        ("doctor_b", 403),
        ("admin", 200),
        ("outsider", 403),
    ],
)
def test_report_metadata_uses_hospital_ownership_and_current_assignment(setup, uid, status):
    client, store = setup
    response = get(client, uid, "/api/v1/reports/report_1")
    assert response.status_code == status
    if status == 200:
        assert response.json()["patientId"] == "patient_a"
    assert store.events[-1].action == "metadata"
    assert store.events[-1].outcome == ("allowed" if status == 200 else "denied")


@pytest.mark.parametrize("suffix", ["document", "result", "review", "reprocess"])
def test_clinical_workflows_deny_administrators(setup, suffix):
    client, _ = setup
    if suffix in {"document", "result"}:
        response = get(client, "admin", f"/api/v1/reports/report_1/{suffix}")
    else:
        body = (
            {"expectedLatestAnalysisId": "analysis_1", "reason": "Synthetic retry"}
            if suffix == "reprocess"
            else {
                "analysisId": "analysis_1",
                "expectedAnalysisVersion": 1,
                "expectedCaseVersion": 1,
                "expectedReviewVersion": 0,
                "decision": "rejected",
                "comment": "Synthetic rejection",
            }
        )
        response = client.post(
            f"/api/v1/reports/report_1/{suffix}",
            headers={"Authorization": "Bearer admin", "Idempotency-Key": "operation_1"},
            json=body,
        )
    assert response.status_code == 403


def test_reassignment_revokes_previous_doctor_on_next_request(setup):
    client, store = setup
    assert get(client, "doctor_a", "/api/v1/reports/report_1/document").status_code == 501
    store.reports["report_1"] = store.reports["report_1"].model_copy(
        update={"assigned_doctor_id": "doctor_b", "case_version": 2}
    )
    assert get(client, "doctor_a", "/api/v1/reports/report_1/document").status_code == 403
    assert get(client, "doctor_b", "/api/v1/reports/report_1/document").status_code == 501
    store.accounts["doctor_b"] = store.accounts["doctor_b"].model_copy(update={"active": False})
    assert get(client, "doctor_b", "/api/v1/reports/report_1/document").status_code == 403


def test_forged_patient_and_role_fields_cannot_promote_request(setup):
    client, _ = setup
    response = client.post(
        "/api/v1/reports",
        headers={"Authorization": "Bearer patient_a", "Idempotency-Key": "request_1"},
        json={
            "fileName": "synthetic.pdf",
            "byteCount": 20,
            "syntheticDataAcknowledged": True,
            "patientId": "patient_b",
            "role": "administrator",
        },
    )
    assert response.status_code == 422
    response = client.post(
        "/api/v1/reports",
        headers={"Authorization": "Bearer admin", "Idempotency-Key": "request_1"},
        json={"fileName": "synthetic.pdf", "byteCount": 20, "syntheticDataAcknowledged": True},
    )
    assert response.status_code == 403


def test_missing_and_other_hospital_resources_have_same_response(setup):
    client, _ = setup
    assert get(client, "outsider", "/api/v1/reports/report_1").status_code == 403
    assert get(client, "patient_a", "/api/v1/reports/nonexistent").status_code == 403


def test_production_rejects_injected_test_authentication():
    with pytest.raises(ValueError, match="only in tests"):
        create_app(
            Settings(environment="production"),
            authorization=Authorization(Tokens(), MemoryIdentityStore()),
        )


def test_assignment_checks_case_hospital_before_workflow(setup):
    client, store = setup
    headers = {"Authorization": "Bearer admin", "Idempotency-Key": "assign_1"}
    body = {"doctorId": "doctor_b", "expectedCaseVersion": 1}
    assert (
        client.post("/api/v1/cases/case_1/assignment", headers=headers, json=body).status_code
        == 501
    )
    store.reports["report_1"] = store.reports["report_1"].model_copy(
        update={"hospital_id": "hospital_2"}
    )
    assert (
        client.post("/api/v1/cases/case_1/assignment", headers=headers, json=body).status_code
        == 403
    )


def test_production_refuses_emulator_hosts(monkeypatch):
    monkeypatch.setenv("FIREBASE_AUTH_EMULATOR_HOST", "localhost:9099")
    monkeypatch.setenv("FIRESTORE_EMULATOR_HOST", "localhost:8080")
    with pytest.raises(ValueError, match="emulators require"):
        create_app(Settings(environment="production", firebase_project_id="demo-mediflow"))
