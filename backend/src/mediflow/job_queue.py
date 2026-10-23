"""Reference-only Azure queue delivery; Firestore owns execution and retries."""

import re
from dataclasses import dataclass
from typing import Any, Protocol

from azure.core.exceptions import AzureError
from azure.storage.queue import QueueClient

from mediflow.contracts import ErrorCode
from mediflow.errors import ApplicationError


@dataclass(frozen=True)
class Delivery:
    job_id: str
    message_id: str
    receipt: str


class Queue(Protocol):
    def send(self, job_id: str) -> None: ...
    def receive(self) -> Delivery | None: ...
    def acknowledge(self, delivery: Delivery) -> None: ...


class AzureQueue:
    def __init__(self, account_url: str, name: str, credential: Any) -> None:
        if not re.fullmatch(r"https://[a-z0-9]{3,24}\.queue\.core\.windows\.net", account_url):
            raise ValueError("Use a credential-free HTTPS Azure Queue endpoint.")
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,61}[a-z0-9]", name):
            raise ValueError("Invalid Azure queue name.")
        self.client = QueueClient(
            account_url,
            name,
            credential=credential,
            retry_total=0,
            connection_timeout=5,
            read_timeout=10,
        )

    def send(self, job_id: str) -> None:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", job_id):
            raise ValueError("Invalid job reference.")
        try:
            self.client.send_message(job_id, time_to_live=86400, timeout=10)
        except AzureError:
            raise ApplicationError(
                ErrorCode.TEMPORARILY_UNAVAILABLE, 503, "Job delivery is unavailable."
            ) from None

    def receive(self) -> Delivery | None:
        try:
            message = next(
                iter(
                    self.client.receive_messages(
                        max_messages=1,
                        messages_per_page=1,
                        visibility_timeout=360,
                        timeout=10,
                    )
                ),
                None,
            )
            if message is None:
                return None
            if not message.pop_receipt:
                raise ValueError("Queue delivery has no receipt.")
            return Delivery(message.content, message.id, message.pop_receipt)
        except AzureError:
            raise ApplicationError(
                ErrorCode.TEMPORARILY_UNAVAILABLE, 503, "Job delivery is unavailable."
            ) from None

    def acknowledge(self, delivery: Delivery) -> None:
        try:
            self.client.delete_message(delivery.message_id, delivery.receipt, timeout=10)
        except AzureError:
            raise ApplicationError(
                ErrorCode.TEMPORARILY_UNAVAILABLE, 503, "Job acknowledgement is unavailable."
            ) from None
