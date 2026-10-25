"""Atomic document transactions; test adapters are never environment-selected."""

from collections.abc import Callable
from copy import deepcopy
from datetime import datetime
from threading import RLock
from typing import Any, Protocol, TypeVar

T = TypeVar("T")
Record = dict[str, Any]


class Transaction(Protocol):
    def get(self, collection: str, key: str) -> Record | None: ...
    def put(self, collection: str, key: str, value: Record) -> None: ...
    def delete(self, collection: str, key: str) -> None: ...


class Database(Protocol):
    def run(self, operation: Callable[[Transaction], T]) -> T: ...
    def due(self, collection: str, field: str, now: str | datetime, limit: int) -> list[str]: ...
    def page(self, collection: str, after: str | None, limit: int) -> list[tuple[str, Record]]: ...
    def scoped_page(
        self, collection: str, filters: dict[str, str], after: str | None, limit: int
    ) -> list[tuple[str, Record]]: ...


class MemoryDatabase:
    """Explicit transactional database fake for offline HTTP tests."""

    def __init__(self) -> None:
        self.records: dict[tuple[str, str], Record] = {}
        self.lock = RLock()

    def run(self, operation: Callable[[Transaction], T]) -> T:
        with self.lock:
            staged = MemoryTransaction(deepcopy(self.records))
            result = operation(staged)
            self.records = staged.records
            return result

    def due(self, collection: str, field: str, now: str | datetime, limit: int) -> list[str]:
        with self.lock:
            return [
                key
                for (stored_collection, key), data in self.records.items()
                if stored_collection == collection
                and data.get(field) is not None
                and data[field] <= now
            ][:limit]

    def page(self, collection: str, after: str | None, limit: int) -> list[tuple[str, Record]]:
        with self.lock:
            return [
                (key, deepcopy(data))
                for (stored_collection, key), data in sorted(self.records.items())
                if stored_collection == collection and (after is None or key > after)
            ][:limit]

    def scoped_page(
        self, collection: str, filters: dict[str, str], after: str | None, limit: int
    ) -> list[tuple[str, Record]]:
        with self.lock:
            return [
                (key, deepcopy(data))
                for (stored_collection, key), data in sorted(self.records.items())
                if stored_collection == collection
                and (after is None or key > after)
                and all(data.get(field) == value for field, value in filters.items())
            ][:limit]


class MemoryTransaction:
    def __init__(self, records: dict[tuple[str, str], Record]) -> None:
        self.records = records

    def get(self, collection: str, key: str) -> Record | None:
        return deepcopy(self.records.get((collection, key)))

    def put(self, collection: str, key: str, value: Record) -> None:
        self.records[collection, key] = deepcopy(value)

    def delete(self, collection: str, key: str) -> None:
        self.records.pop((collection, key), None)
