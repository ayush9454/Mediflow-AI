# 05: Implement private bounded upload, verification and duplicate detection

Status: completed
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

- [x] Valid digital/scanned PDFs upload privately; forged MIME, oversize, over-page, protected and malformed inputs fail with stable safe codes.
- [x] Repeated registration/completion with the same key creates no duplicate report/case, hash counters or processing request.
- [x] Quota-boundary races cannot exceed agreed limits; duplicate completed files do not consume another slot.
- [x] Another patient, an unassigned doctor and an administrator cannot stream the PDF or obtain a usable public Blob URL.
- [x] Partial/abandoned uploads have a bounded cleanup path and cannot be mistaken for verified sources.

## Verification

Exercise real private Blob upload/download in the hosted dev environment plus integration tests for size/page boundaries, idempotency, duplicate scope, quota races and authorization.

## Implementation record

Implemented on `main` in `3c69dab`, with review fixes in `1969a2c`, against baseline `b676c5b`. See [private upload setup and lifecycle](../../../docs/private-uploads.md).

### Changes

- Authenticated registration, bounded temporary-file PUT, real stored-byte PDF/OCR verification and original-PDF streaming. Actual byte count, 10,000,000-byte / ten-page limits, MIME, encryption, corrupt/unreadable/unsupported inputs, synthetic acknowledgement and expiry are enforced.
- Real private Azure Blob adapter with managed identity in production, no SAS/public document links, immutable object writes, bounded reads and source-integrity checks.
- Firestore transactions atomically persist report/case/source, patient-scoped SHA-256 index, UTC patient/hospital quotas, audit, authoritative processing job and pending dispatch intent. Retries and unexpired duplicates preserve the original case/job. Dispatch remains ticket 06.
- One-hour pending reservations, five/patient and twenty/hospital pending caps, bounded write/verification attempts and reservation admission rates. Trusted orphan cleanup retains bounded attempt keys and a minimal prefix record for delayed writes; verified sources remain protected. Scheduled cleanup and verified-content deletion remain ticket 13.
- API image includes English Tesseract. CI runs the upload suite against real Firestore emulator transactions as well as offline adapters. Shared Azure probe guards now serve both OCR and upload smoke tools.

### Verification

- Final Linux/amd64 backend suite: **95 passed, 1 skipped** at **1 vCPU / 1 GiB**, network disabled, PID limit 128. The skip is the opt-in paired Firebase emulator case. Real Tesseract ran, including valid scanned upload and unreadable PDF rejection. The exact ten-page / 10,000,000-byte input passes.
- Separate actual Firebase Auth + Firestore emulator run: **21 passed, 1 skipped**. The host-only OCR skip is covered by Linux above. Tests include real tokens/rules, patient/hospital quota races, concurrent duplicate completion, same-patient versus cross-patient byte scope, restart recovery, uncertain Blob writes, immediate expiry, cleanup, database outage recovery, and a delayed writer finishing after reservation cleanup.
- Flutter: **19 passed**, analysis clean. Dart contract/API smoke passes and all 18 Dart files remain formatted. No APK rebuild or phone workflow claim is made for this backend ticket.
- Backend mypy: **29 sources**, Ruff lint/format and Python compilation pass. All **8** generated contract artifacts match. Existing hosting probe tests **9 passed**; shared OCR cloud guard tests **2 passed**.
- Real Azure storage-only probe: authenticated bytes matched; anonymous access returned **401**; overwrite was denied and original bytes preserved; bounded prefix listing worked; temporary Blob deletion was verified. [Sanitized observations](../../../evaluation/reports/private-upload-cloud.json). Storage shared-key and anonymous access were disabled; student spending protection remained **On**. Account IDs, endpoints, tokens and raw responses stay ignored.
- Azure cleanup: both temporary resource groups were deleted and their absence independently verified. No hosted production API or queue worker was deployed, and no remote CI result is claimed.

### Review

Two independent axes reviewed `b676c5b...3c69dab`, then `3c69dab...1969a2c`:

- **Standards:** zero remaining hard violations or actionable baseline smells. Shared probe initialization and stale OCR documentation were corrected; required Dart validation passed.
- **Spec:** zero remaining actionable findings. The two initial recovery findings were fixed with regression tests: the upload slot is always released after database failures, and durable prefix sweeps remove stale storage writes after takeover/cleanup without deleting the canonical source.

All acceptance criteria are complete. The test emulators and Linux VM started for verification were stopped.

## Comments

- 2026-10-20: Created from the user-confirmed project plan. No implementation performed.

- 2026-10-23: Implemented private upload and durable admission, completed the two-axis review and recorded local/emulator/real-Blob verification above. Both temporary Azure groups are confirmed absent; ticket completed.
