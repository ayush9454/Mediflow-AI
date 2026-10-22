"""Trusted live smoke against real Firebase; never emits credentials or tokens."""

import argparse
import json
import os
from pathlib import Path

import requests
from fastapi.testclient import TestClient

from mediflow.config import Settings
from mediflow.main import create_app
from mediflow.seed import ACCOUNTS


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--secrets-file", type=Path, required=True)
    args = parser.parse_args()
    if any(os.getenv(key) for key in ["FIREBASE_AUTH_EMULATOR_HOST", "FIRESTORE_EMULATOR_HOST"]):
        parser.error("Live smoke refuses emulator configuration.")
    project = os.environ["MEDIFLOW_FIREBASE_PROJECT_ID"]
    api_key = os.environ["MEDIFLOW_FIREBASE_API_KEY"]
    secrets = json.loads(args.secrets_file.read_text())
    app = create_app(Settings(environment="production", firebase_project_id=project))
    with TestClient(app) as client:
        for uid, role in ACCOUNTS.items():
            signin = requests.post(
                "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword",
                params={"key": api_key},
                json={**secrets[uid], "returnSecureToken": True},
                timeout=20,
            )
            if signin.status_code != 200:
                raise RuntimeError(f"Sign-in failed for seeded {uid}; status {signin.status_code}")
            headers = {"Authorization": f"Bearer {signin.json()['idToken']}"}
            response = client.get("/api/v1/me", headers=headers)
            assert response.status_code == 200, f"Backend account check failed for {uid}"
            assert response.json()["role"] == role
            expected = 501 if uid in {"patient_a", "doctor_a"} else 403
            response = client.get("/api/v1/reports/auth_fixture_report/document", headers=headers)
            assert response.status_code == expected, f"Resource policy failed for {uid}"
            path = (
                "https://firestore.googleapis.com/v1/projects/"
                + project
                + "/databases/(default)/documents/users/"
                + uid
            )
            assert requests.get(path, headers=headers, timeout=20).status_code == 403
            assert (
                requests.patch(
                    path,
                    headers=headers,
                    json={"fields": {"role": {"stringValue": "administrator"}}},
                    timeout=20,
                ).status_code
                == 403
            )
        assert (
            client.get("/api/v1/me", headers={"Authorization": "Bearer forged"}).status_code == 401
        )
    print(
        "PASS: five live sign-ins, server roles, clinical policy, Firestore denial, forged token."
    )


if __name__ == "__main__":
    main()
