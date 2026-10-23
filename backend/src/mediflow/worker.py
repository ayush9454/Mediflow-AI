"""One queue delivery per invocation; all recovery state lives in Firestore."""

import argparse
import json
import os
import re
from typing import Protocol

from mediflow.config import Settings
from mediflow.contracts import AnalysisCandidate, ErrorCode
from mediflow.errors import ApplicationError
from mediflow.job_queue import AzureQueue, Queue
from mediflow.jobs import Jobs, Lease
from mediflow.uploads import Uploads


class Processor(Protocol):
    def __call__(self, lease: Lease, source: bytes) -> AnalysisCandidate: ...


class ProcessingFailure(Exception):
    def __init__(self, code: ErrorCode, *, transient: bool = False):
        self.code = code
        self.transient = transient


def execute_one(jobs: Jobs, queue: Queue, uploads: Uploads, processor: Processor) -> bool:
    delivery = queue.receive()
    if delivery is None:
        return False
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", delivery.job_id):
        queue.acknowledge(delivery)
        return True
    lease = jobs.claim(delivery.job_id)
    if lease is not None:
        try:
            source = uploads.document(lease.report_id)
            candidate = processor(lease, source)
        except ProcessingFailure as failure:
            jobs.fail(lease, failure.code, transient=failure.transient)
        except ApplicationError as error:
            jobs.fail(lease, error.code, transient=error.code == ErrorCode.TEMPORARILY_UNAVAILABLE)
        except Exception:
            jobs.fail(lease, ErrorCode.INTERNAL_ERROR)
        else:
            # An uncertain commit must leave the message and execution lease intact.
            jobs.finish(lease, candidate)
    queue.acknowledge(delivery)
    return True


def platform(settings: Settings) -> tuple[Jobs, AzureQueue, Uploads]:
    from azure.identity import DefaultAzureCredential, ManagedIdentityCredential

    from mediflow.firebase import FirestoreIdentityStore, create_authorization
    from mediflow.uploads.platform import BlobDocuments, FirestoreDatabase

    if not settings.firebase_project_id or not settings.azure_storage_account_url:
        raise ValueError("Configure Firebase and private Azure storage before running jobs.")
    authorization = create_authorization(settings)
    store = authorization.store
    assert isinstance(store, FirestoreIdentityStore)
    credential = (
        ManagedIdentityCredential(client_id=os.getenv("AZURE_CLIENT_ID"))
        if settings.environment == "production"
        else DefaultAzureCredential(exclude_interactive_browser_credential=True)
    )
    database = FirestoreDatabase(store.db)
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
            settings.azure_storage_account_url, settings.azure_document_container, credential
        ),
    )
    return Jobs(database, queue, deadline_seconds=settings.job_timeout_seconds), queue, uploads


def main() -> int:
    parser = argparse.ArgumentParser(description="MediFlow durable processing worker")
    parser.add_argument("--check-config", action="store_true")
    parser.add_argument("--reconcile", action="store_true")
    parser.add_argument("--test-adapter", action="store_true")
    arguments = parser.parse_args()
    settings = Settings.from_environment()
    if arguments.check_config:
        print(
            json.dumps(
                {
                    "status": "not_ready",
                    "queueAdapter": "implemented",
                    "analysisAdapter": "not_configured",
                },
                sort_keys=True,
            )
        )
        return 0
    if arguments.test_adapter and settings.environment != "test":
        parser.exit(2, "The deterministic adapter is allowed only in the test environment.\n")
    try:
        jobs, queue, uploads = platform(settings)
        if arguments.reconcile:
            print(json.dumps({"dispatched": jobs.reconcile()}))
        else:
            from mediflow.job_processor import SubprocessProcessor

            execute_one(
                jobs,
                queue,
                uploads,
                SubprocessProcessor(
                    environment=settings.environment, test_adapter=arguments.test_adapter
                ),
            )
    except (ValueError, ApplicationError):
        parser.exit(2, "Job services are unavailable or not configured.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
