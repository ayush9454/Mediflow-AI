"""Small boundaries for future trusted platform adapters.

No in-memory clinical repository or fake identity is wired into the running API.
"""

from collections.abc import AsyncIterator
from typing import Protocol

from mediflow.contracts import Account, AnalysisCandidate, ProcessingJob


class TokenVerifier(Protocol):
    async def verify(self, token: str) -> Account:
        """Verify identity and load trusted account role/active status."""
        ...


class PrivateDocuments(Protocol):
    def read(self, object_key: str) -> AsyncIterator[bytes]:
        """Read an authorized, private source; caller supplies trusted object key."""
        ...

    async def delete(self, object_key: str) -> None: ...


class JobQueue(Protocol):
    async def enqueue(self, job: ProcessingJob) -> None:
        """Deliver a reference to an already durable authoritative job."""
        ...


class AnalysisProvider(Protocol):
    async def extract(self, job: ProcessingJob, page_text: tuple[str, ...]) -> AnalysisCandidate:
        """Return a candidate only; never approve or mutate clinical records."""
        ...
