"""Atomic capacity accounting for serialized clinical payloads and their removal."""

import hashlib
import json

from mediflow.contracts import ErrorCode
from mediflow.errors import ApplicationError
from mediflow.uploads.database import Database, Record, Transaction


def ensure_capacity_ready(database: Database) -> None:
    if database.run(lambda tx: tx.get("storagePolicy", "capacity-v1")):
        return
    occupied = any(
        database.page(collection, None, 1)
        for collection in (
            "uploadSessions",
            "uploadGarbage",
            "sourceArtifacts",
            "analyses",
            "reviews",
            "approvedResults",
        )
    )

    def initialize(tx: Transaction) -> None:
        if tx.get("storagePolicy", "capacity-v1"):
            return
        if occupied:
            raise ApplicationError(
                ErrorCode.INTEGRATION_NOT_CONFIGURED,
                503,
                "Existing storage requires trusted maintenance before accepting uploads.",
            )
        tx.put("storagePolicy", "capacity-v1", {"version": 1})

    database.run(initialize)


def charge_key(collection: str, key: str) -> str:
    return hashlib.sha256(f"{collection}/{key}".encode()).hexdigest()


def adjust_capacity(
    tx: Transaction, hospital_id: str, delta: int, limit: int | None = None
) -> None:
    capacity = tx.get("storageCapacity", hospital_id) or {"reservedBytes": 0}
    total = capacity["reservedBytes"] + delta
    if total < 0:
        raise ApplicationError(
            ErrorCode.INTEGRATION_NOT_CONFIGURED,
            503,
            "Storage accounting requires trusted maintenance.",
        )
    if limit is not None and total > limit:
        raise ApplicationError(
            ErrorCode.QUOTA_EXHAUSTED, 429, "The storage capacity limit has been reached."
        )
    tx.put("storageCapacity", hospital_id, {"reservedBytes": total})


def store_payload(
    tx: Transaction,
    collection: str,
    key: str,
    value: Record,
    hospital_id: str,
    report_id: str,
    limit: int,
) -> None:
    size = len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode())
    previous = tx.get("payloadCharges", charge_key(collection, key)) or {"bytes": 0}
    if size > 900_000:
        raise ApplicationError(
            ErrorCode.QUOTA_EXHAUSTED, 429, "The storage capacity limit has been reached."
        )
    adjust_capacity(tx, hospital_id, size - previous["bytes"], limit)
    tx.put(
        "payloadCharges",
        charge_key(collection, key),
        {
            "bytes": size,
            "hospitalId": hospital_id,
            "reportId": report_id,
        },
    )
    tx.put(collection, key, value)


def delete_payload(tx: Transaction, collection: str, key: str) -> None:
    charge = tx.get("payloadCharges", charge_key(collection, key))
    if charge:
        adjust_capacity(tx, charge["hospitalId"], -charge["bytes"])
        tx.delete("payloadCharges", charge_key(collection, key))
    tx.delete(collection, key)
