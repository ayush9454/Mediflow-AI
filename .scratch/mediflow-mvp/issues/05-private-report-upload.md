# 05: Implement private bounded upload, verification and duplicate detection

Status: in-progress
Type: task
Blocked by: 01, 04
Estimate: 8 hours
Target week: 2

## Outcome

An authorized synthetic PDF upload creates exactly one report/case and private source artifact.

## Context

- [Agreed specification](../spec.md)
- [Roadmap and gates](../roadmap.md)
- [Decisions and external-source checks](../decisions.md)
- [Ticket index](../README.md#implementation-tickets)

Stream and enforce byte bounds before allowing unbounded storage usage. Do not implement an unrestricted direct Blob upload token that bypasses size enforcement.

## Scope

- Implement registration, authenticated streaming PUT upload, completion verification and authorized original-PDF streaming using server-generated IDs/paths.
- Enforce English PDF scope, actual signature/content, 10,000,000-byte and ten-page limits, encrypted/corrupt/unreadable-file handling and synthetic-data acknowledgement.
- Store verified originals in private Azure Blob Storage; prohibit anonymous reads and permanent public links. Bound partial uploads/reservations and clean abandoned objects.
- Compute SHA-256 from stored bytes; same-patient byte duplicates return the existing unexpired report/case without duplicate quota/job creation or cross-patient leakage.
- Atomically enforce five new verified reports per patient and twenty hospital-wide per UTC day. Maintain idempotency through registration/completion retries and establish expiresAt on successful verification.
- Record upload/access events and expose safe status/errors. Persist an authoritative processing-job request for ticket 06 rather than dispatching untracked in-memory work.

## Acceptance criteria

- [ ] Valid digital/scanned PDFs upload privately; forged MIME, oversize, over-page, protected and malformed inputs fail with stable safe codes.
- [ ] Repeated registration/completion with the same key creates no duplicate report/case, hash counters or processing request.
- [ ] Quota-boundary races cannot exceed agreed limits; duplicate completed files do not consume another slot.
- [ ] Another patient, an unassigned doctor and an administrator cannot stream the PDF or obtain a usable public Blob URL.
- [ ] Partial/abandoned uploads have a bounded cleanup path and cannot be mistaken for verified sources.

## Verification

Exercise real private Blob upload/download in the hosted dev environment plus integration tests for size/page boundaries, idempotency, duplicate scope, quota races and authorization.

## Implementation record

Not started. Record actual changes, verification commands/results, measured findings, and any remaining gate here. A readiness label does not imply completion or override the Blocked by line.

## Comments

- 2026-10-20: Created from the user-confirmed project plan. No implementation performed.
