# 06: Implement durable queued jobs, bounded retries and crash recovery

Status: in-progress
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

- [ ] An accepted job continues with the app closed and the developer laptop off.
- [ ] Duplicate delivery and completion-after-restart produce at most one candidate per logical run and one quota/audit transition.
- [ ] Crashes before enqueue, during processing and after result commit recover without losing the authoritative job.
- [ ] Transient failures stop after three total attempts; permanent failures do not loop; authorized manual retry creates a distinct bounded run.
- [ ] Unauthorized retry, expired source and stale/repeated reprocess requests behave predictably.

## Verification

Inject failures at dispatch, lease acquisition, processing, result commit and acknowledgement boundaries. Exercise at least one queue-triggered hosted job. Assert durable state and result counts, not merely HTTP success.

## Implementation record

Implementation in progress on `main`, from baseline `e29a5fa`. The user confirmed
the coordinator, reprocess HTTP endpoint and queue worker as test boundaries.
Durable dispatch/recovery, execution fencing, a three-attempt ceiling, expiry and
bounded authorized reprocessing are implemented. Hosted verification and final
two-axis review remain in progress; completion evidence will be recorded here.

## Comments

- 2026-10-20: Created from the user-confirmed project plan. No implementation performed.
