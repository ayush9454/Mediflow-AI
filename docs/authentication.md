# Authentication and authorization

The Android app signs into Firebase email/password over its REST interface and sends the ID token to the backend `/api/v1/me`. The backend verifies its signature, issuer, audience, expiry, revocation and Auth disabled state through Firebase Admin. Roles and hospital membership are read afresh from server-owned `users/{uid}` and active `hospitals/{id}` records. Firebase custom role claims, request roles and patient identifiers never grant access.

Configure `MEDIFLOW_FIREBASE_PROJECT_ID` and backend-only Application Default Credentials (`GOOGLE_APPLICATION_CREDENTIALS` or an attached Google service identity). Never place Admin credentials in the APK. The app needs `API_BASE_URL` and the Firebase project's public `FIREBASE_API_KEY` in its private build defines file; the API key identifies the project and does not authorize clinical reads. Public signup has no app interface; even an unseeded Auth user has no backend access.

## Trusted synthetic bootstrap

Enable the email/password provider and create Firestore on the existing Spark project. Deploy `firebase/firestore.rules` using `firebase deploy --only firestore:rules --project PROJECT`. All direct mobile Firestore reads/writes, including user promotion and audit mutations, are denied. Admin SDK credentials bypass rules and must remain backend-only.

Create an owner-readable JSON file (`chmod 600`) containing keys `patient_a`, `patient_b`, `doctor_a`, `doctor_b`, `administrator`; each value is `{ "email": "UNIQUE@example.test", "password": "UNIQUE_RANDOM_SECRET_AT_LEAST_16_CHARACTERS" }`. Do not commit this file. With trusted ADC:

```sh
export MEDIFLOW_FIREBASE_PROJECT_ID=PROJECT
backend/.venv/bin/python -m mediflow.seed --confirm-project PROJECT --synthetic-only --secrets-file /private/path/accounts.json
```

This creates one synthetic hospital, five active users and an access-control report/case fixture (patient A, doctor A). It has no uploaded PDF or analysis. Existing Auth passwords are preserved; rerunning restores seeded server roles/active status but preserves assignment on an existing fixture. The seed validates every credential before mutation, but is not a cross-provider transaction; a failed run can be retried. The CLI has no HTTP route and requires both Auth administration and Firestore write privileges. Never give this identity to clients.

## Authorization seam for later tickets

Every route authenticates first. `Authorization.report_access(account, report_id, action, request_id)` loads current report and case records and enforces hospital, patient ownership, current doctor assignment and operation role. Call it before retrieving payloads; never authorize a future document/result from a mobile field or stale assignment. The Firestore adapter obtains assignment/version from `cases`, overriding copies in report metadata. Administrators can access workflow metadata but are denied document/result/review/reprocess access. Missing/forbidden resource IDs produce the same 403. The current document/result/upload/assignment implementations remain unavailable after successful authorization until their respective tickets land.

Minimal access audits contain opaque actor, hospital and resource identifiers, action, outcome, server time, request ID and a 30-day expiry marker. They contain no tokens, provider error text, filenames, PDF text or clinical values. Protected data is not returned if its audit cannot be persisted. The expiry marker is not automatic deletion; scheduled cleanup/TTL configuration and broader audit volume limits belong to ticket 13.

All protected HTTP responses use `Cache-Control: no-store`. The app keeps credentials/tokens only in memory, discards the refresh token, and requires login after ID-token expiry or backend denial on session revalidation. Resume revalidates `/me`; role/hospital changes clear temporary bytes before navigation. Logout/account switching wipes the shared `SensitiveCache`. Future viewers must use that cache or an equally session-scoped disposable store; do not add persistent clinical caches.

## Verification

```sh
cd backend
.venv/bin/pytest tests/test_authorization.py
.venv/bin/mypy src/mediflow
```

For real Firebase verifier, Firestore persistence and client rule checks, run from the repo root with Firebase CLI and Java installed:

```sh
firebase emulators:exec --project demo-mediflow --only auth,firestore \
  'MEDIFLOW_ENV=test backend/.venv/bin/pytest backend/tests/test_firebase_emulators.py'
```

This seeds synthetic identities, signs in all three roles through Auth, verifies their actual emulator ID tokens through the backend, checks direct reads/writes are denied for six collections, and verifies doctor reassignment revokes the former doctor's next request. The emulator test is explicitly skipped outside the paired emulators. Emulator adapters require `test`, both host variables and a `demo-` project; production startup rejects emulator configuration. Injectable test authorization is accepted only by `create_app(Settings(environment="test"), ...)`, with no environment switch to enable it in deployment.

Firebase interfaces follow [ID-token verification](https://firebase.google.com/docs/auth/admin/verify-id-tokens) and [email/password REST authentication](https://firebase.google.com/docs/reference/rest/auth).
