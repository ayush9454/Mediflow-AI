# 13: Implement thirty-day expiry, cleanup and bounded operational controls

Status: ready-for-agent
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

- [ ] Expired reports cannot be accessed even when a cleanup job is delayed.
- [ ] Cleanup removes all linked source/clinical payloads and is idempotent across partial failure.
- [ ] Queued, in-flight and retrying jobs cannot restore an expired report or republish an old approved snapshot.
- [ ] Orphan cleanup, upload quotas, storage ceiling, timeouts and manual-reprocess limits are exercised and visible through safe errors.
- [ ] Logging and audit output contain no secrets or full medical payloads; resource consumption stays observable and bounded.

## Verification

Use a controllable clock/expiry fixtures, injected cleanup failures and stale queue messages. Verify both storage objects and Firestore references are removed/restricted, then inspect sanitized logs.

## Implementation record

Not started. Record actual changes, verification commands/results, measured findings, and any remaining gate here. A readiness label does not imply completion or override the Blocked by line.

## Comments

- 2026-10-20: Created from the user-confirmed project plan. No implementation performed.
