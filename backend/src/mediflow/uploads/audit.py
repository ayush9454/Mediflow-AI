"""Bound audit growth without dropping required events or permitting unaudited access."""

from datetime import UTC, timedelta

from mediflow.contracts import ErrorCode
from mediflow.errors import ApplicationError
from mediflow.uploads.database import Record, Transaction


def record_audit(tx: Transaction, key: str, event: Record, *, access: bool = False) -> None:
    if tx.get("auditEvents", key) is not None:
        return
    now = event["occurred_at"].astimezone(UTC)
    budget_key = ("access-" if access else "transition-") + now.strftime("%Y-%m-%d")
    budget = tx.get("auditBudgets", budget_key) or {"count": 0}
    if budget["count"] >= 10_000:
        raise ApplicationError(
            ErrorCode.QUOTA_EXHAUSTED,
            429,
            "The audit capacity limit has been reached. Try again later.",
        )
    tx.put(
        "auditBudgets",
        budget_key,
        {
            "count": budget["count"] + 1,
            "expiresAt": (now + timedelta(days=31)).isoformat(),
        },
    )
    tx.put("auditEvents", key, event)
