# 06: Implement durable queued jobs, bounded retries and crash recovery

Status: completed
Progress: implementation reviewed, hosted verification passed, and temporary resource deletion confirmed
Type: task
Blocked by: 01, 04
Estimate: 12 hours
Target week: 2–3

## Outcome

Processing survives app closure, duplicate delivery and worker interruption without duplicating records or losing accepted work.

## Context

- [Agreed specification](../spec.md)
- [Roadmap and gates](../roadmap.md)
- [Decisions and external-source checks](../decisions.md)
- [Ticket index](../README.md#implementation-tickets)

Use a lightweight deterministic processing stub until tickets 07/08 exist; clearly label it as a test adapter and prevent it from serving fabricated production/demo analysis.

## Scope

- Implement Firestore-authoritative processing job records, Azure Storage Queue dispatch and a bounded-concurrency Container Apps Job worker.
- Persist dispatch intent and provide bounded reconciliation for jobs saved but not enqueued. Use attempt IDs, leases/visibility and idempotent result commits for duplicate messages and interrupted executions.
- Represent queued/processing/succeeded/failed/rejected separately from assignment and review. Include safe failure codes, attempt timestamps and pipeline/config versions.
- Permit at most initial attempt plus two automatic retries for transient failures, with backoff and finite timeouts. Permanent invalid-document errors must not retry. Avoid nested provider/SDK retries defeating this ceiling.
- Implement authorized idempotent manual retry/reprocess entry points with rate limits, fresh analysis identity and preservation of existing approved snapshots.
- Make expiry terminal for content processing: a stale message must not regenerate expired data.

## Acceptance criteria

- [x] An accepted job continues with the app closed and the developer laptop off.
- [x] Duplicate delivery and completion-after-restart produce at most one candidate per logical run and one quota/audit transition.
- [x] Crashes before enqueue, during processing and after result commit recover without losing the authoritative job.
- [x] Transient failures stop after three total attempts; permanent failures do not loop; authorized manual retry creates a distinct bounded run.
- [x] Unauthorized retry, expired source and stale/repeated reprocess requests behave predictably.

## Verification

Inject failures at dispatch, lease acquisition, processing, result commit and acknowledgement boundaries. Exercise at least one queue-triggered hosted job. Assert durable state and result counts, not merely HTTP success.

## Implementation record

Implemented on `main`, from baseline `e29a5fa`, on 2026-10-23. The user confirmed
the coordinator, reprocess HTTP endpoint and queue worker as test boundaries.
Implementation commit: `0088d0f`; reviewed fixes: `e748686`.

- Upload acceptance atomically saves authoritative job state, run/analysis identity,
  source metadata, quotas and dispatch intent. A bounded scheduled reconciler repairs
  uncertain/missing enqueue, lost messages and expired execution leases. A resumable
  bounded migration also adopts the prior ticket-05 intent shape; deploy the new API
  writers before completing this one-time scan.
- Azure messages contain only opaque job IDs. Transactional attempt/lease fencing,
  one content-processing capacity lease per hospital, deterministic audit IDs and an
  atomic immutable candidate/result commit prevent duplicate effects. Attempt records
  carry safe failure codes, start/deadline/finish times and pipeline/config versions.
- Transient failures have at most three attempts with 30/120-second backoff; invalid
  documents reject permanently. A configurable deadline is capped at 270 seconds,
  execution lease at 330 and queue visibility at 360. Late result and failure reports
  cannot bypass deadline fencing. Azure SDK retries and platform retries are zero;
  Firestore transaction retries never execute processing/providers.
- `POST /reports/{id}/reprocess` checks current assignment in its transaction, expected
  latest candidate, source/expiry, per-key request identity, cooldown and daily limits.
  Null expected candidate supports failed initial runs. Every manual run receives a
  fresh analysis identity and independent retry budget; prior approved IDs/snapshots
  remain unchanged. Expiry is checked during dispatch, claim and commit, including
  a report removed before a stale delivery arrives.
- API/worker share one trusted platform factory. `backend/jobs.bicep` defines separate
  event and scheduled Consumption Jobs with bounded resources and no platform retry.
  The deterministic empty/blocking candidate adapter requires an explicit test flag
  and test environment. Normal execution reports `integration_not_configured` until
  ticket 08 supplies the real candidate provider; no fabricated demo analysis is served.

Verification:

- Red/green coordinator, HTTP and worker slices exercised uncertain dispatch, failed
  lease acquisition, process termination, pre-commit rollback, a lost commit response,
  acknowledgement failure, concurrent completion, backoff/exhaustion, permanent errors,
  reprocessing rate/idempotency/stale-assignment behavior, expiry, legacy pagination
  and capacity across distinct jobs.
- Final full Linux/amd64 backend suite, real Tesseract, no network, 1 GiB / 1 CPU /
  128 processes: **115 passed, 1 skipped** in 119.55 seconds. The skip is the opt-in
  Firebase emulator check, separately verified below. The earlier local suite was
  **109 passed, 3 skips** before review fixes; two skips required real OCR.
- Real Auth/Firestore emulator run using `MEDIFLOW_UPLOAD_TEST_FIRESTORE=1`,
  `test_firebase_emulators.py test_jobs.py test_worker.py`: **23 passed** after all
  migration/deadline/audit/capacity fixes. Uses real transaction contention/pagination
  and direct mobile-rule authorization denial, with isolated temporary collections.
- Flutter full suite: **19 passed**; analysis clean. Dart contract smoke passed.
  Eight generated contract artifacts checked; `expectedLatestAnalysisId` is required
  but nullable to represent an initial failed run. Python mypy **33 sources passed**;
  Ruff lint/format, compileall and `git diff --check` passed. Hosting guard suites:
  **9 + 2 passed**. Bicep compiles; its public-Azure endpoint emits an informational
  portability lint warning, not a compilation error.
- Actual Azure Central India event/scheduled Jobs ran the final Linux worker with
  real private Blob, Azure Queue and Firestore. The seed accepted one synthetic upload
  without enqueueing it locally. The hosted five-minute schedule dispatched it and
  the queue automatically triggered completion. A separately authorized idempotent
  reprocessing run also completed. This proves laptop-independent dispatch/execution;
  no new physical phone/laptop-off manual drill is claimed.
- Two additional identical queue references produced two successful hosted executions
  with **no new candidate, attempt, quota charge or success audit**. Final durable
  counts: **2 jobs, 2 attempts, 2 immutable candidates, 2 commit records, 2 success
  audits**, and the original four admission/upload quota counters each stayed at one.
  Four event executions succeeded and the queue was empty. Test-adapter attempt wall
  times were **2.56 and 2.78 seconds**; these measure neither OCR nor LLM performance.
- Separate Standards and Spec reviews found two advisory smells and three Spec gaps;
  all were fixed and re-reviewed: **0 unresolved findings on either axis**. Details:
  [review record](../review-06.md). [Sanitized evidence](../job-evidence.json),
  [operator documentation](../../../docs/jobs.md), and
  [repeatable cloud check](../../../tools/jobs_smoke/README.md).

Student spending protection was verified **On** before each cloud mutation; no paid
conversion, billing link, Marketplace service, public document access or permanent
test credential was introduced. Temporary resource deletion and isolated Firestore
cleanup are verified. Production/demo
analysis remains ticket 08, and physical retention cleanup remains ticket 13.

Cleanup completed on 2026-10-24: the isolated Firestore namespace is verified empty,
and Azure confirms the entire temporary resource group is absent. The empty
Consumption environment previously remained in `ScheduledForDelete` after the
Jobs, registry, storage and managed identity were removed; that deletion has now
finished. Private ownership/account references remain only in ignored probe state.

## Comments

- 2026-10-20: Created from the user-confirmed project plan. No implementation performed.

- 2026-10-24: While resuming ticket 07, `tools/jobs_smoke/cloud.py cleanup-status` confirmed **all temporary Azure resources deleted: True**. The ticket-06 group is absent; the previously verified empty Firestore namespace and this final Azure observation complete cleanup. All acceptance and cleanup gates are satisfied.
