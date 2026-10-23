# Private PDF uploads

Ticket 05 implements the authenticated registration → bounded PUT → stored-byte
verification → durable job-intent flow. Ticket 06 owns dispatch, worker execution,
recovery and retry; accepting an upload does not claim that a worker ran.

## Configuration and deployment

Set `MEDIFLOW_FIREBASE_PROJECT_ID`, backend-only Google ADC, the HTTPS
`MEDIFLOW_AZURE_STORAGE_ACCOUNT_URL` and `MEDIFLOW_AZURE_DOCUMENT_CONTAINER`
(default `reports`). Provision the container privately and disable account-level
Blob public access and shared-key access. The adapter does not create containers,
return Blob URLs or mint SAS tokens. It rejects a publicly readable container.

In production, Azure authentication uses managed identity; for a user-assigned
identity set `AZURE_CLIENT_ID`. Grant Storage Blob Data Contributor at the storage
account or narrower container scope. Local development uses DefaultAzureCredential.
Emulator hosts remain forbidden in production by the authentication configuration.
No memory database, identity or storage fake is selected from environment settings.

The API Docker image includes the processing extra and English Tesseract. Completion
verifies readability and supported English laboratory content through the existing
isolated `process_pdf` module before it creates work. Conservative classification
can reject uncertain documents; this is not a general language detector or proof
of clinical correctness. This admission check does not create an AI analysis.
Use one API process per replica, a 1 GiB memory ceiling and at least 0.5 vCPU; page
processing retains its 240-second deadline and child process resource limits.
The upload endpoint admits one incoming stream per process; another receives 503
and can retry. Native/OCR evidence extraction is still independently owned by 07.

## HTTP flow

1. `POST /api/v1/reports` with `Idempotency-Key` and `fileName`, `byteCount`, and
   `syntheticDataAcknowledged: true`. Ownership and object paths come from the
   verified account and server IDs. The response contains report metadata, a
   relative authenticated PUT path and the reservation expiry.
2. `PUT` the PDF bytes to that path with `Content-Type: application/pdf`. The
   server writes at most 10,000,000 bytes to a temporary file, checks the actual
   count against registration and permits at most 60 seconds for incoming bytes.
   Nothing is uploaded to Azure until the bounded stream is complete.
3. `POST /reports/{id}/complete-upload` with an empty JSON object and an
   `Idempotency-Key`. Stored bytes, actual PDF signature/structure, encryption,
   ten-page ceiling, readability and supported category are checked. Permanent
   rejection persists `rejected`; a transient verifier failure is retryable.
   Invalid uploads return safe `invalid_upload` errors; oversized streams return
   413, expired sessions 410, concurrency conflicts 409, quota exhaustion 429 and
   unavailable integrations 503. No raw parser/cloud exception is returned.
4. Completion returns the durable `ProcessingJob` (202). Its `reportId` is
   authoritative, including when a duplicate resolves to an existing case.
   `GET /reports/{id}` exposes metadata. Authenticated
   `GET /reports/{id}/document` returns verified PDF bytes in chunks with
   `Cache-Control: no-store`; unverified sources cannot be downloaded. Patient
   ownership, current doctor assignment, active account and hospital are checked
   on each request. Administrators cannot read the document.

A registration key is scoped to hospital/patient and cannot be reused with changed
registration fields. Repeated successful PUTs must contain the same bytes. Accepted
objects are immutable; retrieval also checks their recorded SHA-256 and size.
An uncertain Blob write is tracked before the write and cleaned before another
attempt. There are at most three write attempts and three verification attempts
per reservation. Invalid files may be replaced within those bounds; verified files
cannot be replaced. Client/server interruption cannot enqueue untracked work.

## Transactions, duplicates and quotas

Firestore is authoritative. Transactions buffer writes until all reads finish;
content hashing and PDF/OCR processing happen outside transactions. Blob I/O never
runs in a retried Firestore transaction. A six-minute claim prevents concurrent
writers/verifiers; expiry and the claim token are rechecked before commit.

