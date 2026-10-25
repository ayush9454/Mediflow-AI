"""Production Firebase identity and Firestore adapters. ADC is backend-only."""

import os
from dataclasses import asdict
from typing import Any
from uuid import uuid4

import firebase_admin
from firebase_admin import auth, credentials, firestore
from firebase_admin.exceptions import FirebaseError
from google.api_core.exceptions import GoogleAPICallError
from google.auth.credentials import AnonymousCredentials
from pydantic import ValidationError

from mediflow.authorization import AuditEvent, Authorization
from mediflow.config import Settings
from mediflow.contracts import Account, ErrorCode, ReportMetadata
from mediflow.errors import ApplicationError
from mediflow.uploads.audit import record_audit
from mediflow.uploads.platform import FirestoreDatabase


def unavailable() -> ApplicationError:
    return ApplicationError(
        ErrorCode.TEMPORARILY_UNAVAILABLE, 503, "Account services are temporarily unavailable."
    )


class FirebaseTokens:
    def __init__(self, app: firebase_admin.App) -> None:
        self.app = app

    def verify(self, token: str) -> str:
        try:
            claims = auth.verify_id_token(token, app=self.app, check_revoked=True)
            uid = claims.get("uid")
            if not isinstance(uid, str) or not uid:
                raise ValueError("Invalid identity")
            return uid
        except (
            auth.InvalidIdTokenError,
            auth.RevokedIdTokenError,
            auth.UserDisabledError,
            auth.UserNotFoundError,
            ValueError,
        ):
            raise ValueError("Invalid identity") from None
        except FirebaseError:
            raise unavailable() from None


class FirestoreIdentityStore:
    def __init__(self, app: firebase_admin.App) -> None:
        self.db: Any = firestore.client(app)

    def _get(self, collection: str, identifier: str) -> dict[str, Any] | None:
        try:
            snapshot = self.db.collection(collection).document(identifier).get(timeout=10)
            return snapshot.to_dict() if snapshot.exists else None
        except GoogleAPICallError:
            raise unavailable() from None

    def account(self, uid: str) -> Account | None:
        data = self._get("users", uid)
        if data is None:
            return None
        try:
            return Account.model_validate(data)
        except ValidationError:
            return None

    def hospital_active(self, hospital_id: str) -> bool:
        data = self._get("hospitals", hospital_id)
        return data is not None and data.get("active") is True

    def report(self, report_id: str) -> ReportMetadata | None:
        data = self._get("reports", report_id)
        if data is None:
            return None
        # Assignment is owned by the case; never authorize using a stale report copy.
        case = self._get("cases", data.get("caseId", "missing"))
        if (
            case is None
            or case.get("reportId") != report_id
            or case.get("hospitalId") != data.get("hospitalId")
            or case.get("patientId") != data.get("patientId")
        ):
            return None
        data["assignedDoctorId"] = case.get("assignedDoctorId")
        data["caseVersion"] = case.get("version")
        try:
            return ReportMetadata.model_validate(data)
        except ValidationError:
            return None

    def case_report_id(self, case_id: str) -> str | None:
        case = self._get("cases", case_id)
        identifier = case.get("reportId") if case else None
        return identifier if isinstance(identifier, str) else None

    def audit(self, event: AuditEvent) -> None:
        key = uuid4().hex
        FirestoreDatabase(self.db).run(lambda tx: record_audit(tx, key, asdict(event), access=True))


class EmulatorCredential(credentials.Base):
    def get_credential(self) -> AnonymousCredentials:
        return AnonymousCredentials()


def create_authorization(settings: Settings) -> Authorization:
    emulator_keys = ("FIREBASE_AUTH_EMULATOR_HOST", "FIRESTORE_EMULATOR_HOST")
    emulated = any(os.getenv(key) for key in emulator_keys)
    credential = None
    if emulated:
        if (
            settings.environment != "test"
            or not settings.firebase_project_id.startswith("demo-")
            or not all(os.getenv(key) for key in emulator_keys)
        ):
            raise ValueError(
                "Firebase emulators require test environment, both hosts, and demo- project."
            )
        credential = EmulatorCredential()
    app = firebase_admin.initialize_app(
        credential, options={"projectId": settings.firebase_project_id}, name=f"mediflow-{uuid4()}"
    )
    return Authorization(FirebaseTokens(app), FirestoreIdentityStore(app))
