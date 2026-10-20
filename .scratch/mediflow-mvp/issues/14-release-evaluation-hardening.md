# 14: Measure held-out quality and verify security, review and failure behavior

Status: ready-for-agent
Type: task
Blocked by: 03, 07, 08, 10, 11, 12, 13
Estimate: 10 hours
Target week: 7

## Outcome

Produce honest release evidence for extraction quality, authorization and recoverable workflow behavior.

## Context

- [Agreed specification](../spec.md)
- [Roadmap and gates](../roadmap.md)
- [Decisions and external-source checks](../decisions.md)
- [Ticket index](../README.md#implementation-tickets)

The benchmark is synthetic and small. Do not generalize it to real-world clinical accuracy or imply that source quotes establish clinical correctness.

## Scope

- Freeze the implementation/model/prompt version, run the ten valid held-out documents and ten negative examples, and record dataset/version hashes and execution environment.
- Report strict row precision/recall (both target at least 95%), per-field results, sample counts and separate digital/scanned results. Inspect evidence and summaries for unsupported claims.
- Run the defined API/rules/storage access matrix, review/assignment concurrency and patient approved-version checks.
- Exercise duplicate completion/delivery, crash recovery, quota exhaustion, provider failure, app reopen, cold start, retry ceilings and retention cleanup.
- Measure per-stage/end-to-end latency, processing failures, provider usage and infrastructure resource consumption. Separate student-credit usage from out-of-pocket spend.
- Fix release blockers without tuning on held-out data. If an investigation exposes held-out examples to tuning, mark that result contaminated and create a newly versioned independent held-out set before claiming fresh performance.

## Acceptance criteria

- [ ] Reproducible Markdown/machine-readable results state achieved metrics honestly, with no invented 95% claim.
- [ ] All defined authorization and review-workflow tests pass; no known cross-user exposure, draft leak or silent review overwrite remains.
- [ ] Reliability tests demonstrate bounded attempts and durable recovery without duplicate clinical versions.
- [ ] Any missed extraction target is explicitly recorded with limitations; the mandatory release gate is not falsely marked passed.
- [ ] Resource and latency measurements accompany extraction results, including actual laptop-off hosted operation.

## Verification

Run the documented release suite against the release-candidate APK/backend, retain sanitized test summaries and metrics, and list remaining defects/limitations with impact.

## Implementation record

Not started. Record actual changes, verification commands/results, measured findings, and any remaining gate here. A readiness label does not imply completion or override the Blocked by line.

## Comments

- 2026-10-20: Created from the user-confirmed project plan. No implementation performed.
