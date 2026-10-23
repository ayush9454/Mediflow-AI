# Ticket 06: implementation review

Baseline: `e29a5fae83dd866103921f36ba4420e5b32b596e`.
Initial implementation: `0088d0f`. Reviewed the committed diff and then the working
tree fixes with separate Standards and Spec agents using the code-review skill.
Specification: [ticket 06](issues/06-durable-processing-jobs.md) and
[agreed specification](spec.md), especially sections 4, 6, 8–10.

## Standards

Initial review: no documented-standard violations; two advisory smells.

1. Possible Duplicated Code: API and worker separately constructed credentials,
   Blob/Queue adapters and job configuration. Resolved with the shared trusted
   `create_job_services` factory and `JobServices` composition.
2. Possible Refused Bequest: the jobs acceptance probe inherited OCR-specific
   lifecycle behavior and read a saved template file to customize it. Resolved by
   extracting `ContainerJobProbe`, shared guarded infrastructure, a non-mutating
   job template, Docker setup and cleanup. Both probes now use that common base.

Follow-up report: both advisories resolved; no new documented-standard violations
or actionable baseline smells. **0 unresolved Standards findings.**

## Spec

Initial review: three actionable findings; no scope creep.

1. P1, stranded existing accepted work: ticket-05 intents lacked the fields queried
   by the reconciler. The requirement is to “recover without losing the authoritative
   job.” Resolved by bounded document-ID pagination, idempotent adoption and a durable
   migration checkpoint. Deployment replaces old writers before completing the scan.
2. P2, incomplete processing audits: specification section 10 requires auditing
   processing state/result creation. Resolved with atomic deterministic per-attempt
   start/retry events containing job, attempt, analysis and version references.
3. P2, late failure reports bypassed deadline fencing: an old worker could permanently
   fail a timed-out run before recovery. Resolved by checking the persisted deadline
   and using bounded timeout recovery for a late failure report.

Follow-up report: no unresolved actionable Spec findings. Migration, attempt audits,
late-failure fencing and the transactional hospital capacity lease satisfy their
requirements. No authorization, expiry, retry or approved-snapshot regression was
observed in shared platform composition. **0 unresolved Spec findings.**

Standards: 0 unresolved; Spec: 0 unresolved. Neither axis has a remaining worst issue.
Execution, measurement and resource-cleanup evidence is recorded in the ticket.
