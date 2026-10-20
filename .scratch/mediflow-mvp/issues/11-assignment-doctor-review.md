# 11: Implement administrator assignment and immutable version-specific doctor review

Status: ready-for-agent
Type: task
Blocked by: 04, 10
Estimate: 12 hours
Target week: 5

## Outcome

An eligible assigned doctor can turn an AI candidate into an auditable approved or rejected review without silent overwrites.

## Context

- [Agreed specification](../spec.md)
- [Roadmap and gates](../roadmap.md)
- [Decisions and external-source checks](../decisions.md)
- [Ticket index](../README.md#implementation-tickets)

The review screen must not make clinical claims. Audit event creation is part of the same reliable transition, not a best-effort client request.

## Scope

- Implement paginated administrator workflow lists, active eligible doctor lists, assignment/reassignment and sanitized status diagnostics without clinical payloads.
- Implement doctor assigned-case list and begin-review/approve/correct-and-approve/reject actions against an explicit analysis version.
- Require every blocking issue to be corrected or explicitly acknowledged unresolved with a reason before approval. Preserve source links and the original AI values.
- Use transactional/version checks and idempotency for review decisions; append immutable review history and update the approved snapshot atomically.
- Recheck current assignment at review time. Reprocessing requires fresh approval and leaves the existing approved snapshot visible until replacement approval.
- Record server-controlled assignment/review/audit events with appropriate authorship and timestamps.

## Acceptance criteria

- [ ] Administrator can assign/reassign but cannot open PDFs, AI drafts, clinical results or correction payloads.
- [ ] Only the currently assigned active doctor can review/reprocess a case.
- [ ] Approve, correct-and-approve, qualified unresolved approval and reject are distinguishable, attributed and preserved.
- [ ] Duplicate review requests do not create duplicate decisions; stale version/assignment conflicts cannot overwrite a newer result.
- [ ] Rejected/failed replacement analyses do not remove the patient's previous approved result.

## Verification

Run API integration and concurrency tests for review/assignment races, duplicate requests, unresolved flags, preserved originals and replacement approval; complete the corresponding Android flows.

## Implementation record

Not started. Record actual changes, verification commands/results, measured findings, and any remaining gate here. A readiness label does not imply completion or override the Blocked by line.

## Comments

- 2026-10-20: Created from the user-confirmed project plan. No implementation performed.
