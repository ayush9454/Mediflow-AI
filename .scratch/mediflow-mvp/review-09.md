# Ticket 09 review

Baseline: `99f462f`. Initial implementation: `f4d8b1c`.
Reviewed diff: `git diff 99f462f...HEAD`, followed by the corrective working-tree diff.
The code-review skill ran separate Standards and Spec reviewers in parallel.

## Standards

- Late PDF downloads could repopulate the viewer after background cleanup. Resolved with a viewer generation, foreground, report identity and expiry guard. Late bytes/images are wiped. A widget regression failed before the fix and passes afterward.
- A same-UID hospital change kept the previous report host because its key omitted hospital scope. Resolved by including hospital ID; a navigation regression verifies old-controller disposal and the new owner. The regression failed before the fix.
- Possible primitive obsession: the response byte ceiling also selected PDF MIME/validation policy. Resolved with an explicit `expectPdf` flag.

The follow-up smoke-tool review identified cleanup races and duplicate aliases. Cleanup now discovers run-owned upload sessions independently, retains foreign canonical reports, checks terminal processing before deletion, conditionally releases shared worker leases in a transaction, persists a resumable deletion manifest and requeries linked payload collections before confirming removal. The final Standards follow-up found all original and cleanup findings resolved; actual cleanup evidence is recorded separately.

## Spec

- Same-UID hospital changes could retain the previous hospital's protected content, violating account-change cleanup. Resolved with the scoped host key and regression above.
- No unrequested scope expansion found. Approved-result presentation, evidence rows and doctor/admin workflows remain later tickets.

The corrective Spec review found no remaining ticket-09 code issues. Hosted and Android acceptance are recorded in the ticket and sanitized verification artifact.

## Validation

The full Linux backend suite passed 162 tests, with one optional Firebase-emulator test skipped. The full Flutter suite passed 33 tests. Python lint/format, mypy (38 sources), generated artifacts, Flutter analysis and Dart contract/API smoke checks passed. The configured development APK built and installed on Android 15/API 35.

Initial findings: Standards 2 documented breaches plus 1 optional smell; Spec 1 finding (the hospital-scope issue also identified by Standards). All initial findings were resolved. Both corrective reviews found no unresolved findings. Follow-up verification is recorded in the implementation/acceptance commit.

The real cold-start check observed zero replicas, a safe startup-unavailable state, and successful manual retry. Run-owned Firestore payload cleanup passed; Azure teardown confirmation is tracked in the sanitized acceptance artifact.

Initial Standards: 3 findings, worst late PDF content after background cleanup; initial Spec: 1 finding, worst previous-hospital content retention. Three later smoke-cleanup findings were also resolved. Final unresolved findings: Standards 0, Spec 0.

Azure delayed the empty environment in `ScheduledForDelete`. A final read-only review approved the guarded exact-environment DELETE retry and status diagnostics; all other resource IDs must already be absent. No additional findings.
