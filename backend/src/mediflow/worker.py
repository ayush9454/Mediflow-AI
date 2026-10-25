"""One queue delivery per invocation; all recovery state lives in Firestore."""

import argparse
import json
import re
from typing import Protocol

from mediflow.config import Settings
from mediflow.contracts import AnalysisCandidate, ErrorCode
from mediflow.errors import ApplicationError, ProcessingFailure
from mediflow.job_platform import JobServices, create_job_services
from mediflow.job_queue import Queue
from mediflow.jobs import Jobs, Lease
from mediflow.uploads import Uploads


class Processor(Protocol):
    def __call__(self, lease: Lease, source: bytes) -> AnalysisCandidate: ...


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


def platform(settings: Settings) -> JobServices:
    from mediflow.firebase import FirestoreIdentityStore, create_authorization
    from mediflow.uploads.platform import FirestoreDatabase

    if not settings.firebase_project_id or not settings.azure_storage_account_url:
        raise ValueError("Configure Firebase and private Azure storage before running jobs.")
    authorization = create_authorization(settings)
    store = authorization.store
    assert isinstance(store, FirestoreIdentityStore)
    return create_job_services(settings, FirestoreDatabase(store.db))


def main() -> int:
    parser = argparse.ArgumentParser(description="MediFlow durable processing worker")
    parser.add_argument("--check-config", action="store_true")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--reconcile", action="store_true")
    mode.add_argument("--maintenance", action="store_true")
    parser.add_argument("--limit", type=int, default=20, choices=range(1, 101))
    parser.add_argument("--test-adapter", action="store_true")
    arguments = parser.parse_args()
    settings = Settings.from_environment()
    if arguments.check_config:
        from mediflow.laboratory import GeminiProvider

        try:
            GeminiProvider.from_settings(settings)
            analysis_adapter = "configured"
        except ProcessingFailure:
            analysis_adapter = "not_configured"
        print(
            json.dumps(
                {
                    "status": "not_ready",
                    "queueAdapter": "implemented",
                    "analysisAdapter": analysis_adapter,
                },
                sort_keys=True,
            )
        )
        return 0
    if arguments.test_adapter and settings.environment != "test":
        parser.exit(2, "The deterministic adapter is allowed only in the test environment.\n")
    try:
        services = platform(settings)
        if arguments.maintenance:
            removed = services.uploads.cleanup(limit=arguments.limit)
            print(
                json.dumps(
                    {
                        "expiredRecordsRemoved": removed,
                        "cleanupFailures": services.uploads.cleanup_failures,
                    }
                )
            )
            if services.uploads.cleanup_failures:
                return 1
        elif arguments.reconcile:
            print(json.dumps({"dispatched": services.jobs.reconcile(limit=arguments.limit)}))
        else:
            from mediflow.job_processor import SubprocessProcessor

            execute_one(
                services.jobs,
                services.queue,
                services.uploads,
                SubprocessProcessor(
                    environment=settings.environment, test_adapter=arguments.test_adapter
                ),
            )
    except Exception:
        parser.exit(2, "Job services are unavailable or not configured.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
