"""Explicit synthetic-only hosted integration, using real queue/Blob/Firestore."""

import json
import os
import sys

from azure.identity import ManagedIdentityCredential
from google.cloud import firestore
from google.oauth2.credentials import Credentials

from mediflow.job_processor import SubprocessProcessor
from mediflow.job_queue import AzureQueue
from mediflow.jobs import Jobs
from mediflow.uploads import Uploads
from mediflow.uploads.platform import BlobDocuments, FirestoreDatabase
from mediflow.worker import execute_one


class NamespacedClient:
    """All test records live beneath one disposable, opaque Firestore namespace."""

    def __init__(self, db, probe_id):
        self.db = db
        self.namespace = db.collection("jobSmokeRuns").document(probe_id)

    def collection(self, name):
        return self.namespace.collection(name)

    def transaction(self, **kwargs):
        return self.db.transaction(**kwargs)


def main():
    if os.environ.get("MEDIFLOW_ENV") != "test":
        raise RuntimeError("This entry point is exclusively a synthetic integration adapter")
    db = firestore.Client(
        project=os.environ["GOOGLE_PROJECT"],
        credentials=Credentials(token=os.environ["GOOGLE_TOKEN"]),
    )
    database = FirestoreDatabase(NamespacedClient(db, os.environ["SPIKE_ID"]))
    account = os.environ["STORAGE_ACCOUNT"]
    credential = ManagedIdentityCredential(client_id=os.environ["IDENTITY_CLIENT_ID"])
    queue = AzureQueue(f"https://{account}.queue.core.windows.net", "report-processing", credential)
    jobs = Jobs(database, queue)
    if "--reconcile" in sys.argv:
        print(json.dumps({"dispatched": jobs.reconcile()}))
        return
    uploads = Uploads(
        database, BlobDocuments(f"https://{account}.blob.core.windows.net", "reports", credential)
    )
    processed = execute_one(
        jobs, queue, uploads, SubprocessProcessor(environment="test", test_adapter=True)
    )
    print(json.dumps({"syntheticDeliveryHandled": processed}))


if __name__ == "__main__":
    main()
