"""Opt-in integration: real Firebase verifier/store and direct Firestore bypass attempts."""

import os

import pytest
import requests
from fastapi.testclient import TestClient

from mediflow.config import Settings
from mediflow.main import create_app
from mediflow.seed import ACCOUNTS, bootstrap

pytestmark = pytest.mark.skipif(
    not (os.getenv("FIREBASE_AUTH_EMULATOR_HOST") and os.getenv("FIRESTORE_EMULATOR_HOST")),
    reason="Run inside Firebase auth + Firestore emulators with demo-mediflow project",
)


def test_seeded_signin_real_verifier_rules_and_reassignment():
    project = "demo-mediflow"
    secrets = {
        uid: {"email": f"{uid}@example.test", "password": "synthetic-password-1234"}
        for uid in ACCOUNTS
    }
    bootstrap(project, secrets)
    host = os.environ["FIREBASE_AUTH_EMULATOR_HOST"]
    tokens = {}
    app = create_app(Settings(environment="test", firebase_project_id=project))
    with TestClient(app) as client:
        for uid, role in ACCOUNTS.items():
            response = requests.post(
                f"http://{host}/identitytoolkit.googleapis.com/v1/"
                "accounts:signInWithPassword?key=demo-key",
                json={**secrets[uid], "returnSecureToken": True},
                timeout=10,
            )
            response.raise_for_status()
            token = response.json()["idToken"]
            tokens[uid] = {"Authorization": f"Bearer {token}"}
            account = client.get("/api/v1/me", headers=tokens[uid])
            assert account.status_code == 200
            assert account.json()["role"] == role
            firestore_host = os.environ["FIRESTORE_EMULATOR_HOST"]
            base = f"http://{firestore_host}/v1/projects/{project}/databases/(default)/documents"
            for collection in ["users", "reports", "cases", "analyses", "reviews", "auditEvents"]:
                path = f"{base}/{collection}/auth_fixture_report"
                assert requests.get(path, headers=tokens[uid], timeout=10).status_code == 403
                assert (
                    requests.patch(
                        path,
                        headers=tokens[uid],
                        json={"fields": {"role": {"stringValue": "administrator"}}},
                        timeout=10,
                    ).status_code
                    == 403
                )
        target = "/api/v1/reports/auth_fixture_report/document"
        assert client.get(target, headers=tokens["patient_a"]).status_code == 501
        assert client.get(target, headers=tokens["patient_b"]).status_code == 403
        assert client.get(target, headers=tokens["administrator"]).status_code == 403
        assert client.get(target, headers=tokens["doctor_a"]).status_code == 501
        store = app.state.authorization.store
        store.db.collection("cases").document("auth_fixture_case").update(
            {"assignedDoctorId": "doctor_b", "version": 2}
        )
        try:
            assert client.get(target, headers=tokens["doctor_a"]).status_code == 403
            assert client.get(target, headers=tokens["doctor_b"]).status_code == 501
        finally:
            store.db.collection("cases").document("auth_fixture_case").update(
                {"assignedDoctorId": "doctor_a", "version": 3}
            )
        assert (
            client.get("/api/v1/me", headers={"Authorization": "Bearer forged"}).status_code == 401
        )
