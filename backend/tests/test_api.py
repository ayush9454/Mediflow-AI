import pytest
from fastapi.testclient import TestClient

from mediflow.api import current_account
from mediflow.config import Settings
from mediflow.contracts import Account
from mediflow.main import create_app


@pytest.fixture
def app():
    return create_app(Settings(environment="test"))


@pytest.fixture
def client(app):
    with TestClient(app) as result:
        yield result


def test_liveness_does_not_claim_cloud_readiness(client):
    live = client.get("/health/live")
    assert live.status_code == 200
    assert live.json()["status"] == "ok"
    assert live.json()["syntheticDataOnly"] is True
    assert live.headers["x-request-id"]
    ready = client.get("/health/ready")
    assert ready.status_code == 503
    assert ready.json()["status"] == "not_ready"


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/me",
        "/api/v1/cases",
        "/api/v1/doctors",
        "/api/v1/reports/report_1",
        "/api/v1/reports/report_1/result",
        "/api/v1/reports/report_1/document",
    ],
)
def test_protected_reads_fail_closed_without_authentication(client, path):
    response = client.get(path)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json()["error"]["requestId"] == response.headers["x-request-id"]


def test_token_shaped_text_does_not_create_a_fake_authenticated_account(client):
    response = client.get("/api/v1/me", headers={"Authorization": "Bearer patient_1"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "integration_not_configured"


def test_validation_errors_do_not_echo_sensitive_request_input(app):
    async def trusted_test_identity():
        return Account(
            uid="patient_1",
            hospital_id="hospital_1",
            display_name="Synthetic Patient",
            role="patient",
            active=True,
        )

    app.dependency_overrides[current_account] = trusted_test_identity
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/reports",
            headers={"Idempotency-Key": "test_operation"},
            json={
                "fileName": "PRIVATE_PAYLOAD",
                "byteCount": 0,
                "syntheticDataAcknowledged": False,
                "PRIVATE_PATIENT_NAME": "NEVER_ECHO",
            },
        )
    assert response.status_code == 422
    assert response.json()["error"]["fields"]
    assert "PRIVATE_PAYLOAD" not in response.text
    assert "NEVER_ECHO" not in response.text
    assert "PRIVATE_PATIENT_NAME" not in response.text
    assert '"input"' not in response.text


def test_unexpected_errors_do_not_leak_exception_contents(app, caplog):
    @app.get("/test-crash")
    async def crash():
        raise RuntimeError("SENSITIVE_EXCEPTION_CONTENT")

    with TestClient(app) as client:
        response = client.get("/test-crash")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert "SENSITIVE_EXCEPTION_CONTENT" not in response.text
    assert "SENSITIVE_EXCEPTION_CONTENT" not in caplog.text
    assert response.json()["error"]["requestId"] == response.headers["x-request-id"]
    assert response.headers["x-request-id"] in caplog.text


def test_repeated_failures_have_bounded_sanitized_logs_and_safe_responses(app, caplog):
    @app.get("/test-repeated-crash")
    async def crash():
        raise RuntimeError("PRIVATE_DOCUMENT_AND_TOKEN")

    with TestClient(app) as client:
        for _ in range(105):
            response = client.get("/test-repeated-crash")
            assert response.status_code == 500
    records = [record for record in caplog.records if record.name == "mediflow.main"]
    assert len(records) == 100
    assert "PRIVATE_DOCUMENT_AND_TOKEN" not in caplog.text
    assert "Traceback" not in caplog.text


def test_contracts_include_idempotency_concurrency_and_document_upload(client):
    document = client.get("/api/v1/openapi.json").json()
    registration = document["paths"]["/api/v1/reports"]["post"]
    assert any(p["name"] == "Idempotency-Key" for p in registration["parameters"])
    assert registration["security"]
    upload = document["paths"]["/api/v1/reports/{report_id}/file"]["put"]
    assert "application/pdf" in upload["requestBody"]["content"]
    review_ref = document["paths"]["/api/v1/reports/{report_id}/review"]["post"]["requestBody"][
        "content"
    ]["application/json"]["schema"]["$ref"]
    review = document["components"]["schemas"][review_ref.split("/")[-1]]
    assert "expectedAnalysisVersion" in review["required"]
    assert "expectedCaseVersion" in review["required"]
    assert "expectedReviewVersion" in review["required"]
    assignment = document["components"]["schemas"]["AssignmentRequest"]
    assert "expectedCaseVersion" in assignment["required"]


def test_unknown_route_uses_safe_error_envelope(client):
    response = client.get("/not-a-route")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
