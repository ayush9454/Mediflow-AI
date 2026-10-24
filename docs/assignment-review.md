# Assignment and simulated doctor review

Ticket 11 adds the administrator and assigned-doctor workflows to the existing
synthetic-only Android application. These actions review extracted document data;
they do not establish clinical correctness or make diagnoses.

## Administrator

The Cases tab pages through hospital workflow metadata: opaque case/report/patient
references, assignment, independent processing/review statuses, timestamps, versions,
expiry and an allowlisted processing error code. It never retrieves clinical rows,
source quotations, correction payloads or document bytes. The Doctors tab lists
active hospital doctor profiles whose server-owned user account is also active and
has the doctor role. Department metadata comes from the trusted doctor profile.
The initial trusted seed uses `Laboratory`; existing profiles without a department
show `General` until updated by the trusted account operator.

Assign/reassign requires the displayed case version and an idempotency key.
Assignment eligibility, actor activity, hospital state and the case/report
relationship are checked again inside the transaction. Assignment advances the
case version and resets an in-progress review to pending. Subsequent former-doctor
requests are denied. The server cannot erase content already downloaded to a device.

## Doctor

Assigned cases link to laboratory evidence and the version-specific review screen.
The Reviews tab offers the same currently assigned cases with their immutable
review history. Begin review advances the case version and records `under_review`.

The review editor displays original AI values and lets a doctor correct each printed
field, supply source page/quotation/origin and explain the change. Corrections retain
the immutable AI candidate. The backend checks quotations against the candidate's
preserved source text, checks printed fields against those quotations and rejects
new detectable conflicts. This establishes traceability, not medical interpretation.
A source-derived correction without valid evidence is rejected.

Every original blocking issue must be corrected in its corresponding field or
explicitly acknowledged unresolved with a nonblank reason. Clearing an issue list
or changing an unrelated field does not resolve a blocker. Document-level blockers
require unresolved acknowledgement. The server owns the resulting issue list;
client-supplied issue lists cannot clear flags. Original-to-corrected rows and
reasons are retained in the immutable review record. Qualified approvals preserve
unresolved reasons in the patient-visible approved snapshot. Rejection requires a
reason and cannot carry corrections or unresolved approvals.

The screen distinguishes approval, correction and approval, qualified approval,
and rejection. An interrupted submission offers **Retry same operation** using the
same exact payload and key. Backgrounding, expiry, session loss and detected
assignment/version changes clear the editor. Foreground access checks run every
15 seconds while the screen is active; the server rechecks permissions on every
request. A concurrent change produces a refresh-required conflict.

## Atomic persistence and versions

`POST /cases/{caseId}/assignment`, `POST /reports/{reportId}/begin-review` and
`POST /reports/{reportId}/review` commit their state and audit transition together
through the shared Firestore transaction adapter. The request must match the latest
analysis ID/version, case version and prior review version. Reviews are terminal
for that candidate; another decision needs a new processing candidate. Reprocessing
is forbidden while another run is active, and the old candidate cannot be approved
while replacement processing is pending or failed.

Separate `assignmentKeys`, `beginReviewKeys` and `reviewKeys` records scope replay
to hospital, actor, resource and operation. Reusing a key with a different payload
conflicts. A replay still requires current activity, assignment and retention access.
Reviews, their index and server-authored audit event are appended once; the approved
snapshot is changed only by an approval in the same transaction. Audit records
contain versions, author, time and correction/qualification counts, with no clinical
payload or correction text. The approved summary is a server-generated reviewed-row
count so an old AI summary cannot contradict corrected fields.

A rejected or failed replacement leaves the previous approved snapshot intact.
A replacement approval atomically changes the snapshot and advances the review
version. Expiry denies access regardless of which version was approved.

`GET /cases`, `GET /doctors` and `GET /reports/{reportId}/reviews` use bounded pages
and actor/role/resource-scoped cursors. Clients must follow `nextCursor` even when a
page is empty, because ineligible or legacy records can be filtered after querying.
Review history is paged by opaque record ID; review versions identify decision order.
The lists use the existing Firestore query adapter with equality filters and
document-ID ordering.

## Verification

Focused API and Flutter tests exercise real public workflow boundaries. The same
API tests run against actual Firestore emulator transactions in the Firebase CI job,
including assignment/review races and duplicate submissions. Local Linux execution
provides native PDF/OCR behavior. Installed Android acceptance uses synthetic
in-memory clinical fixtures and real Firebase token verification; it does not deploy
a production API or establish the later hosted end-to-end/release gates.
