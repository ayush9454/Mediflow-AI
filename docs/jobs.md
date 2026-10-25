# Durable processing jobs

The upload transaction is the acceptance boundary: it saves the report, one quota
charge, the authoritative `processingJobs` record and its `jobDispatches` intent.
Queue messages contain only an opaque job ID. Losing an HTTP connection or closing
the Android app cannot cancel this transaction.

The queue uses at-least-once delivery. Firestore transactions grant an attempt ID
and finite execution lease before processing; all result commits check that lease.
An analysis identity belongs to a logical run, so interrupted executions cannot
create a second candidate. Reprocessing creates a fresh logical run.

The bounded scheduled reconciler must run independently of API traffic. It scans
only due intents, repairs missed dispatches and expired execution leases, and
redispatches queued work if a message has disappeared. An enqueue success followed
by a database failure can produce a duplicate message, which is safe.

Initial deployment bounds:

| Control | Value |
| --- | --- |
| Total processing attempts per run | 3 |
| Automatic retry backoff | 30 seconds, then 120 seconds |
| Processing deadline | 270 seconds; configurable from 1 to 270 |
| Firestore execution lease | 330 seconds |
| Queue visibility | 360 seconds |
| Queue message lifetime | 24 hours |
| Missed-delivery reconciliation | 5 minutes |
| Dispatch claim | 60 seconds |
| Reconciler batch | 20, hard maximum 100 |
| Active content-processing lease | 1 per hospital |
| Manual reprocessing | 2/report/UTC day; 60-second cooldown |

Configure event-driven Azure Container Apps Jobs with one replica per execution,
parallelism one, maximum executions one per polling interval, a 30-second polling
interval, a 420-second replica timeout and `replicaRetryLimit=0`. The application
transaction owns the three-attempt ceiling. Duplicate platform executions remain
safe because acquisition is fenced. Queue, Blob and processing-provider SDKs must
disable automatic request retries; Firestore transaction retries do not execute the
provider. Use a separate scheduled Job every five minutes for reconciliation,
with a 120-second timeout, parallelism/completion one and platform retries zero.
`maxExecutions` is a bound per polling interval, rather than a global mutex. A
transactional `jobWorkerSlots` lease separately limits actual content processing to
one run per hospital. Busy deliveries do not consume a processing attempt and are
redispatched by reconciliation. Completion/failure releases only its own attempt's
slot; interruption releases capacity when the lease expires.

The Azure event scaler starts Jobs; the worker explicitly receives and deletes
its message. A message is deleted only after the durable transition, or after
observing that the reference is already completed, expired, leased or no longer
eligible. Recovery always comes from Firestore rather than dequeue counts.
See Microsoft's [event-driven Jobs tutorial](https://learn.microsoft.com/en-us/azure/container-apps/tutorial-event-driven-jobs)
and [QueueClient contract](https://learn.microsoft.com/python/api/azure-storage-queue/azure.storage.queue.queueclient).

No deterministic test adapter may serve production or demo analysis. The normal
worker runs real PDF/OCR and the configured Gemini laboratory provider. Missing
free-tier configuration reports `integration_not_configured` without inventing
output. See [laboratory extraction](laboratory-extraction.md) for configuration,
bounds, failure classifications and development evaluation.

## Run and deploy

Configure the existing Firebase project, private Blob endpoint and queue name from
`backend/.env.example`. `MEDIFLOW_JOB_TIMEOUT_SECONDS` controls the deadline; hard
lease/visibility/platform bounds stay larger. Neither the API nor the worker
creates cloud resources at startup. The worker uses backend-only Google ADC and
Azure managed identity in production. Never ship either credential in the APK.

```sh
backend/.venv/bin/python -m mediflow.worker --check-config
backend/.venv/bin/python -m mediflow.worker
backend/.venv/bin/python -m mediflow.worker --reconcile
```

`backend/jobs.bicep` defines the event and scheduled Jobs in an existing Consumption
environment. Supply a digest-pinned worker image, private registry, storage account,
Firebase project, managed identity and secure backend Google ADC configuration.
The Azure identity needs registry-scoped AcrPull and storage-scoped Blob/Queue data
permissions; Google credentials need Firestore data access. Credentials are mounted
as a secret, never placed in the image. Provision the private `reports` container
and `report-processing` queue before deployment. Deploy the reconciler with the
worker: API traffic is not the recovery clock. A newly accepted report may wait up
to the next five-minute reconciliation cycle before dispatch.

For an upgrade from ticket 05, replace old API writers before starting the scheduled
Job. Each reconciliation first adopts up to its batch limit of existing intents,
using a persistent document-ID cursor in `jobMigrations/durable-v1`. This gives
previously accepted jobs their missing dispatch schedule, analysis identity and
head, without charging quotas. A transaction rechecks each intent so interruption
or overlapping migrations cannot reset a current run. The bounded scan stops after
all existing records are inspected; do not leave an old writer creating legacy
intents after that point.

Attempts are separate `jobAttempts` records, with start/deadline/finish times and
safe failure codes. `jobDispatches` holds run identity, pipeline/config versions,
lease and next dispatch/attempt times; `jobHeads` selects the current logical run.
An atomic successful commit writes one immutable candidate, its `analysisCommits`
attempt/config reference, the report/case processing state and a deterministic audit
event. The original upload quota is never touched by processing/reprocessing.
Attempt start and retry scheduling also write deterministic per-attempt audit events
in their state-changing transactions, with run/attempt/version references.

`POST /api/v1/reports/{id}/reprocess` requires the currently assigned active doctor,
an idempotency key and `expectedLatestAnalysisId`. Send JSON null for a failed
initial run without a candidate. Reusing a key with a changed request is a conflict;
reusing it after reassignment or expiry cannot bypass current access checks. New
requests conflict while another run is active or the expected candidate is stale.
The response is the current state of the original operation for an identical key.
The approved analysis ID and snapshot remain untouched while a replacement is
queued, failed, rejected or pending review. Assignment and approval are still owned
by their own workflows.

Expiry is checked against the authoritative report during claim, reconciliation
and result commit. Removing the report/source or passing its expiry cannot lead a
stale delivery to create analysis content. Physical deletion and rolling removal of
job bookkeeping run through the independent [retention schedule](operations.md).

## Verification

The confirmed coordinator, reprocess HTTP and queue worker tests inject uncertain
dispatch, unavailable lease acquisition, process termination, failed/uncertain
result commits and lost acknowledgements. The same tests can use real Firestore
transactions through the opt-in emulator fixture:

```sh
firebase emulators:exec --config firebase.json --project demo-mediflow --only auth,firestore 'MEDIFLOW_ENV=test MEDIFLOW_UPLOAD_TEST_FIRESTORE=1 backend/.venv/bin/python -m pytest backend/tests/test_jobs.py backend/tests/test_worker.py'
```

See [the disposable cloud acceptance procedure](../tools/jobs_smoke/README.md) for
the queue-triggered hosted execution. The test adapter requires an explicit CLI
flag and test environment; no environment setting automatically installs it.
