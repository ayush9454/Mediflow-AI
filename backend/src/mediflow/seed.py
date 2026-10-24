"""Trusted synthetic bootstrap. Run with ADC; never exposed through HTTP."""

import argparse
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from firebase_admin import auth

from mediflow.config import Settings
from mediflow.contracts import Account, ProcessingStatus, ReportMetadata, Role
from mediflow.firebase import FirebaseTokens, FirestoreIdentityStore, create_authorization

ACCOUNTS = {
    "patient_a": "patient",
    "patient_b": "patient",
    "doctor_a": "doctor",
    "doctor_b": "doctor",
    "administrator": "administrator",
}


def bootstrap(project: str, secrets: dict[str, Any], *, reset_accounts: bool = False) -> None:
    module = create_authorization(
        Settings(
            environment="test" if project.startswith("demo-") else "development",
            firebase_project_id=project,
        )
    )
    assert isinstance(module.verifier, FirebaseTokens)
    assert isinstance(module.store, FirestoreIdentityStore)
    app, db = module.verifier.app, module.store.db
    # Validate every account before making any cloud mutation.
    emails: set[str] = set()
    for uid in ACCOUNTS:
        record = secrets.get(uid, {})
        if not isinstance(record.get("email"), str) or not record["email"].endswith(
            "@example.test"
        ):
            raise ValueError("Use synthetic @example.test account addresses.")
        if not isinstance(record.get("password"), str) or len(record["password"]) < 16:
            raise ValueError("Each password must contain at least 16 characters.")
        email = record["email"].lower()
        if email in emails:
            raise ValueError("Every seed account needs a distinct email address.")
        emails.add(email)
        try:
            user = auth.get_user(uid, app=app)
            if user.email != record["email"]:
                raise ValueError("Existing seed identity differs; refusing to overwrite.")
        except auth.UserNotFoundError:
            try:
                auth.get_user_by_email(record["email"], app=app)
            except auth.UserNotFoundError:
                pass
            else:
                raise ValueError("Seed email belongs to a different identity.") from None
    db.collection("hospitals").document("hospital_demo").set(
        {"active": True, "displayName": "Synthetic demonstration hospital"}
    )
    for uid, role in ACCOUNTS.items():
        record = secrets[uid]
        try:
            user = auth.get_user(uid, app=app)
            if user.email != record["email"]:
                raise ValueError("Existing seed identity differs; refusing to overwrite.")
        except auth.UserNotFoundError:
            auth.create_user(
                uid=uid,
                email=record["email"],
                password=record["password"],
                display_name=f"Synthetic {uid}",
                app=app,
            )
        if reset_accounts:
            auth.update_user(uid, password=record["password"], disabled=False, app=app)
            auth.revoke_refresh_tokens(uid, app=app)
        account = Account(
            uid=uid,
            hospital_id="hospital_demo",
            display_name=f"Synthetic {uid}",
            role=Role(role),
            active=True,
        )
        db.collection("users").document(uid).set(account.model_dump(mode="json", by_alias=True))
        db.collection(
            "doctors" if role == "doctor" else "patients" if role == "patient" else "administrators"
        ).document(uid).set(
            {
                "hospitalId": "hospital_demo",
                "active": True,
                **({"department": "Laboratory"} if role == "doctor" else {}),
            }
        )
    # A representative access-control fixture; not an uploaded clinical document.
    report = ReportMetadata(
        report_id="auth_fixture_report",
        case_id="auth_fixture_case",
        case_version=1,
        review_version=0,
        patient_id="patient_a",
        hospital_id="hospital_demo",
        file_name="synthetic-authorization-fixture.pdf",
        processing_status=ProcessingStatus.UPLOAD_PENDING,
        assigned_doctor_id="doctor_a",
        created_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(days=30),
    )
    batch = db.batch()
    if not db.collection("reports").document(report.report_id).get().exists:
        batch.create(
            db.collection("reports").document(report.report_id), report.model_dump(by_alias=True)
        )
        batch.create(
            db.collection("cases").document(report.case_id),
            {
                "reportId": report.report_id,
                "patientId": report.patient_id,
                "hospitalId": report.hospital_id,
                "assignedDoctorId": "doctor_a",
                "version": 1,
            },
        )
    batch.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-project", required=True)
    parser.add_argument("--synthetic-only", action="store_true", required=True)
    parser.add_argument("--secrets-file", type=Path, required=True)
    parser.add_argument(
        "--reset-accounts",
        action="store_true",
        help=(
            "Restore seed passwords, enable accounts and revoke sessions; "
            "preserve reports and quota usage."
        ),
    )
    args = parser.parse_args()
    if args.confirm_project != os.getenv("MEDIFLOW_FIREBASE_PROJECT_ID"):
        parser.error("Project confirmation must match MEDIFLOW_FIREBASE_PROJECT_ID.")
    if args.secrets_file.stat().st_mode & 0o077:
        parser.error("Secrets file must be accessible only to its owner (chmod 600).")
    bootstrap(
        args.confirm_project,
        json.loads(args.secrets_file.read_text()),
        reset_accounts=args.reset_accounts,
    )
    print("Synthetic hospital, five account records, and authorization fixture seeded.")


if __name__ == "__main__":
    main()