Successful verification atomically commits the report/case state, source artifact,
patient/hospital hash index, quota counters, audit event, `processingJobs/{jobId}`
and `jobDispatches/{jobId}`. The latter contains `dispatchPending: true`, job/report
IDs, creation/expiry and pipeline version for ticket 06. No queue or in-process
background worker is started by this ticket. A crash after commit can be retried
against the same durable job.

The SHA-256 index is scoped to hospital and patient. An unexpired byte duplicate
returns the existing job/report/case and consumes no new verified-upload quota.
Its provisional report/case is removed and its temporary Blob deleted. A reservation
slot remains occupied if duplicate-byte deletion fails, until trusted cleanup runs.
Another patient receives an independent case; no cross-patient hash result leaks.
Expired reports are not reused as duplicates.

Verified-upload counters use the UTC date at verification: five per patient and
twenty per hospital. Pending admission is separately bounded to five reservations
per patient and twenty per hospital (at most 200 MB of pending source bytes per
hospital). Supplemental reservation limits are twenty per patient and one hundred
per hospital per UTC day, including invalid and duplicate registrations; these
bound reservation/audit churn without charging another verified slot. New keys
count toward admission; retries with the same key do not.

## Expiry and cleanup

Reservations last one hour. Verified report expiry is verification time + 30 days;
document access is denied immediately at that boundary. Verified-content deletion
and operational scheduling remain ticket 13. The reservation cap fails closed if
abandoned uploads accumulate; registration does not silently release storage slots.

Run trusted orphan cleanup with the same Firestore/Blob configuration and credentials:

```sh
backend/.venv/bin/python -m mediflow.uploads --limit 100
```

Each call examines at most 100 expired sessions, claims them, deletes any tracked
Blob and only then removes the provisional metadata, idempotency index and reserved
slot. Active claims are skipped; interrupted cleanup can resume after its two-minute
lease. Duplicate aliases are removed without deleting the canonical case or source.
A successful verified report is never removed by orphan cleanup. Audit events use
opaque IDs and contain no PDF/page text, tokens or provider payloads. Existing
30-day audit/verified-content cleanup is consolidated in ticket 13; it is not yet
an automatically deployed schedule.

## Reproduce verification

```sh
backend/.venv/bin/pytest backend/tests/test_uploads.py
# Within the configured real Firebase emulator environment:
MEDIFLOW_UPLOAD_TEST_FIRESTORE=1 backend/.venv/bin/pytest backend/tests/test_uploads.py
```

The same HTTP suite runs against an explicit transactional database fake or real
Firestore transactions in per-test isolated namespaces. Blob failures are injected
at the external storage seam. Run with Tesseract available to include the real
scanned/unreadable PDF case; it skips explicitly on hosts without Tesseract. Linux
CI and the bounded integration container run it with the actual engine. Tests cover
quota-boundary races, concurrent duplicate completion, restart recovery, uncertain
writes, expiry, cleanup, access denial, malformed/encrypted/unsupported inputs and
exact 10,000,000-byte / ten-page acceptance.

For the isolated real Azure adapter check (synthetic PDF only):

```sh
backend/.venv/bin/python tools/upload_smoke.py init
backend/.venv/bin/python tools/upload_smoke.py infrastructure
backend/.venv/bin/python tools/upload_smoke.py check
backend/.venv/bin/python tools/upload_smoke.py cleanup
backend/.venv/bin/python tools/upload_smoke.py cleanup-status
```

If storage is still provisioning, repeat `infrastructure`; allow scoped RBAC to
propagate before `check`. Stages guard the recorded subscription and require
spending protection On before creation/checks. Cleanup checks exact ownership tags
and is available even if subscription credit changes. Private responses and tokens
stay under ignored `.tooling/issue-5/azure/`; never paste them into tickets. Verify
`all temporary resources deleted: True`, not merely a deletion request. The sanitized
report is `evaluation/reports/private-upload-cloud.json`. This verifies real hosted
Blob storage through the production adapter; it does not claim a deployed hosted
API or a queue-triggered worker.
