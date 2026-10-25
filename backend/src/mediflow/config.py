"""Configuration without implicit cloud access or client-visible secrets."""

import os
from dataclasses import dataclass, field
from typing import Self


@dataclass(frozen=True)
class Settings:
    environment: str = "development"
    firebase_project_id: str = ""
    azure_storage_account_url: str = ""
    azure_document_container: str = "reports"
    azure_queue_name: str = "report-processing"
    gemini_model: str = ""
    gemini_api_key: str = field(default="", repr=False)
    gemini_free_tier_confirmed: bool = False
    job_timeout_seconds: int = 270
    storage_limit_bytes: int = 1_000_000_000
    accept_new_work: bool = True

    def __post_init__(self) -> None:
        if self.environment not in {"development", "test", "production"}:
            raise ValueError("MEDIFLOW_ENV must be development, test or production.")
        if not 1 <= self.job_timeout_seconds <= 270:
            raise ValueError("MEDIFLOW_JOB_TIMEOUT_SECONDS must be between 1 and 270.")
        if not 1 <= self.storage_limit_bytes <= 1_000_000_000:
            raise ValueError("MEDIFLOW_STORAGE_LIMIT_BYTES must be between 1 and 1,000,000,000.")

    @classmethod
    def from_environment(cls) -> Self:
        return cls(
            environment=os.getenv("MEDIFLOW_ENV", "development"),
            firebase_project_id=os.getenv("MEDIFLOW_FIREBASE_PROJECT_ID", ""),
            azure_storage_account_url=os.getenv("MEDIFLOW_AZURE_STORAGE_ACCOUNT_URL", ""),
            azure_document_container=os.getenv("MEDIFLOW_AZURE_DOCUMENT_CONTAINER", "reports"),
            azure_queue_name=os.getenv("MEDIFLOW_AZURE_QUEUE_NAME", "report-processing"),
            gemini_model=os.getenv("MEDIFLOW_GEMINI_MODEL", ""),
            gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
            gemini_free_tier_confirmed=os.getenv("MEDIFLOW_GEMINI_FREE_TIER_CONFIRMED") == "true",
            job_timeout_seconds=int(os.getenv("MEDIFLOW_JOB_TIMEOUT_SECONDS", "270")),
            storage_limit_bytes=int(os.getenv("MEDIFLOW_STORAGE_LIMIT_BYTES", "1000000000")),
            accept_new_work=os.getenv("MEDIFLOW_ACCEPT_NEW_WORK", "true") == "true",
        )
