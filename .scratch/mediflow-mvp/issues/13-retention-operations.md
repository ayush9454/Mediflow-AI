# 13: Implement thirty-day expiry, cleanup and bounded operational controls

Status: completed
Type: task
Blocked by: 05, 06, 08, 11
Estimate: 10 hours
Target week: 6

## Outcome

Keep the hosted demo within its retention and resource limits without deleting records inconsistently or recreating expired content.

## Context

- [Agreed specification](../spec.md)
- [Roadmap and gates](../roadmap.md)
- [Decisions and external-source checks](../decisions.md)
- [Ticket index](../README.md#implementation-tickets)

Thirty-day retention applies to simulated approved data as well as drafts. Keep the retained expiry event minimal rather than preserving deleted clinical information inside audit text.

## Scope

- Enforce thirty-day content expiry at every API/worker access before physical cleanup. Schedule trusted deletion of original PDFs, derived artifacts, analyses, approved snapshots and review payloads.
- Record minimal nonclinical expiry outcomes and apply thirty-day rolling audit retention. Do not use paid Firestore TTL.
- Clean abandoned uploads, bound total stored bytes, manual reprocessing, job/provider time, worker concurrency and log volume; document initial values based on ticket 01/07 measurements.
- Provide sanitized admin operational error/status fields and request/job correlation IDs without full document/model payloads.
- Document credit monitoring, expiry/export/reset and service-stop behavior; retain student spending protection and no paid upgrade.

## Acceptance criteria

- [x] Expired reports cannot be accessed even when a cleanup job is delayed.
- [x] Cleanup removes all linked source/clinical payloads and is idempotent across partial failure.
- [x] Queued, in-flight and retrying jobs cannot restore an expired report or republish an old approved snapshot.
- [x] Orphan cleanup, upload quotas, storage ceiling, timeouts and manual-reprocess limits are exercised and visible through safe errors.
- [x] Logging and audit output contain no secrets or full medical payloads; resource consumption stays observable and bounded.

## Verification

Use a controllable clock/expiry fixtures, injected cleanup failures and stale queue messages. Verify both storage objects and Firestore references are removed/restricted, then inspect sanitized logs.

## Implementation record

Completed on 2026-10-25, from baseline `e705c3d`. Implementation commits:
`f67a137`, `358ab00`, `5225ea8`, `85d3458` on the current `main` branch.

### Changes

Implemented report-wide expiry denial and post-storage-read expiry checks; worker
deadlines capped by retention; refreshed expiry checks inside transaction attempts;
resumable trusted deletion of source, clinical/review/approval and job payloads;
minimal rolling expiry/audit records; and independent scheduled maintenance in the
deployment template. Existing Firestore Timestamp and ISO expiry values work.

Registration reserves capacity for three uncertain immutable source writes.
Analyses, reviews and approved snapshots share the same atomic payload ledger,
with rollback on quota exhaustion and a common nonnegative adjustment invariant.
Late-write prefix reservations survive apparent deletion until their safe sweep
window closes. Unsupported legacy capacity initialization fails closed.

Added bounded access/transition audit budgets, metadata-first audit expiry,
sanitized correlated administrator diagnostics, bounded error logging, and a
service-stop configuration. Firestore read-lock and commit aborts share five
transaction attempts without repeating provider/Blob work. Operations documentation
covers initial measured-resource assumptions, credits, export/reset, cleanup and
stop/resume behavior. No paid TTL, billing conversion or paid model fallback.

### Verification

TDD used the existing HTTP, trusted cleanup, coordinator/queue-worker and external
Firestore/storage boundaries. Sixteen retention regressions cover controllable
time, approved/review copies, stale queued/in-flight/retrying work, lost deletion
responses, unavailable sources and small/default/mixed cleanup batches. Review
findings went red before their fixes.

- Full isolated Linux backend suite: **221 passed, 2 opt-in Firebase tests skipped**,
  150.46 seconds, 1 CPU / 1 GiB / network disabled; actual OCR is included.
- Real Auth/Firestore emulator integration: **115 passed, 1 host OCR case skipped**,
  45.25 seconds. Includes actual transactions, concurrency, access/rules and the
  same retention/failure tests. Run-owned namespaces were removed and emulators stopped.
- Flutter: **55 passed**; analysis, 33-file format check and Dart contract/API smoke pass.
- Python formatting/lint/compilation and mypy on 46 sources pass. All eight generated
  contract artifacts match. Nine hosting-probe and two deployment-guard checks pass.
- Bicep compiles the independent five-minute maintenance schedule; the existing
  public-cloud storage-hostname warning remains. Safe missing-configuration cleanup
  behavior was checked without credentials or raw tracebacks.
- Independent Standards and Spec reviews and corrective re-reviews: **zero remaining
  findings on either axis**. See [review](../review-13.md) and
  [sanitized verification](../../../evaluation/reports/retention-operations.json).

### Operational limits and handoff

See [operations](../../../docs/operations.md) for the 1 GB payload budget, conservative
source reservation, audit/log bounds, CLI commands and failed-record deferral.
Automatic cleanup requires deployment of `backend/jobs.bicep`; this ticket compiled
the schedule but did not deploy or claim a hosted cleanup execution. No cloud
resources were created or paid features enabled. Existing Azure adapter deletion
evidence remains in ticket 05; this ticket injects Blob failures at its external
boundary and uses real Firestore transactions locally. Ticket 14's held-out quality
gate and ticket 15's signed APK/deployment handoff remain separate.

## Comments

- 2026-10-20: Created from the user-confirmed project plan. No implementation performed.

- 2026-10-25: Implemented retention and operational controls, completed corrective
  TDD and both independent review axes, verified the final integration suites and
  committed on `main`. Ticket 14 is now unblocked by retention work.
