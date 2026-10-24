# Patient PDF upload and recovery

The signed-in patient Reports tab uses the hosted API for PDF registration, streaming upload, completion, case pagination and metadata. History lists terminal processing states. Doctor/admin screens and approved-result presentation belong to later tickets.

## Android behavior

Require acknowledgement of invented patient data before choosing an English laboratory PDF. The Android system document picker grants temporary access without shared-storage permissions. Read at most 10,000,000 bytes; the server verifies the stored PDF, including its 10-page limit and encryption/readability checks. Display upload progress, then the authoritative processing/review status. Workflow labels do not indicate medical urgency.

A private, owner-scoped recovery journal stores filename, byte count, SHA-256, two random idempotency keys and the server report ID. Persist each checkpoint before its request; retry transient upload operations at most once per action with the same keys. A restart requires sign-in again because tokens stay in memory. Continue an interrupted transfer by selecting the same digest/size PDF. Completion recovery does not need the PDF again. Byte-identical completion can return an existing canonical report ID; preserve that ID before reading its metadata. Starting a different upload removes local recovery metadata; abandoned server reservations follow normal expiry cleanup.

Poll every 15 seconds only while the patient reports/history screen is foregrounded. Stop polling on background, tab exit or logout; refresh on resume. A temporary offline account recheck retains the already verified session until actual expiry. Denied or expired sessions clear protected content and return to sign-in.

## Protected document access

Fetch the original through authenticated `GET /api/v1/reports/{id}/document`. Reject non-PDF or oversized responses. Render bounded pages in the Android PDF renderer, using a private temporary file removed after rendering and orphan cleanup at startup. Keep source bytes and rendered images in memory only, clear them on background/close/account change, and disable the open button after retention expiry. No public document URL, AI provider key, draft-analysis endpoint or raw server error is used by this UI.

## Patient cases API

`GET /api/v1/cases?limit=20&cursor=...` filters hospital and patient ownership in Firestore before bounded pagination. Its opaque cursor is scoped to that account; every result is rechecked transactionally against its report. Return only workflow metadata and expiry. Authorization-only legacy seed records without an upload workflow are omitted. Doctor/admin listing is deferred to their role-workflow ticket and currently denied.

## Build and verification

Use the normal setup in [development](development.md), with public Firebase configuration and an HTTPS API origin in an ignored Dart defines file:

```sh
cd app
../tools/flutterw build apk --debug --no-pub --dart-define-from-file=/path/to/private-defines.json
../tools/flutterw test --no-pub
```

See [hosted acceptance tooling](../tools/patient_smoke/README.md). The APK uses debug signing; release signing/distribution remains ticket 15. A temporary acceptance endpoint must be replaced with a live deployment before using that APK after teardown.
