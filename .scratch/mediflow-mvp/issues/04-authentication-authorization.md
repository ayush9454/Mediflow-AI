# 04: Implement seeded authentication and deny-by-default permissions

Status: in-progress
Progress: implementation and local verification complete; live Firebase configuration and integration review in progress
Type: task
Blocked by: 02
Estimate: 8 hours
Target week: 1–2

## Outcome

Make role and resource authorization a shared backend boundary before exposing documents or clinical data.

## Context

- [Agreed specification](../spec.md)
- [Roadmap and gates](../roadmap.md)
- [Decisions and external-source checks](../decisions.md)
- [Ticket index](../README.md#implementation-tickets)

Use synthetic account information and secrets via environment/secret storage. Auth token verification must be real in the deployed environment; test overrides cannot be enabled there.

## Scope

- Configure Firebase email/password authentication, trusted seed/bootstrap for one hospital and active patient/doctor/administrator accounts, and no public signup UI.
- Verify Firebase ID tokens and server-controlled active status/role/hospital membership on protected endpoints. Add authorization helpers for patient ownership and current doctor assignment.
- Use backend-only clinical record access; deny direct mobile Firestore clinical reads/writes and client audit mutations. Do not rely on client navigation to protect endpoints.
- Add Android sign-in, sign-out, role navigation and session-expiry behavior. Clear temporary sensitive state/cache when signing out or switching accounts.
- Create safe authorization audit events without exposing document contents or secrets; keep administrator operational metadata distinct from clinical payloads.

## Acceptance criteria

- [x] Each seeded role signs in and lands on the intended navigation shell.
- [x] Missing/invalid tokens, inactive users, forged role/patient fields and cross-hospital/resource access are denied consistently.
- [x] Patient A cannot read patient B's records; unassigned doctors and administrators cannot read clinical documents/results.
- [x] Seed scripts require trusted execution and never enable self-promotion from the client.
- [x] Firestore rules and backend checks both reject their respective bypass attempts.

## Verification

Use API authorization tests and Firebase emulator/rules checks for direct access. Include reassignment authorization through a representative seeded case, even before full assignment UI exists.

## Implementation record

Implemented in isolated `implement/ticket-04` worktree, with the existing HTTP, Firebase rules/emulator and Android session/navigation seams exercised test-first.

- Added real Firebase Admin ID-token verification with revocation/disabled-user checks, server-owned active account/hospital records, and one shared authorization module. No environment variable can install a fake identity. Production rejects emulator configuration; paired emulators require a `demo-` project and test environment.
- Added trusted ADC-only synthetic bootstrap for one hospital, patient A/B, doctor A/B and administrator. No public signup or promotion endpoint. A seeded case provides ownership/current-assignment authorization without implementing the later upload/review workflows.
- Protected HTTP routes now check operation roles, hospital scope, ownership and current case assignment before workflow handling. Metadata reads return server records; document/result/upload/review/assignment workflows remain unavailable after authorization until their own tickets. Reassignment is loaded from the current case on each request.
- Added minimal server-persisted allow/deny audits without tokens, clinical payloads or provider errors. Audit persistence failures fail closed. A 30-day expiry marker is recorded; scheduled cleanup/TTL and broader volume controls remain ticket 13.
- Implemented Android email/password Firebase REST sign-in, backend `/me` role shells, sign-out, in-memory token expiry, resume revalidation, trusted-role deep-link guards and sensitive temporary byte wiping on logout, account/role/hospital changes and session expiry. Refresh tokens are discarded and session expiry requires login. No clinical disk cache exists.
- Added emulator configuration, real Auth/Firestore/rules integration checks, public Firebase build configuration names, generated OpenAPI update and [operator instructions](../../../docs/authentication.md).

Verification (2026-10-23):

- `cd backend && .venv/bin/pytest`: **65 passed, 1 skipped** (the opt-in emulator test).
- Firebase CLI `emulators:exec --config firebase.json --project demo-mediflow --only auth,firestore 'MEDIFLOW_ENV=test backend/.venv/bin/pytest backend/tests/test_firebase_emulators.py'`: **1 passed**. Uses real emulator sign-in and Admin token checks, five seeded identities, 60 direct Firestore read/write denials across users/reports/cases/analyses/reviews/auditEvents, clinical role denial and reassignment revocation. Required explicit local socket/network execution permission; no live project was changed by this test.
- `cd backend && .venv/bin/mypy src/mediflow`: **passed, 19 sources**. Ruff lint and format checks passed for 25 Python source/test files.
- `cd app && ../tools/flutterw analyze --no-pub`: **passed**. Full `../tools/flutterw test --no-pub`: **19 passed**, including every seeded role's sign-in navigation, logout, forbidden role deep links, REST ID-token forwarding, revoked-account revalidation, switching accounts and open-screen expiry/cache clearing.
- `backend/.venv/bin/python tools/export_contracts.py --check`: **8 generated artifacts checked**.

Remaining integration evidence: parent session is enabling/verifying the existing Spark project's Auth provider, Firestore and client deny rules, running the trusted live seed/smoke, and arranging combined Standards + Spec review before integrating. `python -m mediflow.auth_smoke --secrets-file PRIVATE_JSON` uses production settings and live Firebase services while exercising the backend through TestClient; it must not be described as verification of a publicly deployed API. No production verification claim is made here yet.

## Comments

- 2026-10-20: Created from the user-confirmed project plan. No implementation performed.

- 2026-10-23: Implementation and local verification recorded; live configuration and combined integration review tracked by parent session.
