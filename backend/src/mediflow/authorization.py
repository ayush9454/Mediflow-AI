"""Shared authorization, using freshly loaded server records on every request."""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Literal, Protocol

from mediflow.contracts import Account, ErrorCode, ReportMetadata, Role
from mediflow.errors import ApplicationError

Action = Literal["metadata", "document", "result", "upload", "review", "reprocess", "assign"]


class TokenVerifier(Protocol):
    def verify(self, token: str) -> str: ...


@dataclass(frozen=True)
class AuditEvent:
    actor_id: str | None
    hospital_id: str | None
    resource_id: str | None
    action: str
    outcome: str
    request_id: str
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime = field(default_factory=lambda: datetime.now(UTC) + timedelta(days=30))


class IdentityStore(Protocol):
    def account(self, uid: str) -> Account | None: ...
    def hospital_active(self, hospital_id: str) -> bool: ...
    def report(self, report_id: str) -> ReportMetadata | None: ...
    def audit(self, event: AuditEvent) -> None: ...
    def case_report_id(self, case_id: str) -> str | None: ...


class Authorization:
    def __init__(self, verifier: TokenVerifier, store: IdentityStore) -> None:
        self.verifier = verifier
        self.store = store

    def authenticate(self, token: str | None, request_id: str) -> Account:
        if not token:
            self.store.audit(AuditEvent(None, None, None, "authenticate", "denied", request_id))
            raise ApplicationError(ErrorCode.UNAUTHENTICATED, 401, "Sign in to continue.")
        try:
            uid = self.verifier.verify(token)
        except ValueError:
            self.store.audit(AuditEvent(None, None, None, "authenticate", "denied", request_id))
            raise ApplicationError(ErrorCode.UNAUTHENTICATED, 401, "Sign in to continue.") from None
        account = self.store.account(uid)
        if (
            account is None
            or account.uid != uid
            or not account.active
            or not self.store.hospital_active(account.hospital_id)
        ):
            self.store.audit(AuditEvent(None, None, None, "authenticate", "denied", request_id))
            raise ApplicationError(
                ErrorCode.PERMISSION_DENIED, 403, "Account access is unavailable."
            )
        return account

    def require_role(self, account: Account, roles: set[Role], request_id: str) -> None:
        self._decision(account, None, "role", account.role in roles, request_id)

    def report_access(
        self, account: Account, report_id: str, action: Action, request_id: str
    ) -> ReportMetadata:
        report = self.store.report(report_id)
        allowed = False
        if report is not None and report.hospital_id == account.hospital_id:
            owner = account.role == Role.PATIENT and report.patient_id == account.uid
            assigned = account.role == Role.DOCTOR and report.assigned_doctor_id == account.uid
            if action == "metadata":
                allowed = owner or assigned or account.role == Role.ADMINISTRATOR
            elif action in {"document", "result"}:
                allowed = owner or assigned
            elif action == "upload":
                allowed = owner
            elif action in {"review", "reprocess"}:
                allowed = assigned
            elif action == "assign":
                allowed = account.role == Role.ADMINISTRATOR
        self._decision(account, report_id, action, allowed, request_id)
        assert report is not None
        if report.expires_at is not None:
            if report.expires_at <= datetime.now(UTC):
                raise ApplicationError(ErrorCode.EXPIRED, 410, "This report has expired.")
        return report

    def case_access(self, account: Account, case_id: str, request_id: str) -> ReportMetadata:
        report_id = self.store.case_report_id(case_id)
        if report_id is None:
            self._decision(account, case_id, "assign", False, request_id)
            raise AssertionError("denial must raise")
        return self.report_access(account, report_id, "assign", request_id)

    def _decision(
        self, account: Account, resource: str | None, action: str, allowed: bool, request_id: str
    ) -> None:
        self.store.audit(
            AuditEvent(
                account.uid,
                account.hospital_id,
                resource,
                action,
                "allowed" if allowed else "denied",
                request_id,
            )
        )
        if not allowed:
            # Missing and forbidden resources have the same response.
            raise ApplicationError(ErrorCode.PERMISSION_DENIED, 403, "Access is denied.")


@dataclass
class MemoryIdentityStore:
    """Explicit test adapter; never selected by environment configuration."""

    accounts: dict[str, Account] = field(default_factory=dict)
    hospitals: set[str] = field(default_factory=set)
    reports: dict[str, ReportMetadata] = field(default_factory=dict)
    events: list[AuditEvent] = field(default_factory=list)

    def account(self, uid: str) -> Account | None:
        return self.accounts.get(uid)

    def hospital_active(self, hospital_id: str) -> bool:
        return hospital_id in self.hospitals

    def report(self, report_id: str) -> ReportMetadata | None:
        return self.reports.get(report_id)

    def case_report_id(self, case_id: str) -> str | None:
        return next(
            (report.report_id for report in self.reports.values() if report.case_id == case_id),
            None,
        )

    def audit(self, event: AuditEvent) -> None:
        self.events.append(event)
