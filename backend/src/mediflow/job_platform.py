"""Trusted adapter composition shared by the API and hosted worker."""

import os
from dataclasses import dataclass

from azure.identity import DefaultAzureCredential, ManagedIdentityCredential

from mediflow.config import Settings
from mediflow.job_queue import AzureQueue
from mediflow.jobs import Jobs
from mediflow.uploads import Uploads
from mediflow.uploads.database import Database
from mediflow.uploads.platform import BlobDocuments


@dataclass(frozen=True)
class JobServices:
    jobs: Jobs
    queue: AzureQueue
    uploads: Uploads


def create_job_services(settings: Settings, database: Database) -> JobServices:
    credential = (
        ManagedIdentityCredential(client_id=os.getenv("AZURE_CLIENT_ID"))
        if settings.environment == "production"
        else DefaultAzureCredential(exclude_interactive_browser_credential=True)
    )
    queue = AzureQueue(
        settings.azure_storage_account_url.replace(
            ".blob.core.windows.net", ".queue.core.windows.net"
        ),
        settings.azure_queue_name,
        credential,
    )
    uploads = Uploads(
        database,
        BlobDocuments(
            settings.azure_storage_account_url,
            settings.azure_document_container,
            credential,
        ),
    )
    return JobServices(
        Jobs(database, queue, deadline_seconds=settings.job_timeout_seconds), queue, uploads
    )
