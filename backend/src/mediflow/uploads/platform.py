"""Trusted Firestore transactions and private Azure Blob storage adapters."""

import re
from collections.abc import Callable
from typing import Any, BinaryIO

from azure.core.exceptions import AzureError, ResourceNotFoundError
from azure.storage.blob import BlobServiceClient, ContentSettings
from google.api_core.exceptions import GoogleAPICallError
from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from mediflow.contracts import ErrorCode
from mediflow.errors import ApplicationError
from mediflow.uploads import MAX_BYTES, fail
from mediflow.uploads.database import Record, T, Transaction


def unavailable() -> ApplicationError:
    return fail(
        ErrorCode.TEMPORARILY_UNAVAILABLE, 503, "Document storage is temporarily unavailable."
    )


class FirestoreTransaction:
    def __init__(self, db: Any, transaction: Any) -> None:
        self.db = db
        self.transaction = transaction
        self.writes: dict[tuple[str, str], Record | None] = {}

    def get(self, collection: str, key: str) -> Record | None:
        # Buffer writes until all reads finish, as required by Firestore.
        if (collection, key) in self.writes:
            return self.writes[collection, key]
        snapshot = (
            self.db.collection(collection)
            .document(key)
            .get(transaction=self.transaction, timeout=10)
        )
        return snapshot.to_dict() if snapshot.exists else None

    def put(self, collection: str, key: str, value: Record) -> None:
        self.writes[collection, key] = value

    def delete(self, collection: str, key: str) -> None:
        self.writes[collection, key] = None

    def commit_writes(self) -> None:
        for (collection, key), value in self.writes.items():
            ref = self.db.collection(collection).document(key)
            if value is None:
                self.transaction.delete(ref)
            else:
                self.transaction.set(ref, value)


class FirestoreDatabase:
    def __init__(self, db: Any) -> None:
        self.db = db

    def run(self, operation: Callable[[Transaction], T]) -> T:
        @firestore.transactional
        def execute(transaction: Any) -> T:
            staged = FirestoreTransaction(self.db, transaction)
            result = operation(staged)
            staged.commit_writes()
            return result

        try:
            return execute(self.db.transaction(max_attempts=5))
        except (GoogleAPICallError, ValueError):
            raise unavailable() from None

    def expired(self, now: str, limit: int) -> list[str]:
        try:
            query = (
                self.db.collection("uploadSessions")
                .where(filter=FieldFilter("cleanupAt", "<=", now))
                .limit(limit)
            )
            return [snapshot.id for snapshot in query.stream(timeout=10)]
        except GoogleAPICallError:
            raise unavailable() from None


class BlobDocuments:
    def __init__(self, account_url: str, container: str, credential: Any) -> None:
        if not re.fullmatch(r"https://[a-z0-9]{3,24}\.blob\.core\.windows\.net", account_url):
            raise ValueError(
                "Use an HTTPS Azure Blob account endpoint without credentials or paths."
            )
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,61}[a-z0-9]", container):
            raise ValueError("Invalid private document container name.")
        self.client = BlobServiceClient(
            account_url,
            credential=credential,
            retry_total=0,
            connection_timeout=5,
            read_timeout=20,
            max_single_put_size=MAX_BYTES,
            max_block_size=1_000_000,
            max_single_get_size=1_000_000,
            max_chunk_get_size=1_000_000,
        )
        self.container = self.client.get_container_client(container)

    def _private(self) -> None:
        if self.container.get_container_properties(timeout=10).get("public_access") is not None:
            raise fail(
                ErrorCode.INTEGRATION_NOT_CONFIGURED, 503, "Private document storage is required."
            )

    def put(self, key: str, source: BinaryIO, size: int) -> None:
        if not 0 < size <= MAX_BYTES:
            raise fail(ErrorCode.INVALID_UPLOAD, 413, "The PDF exceeds the upload limit.")
        try:
            self._private()
            self.container.get_blob_client(key).upload_blob(
                source,
                length=size,
                overwrite=False,
                max_concurrency=1,
                timeout=20,
                content_settings=ContentSettings(
                    content_type="application/pdf", cache_control="no-store"
                ),
            )
        except AzureError:
            raise unavailable() from None

    def read(self, key: str) -> bytes:
        try:
            self._private()
            blob = self.container.get_blob_client(key)
            size = blob.get_blob_properties(timeout=10).size
            if not 0 < size <= MAX_BYTES:
                raise fail(ErrorCode.INVALID_UPLOAD, 422, "The stored PDF size is invalid.")
            result = bytearray()
            for chunk in blob.download_blob(max_concurrency=1, timeout=20).chunks():
                if len(result) + len(chunk) > MAX_BYTES:
                    raise fail(ErrorCode.INVALID_UPLOAD, 422, "The stored PDF size is invalid.")
                result.extend(chunk)
            if len(result) != size:
                raise unavailable()
            return bytes(result)
        except ResourceNotFoundError:
            raise unavailable() from None
        except AzureError:
            raise unavailable() from None

    def delete(self, key: str) -> None:
        try:
            self._private()
            self.container.delete_blob(key, timeout=20)
        except ResourceNotFoundError:
            pass
        except AzureError:
            raise unavailable() from None
