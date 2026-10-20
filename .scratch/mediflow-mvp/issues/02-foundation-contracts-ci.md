# 02: Create Android/backend foundations, contracts and baseline checks

Status: completed
Progress: complete
Type: task
Blocked by: None
Estimate: 10 hours
Target week: 1

## Outcome

Create the minimum maintainable application structure and shared contracts needed by the agreed end-to-end slice.

## Context

- [Agreed specification](../spec.md)
- [Roadmap and gates](../roadmap.md)
- [Decisions and external-source checks](../decisions.md)
- [Ticket index](../README.md#implementation-tickets)

This can begin while ticket 01's account gate is pending. The cloud spike's temporary test endpoint need not wait for this production structure.

## Scope

- Scaffold Flutter Android with Riverpod/GoRouter and Python FastAPI/Pydantic with a small worker entry point. Keep presentation, domain/repository interfaces, API models and platform adapters separate without generating unused feature layers.
- Define versioned report, job, analysis, evidence, validation issue, assignment, review and error contracts from the specification. Keep processing, assignment, review and expiry state separate.
- Publish /api/v1 OpenAPI contracts, including idempotency keys, expected analysis/review versions, paginated lists and stable safe error codes. Patient-visible result selection is server controlled.
- Add environment templates using configuration names only, local development commands, formatting/static analysis, and focused backend/Flutter test commands.
- Initialize source control if still absent, add secret/build-artifact exclusions, and set up CI within available free GitHub allowances. Do not push/publish without the applicable session authorization.

## Acceptance criteria

- [x] Flutter Android builds/runs a shell with login and role-routing placeholders; FastAPI starts with a health endpoint and generated API docs.
- [x] Backend and Dart models consistently represent the agreed schemas, optional printed fields, evidence and version-specific review.
- [x] Azure, Firebase and AI integrations are behind interfaces and configurable environments; no real account is required to exercise basic local contracts.
- [x] Source/config examples contain no credentials, signing material or personal records.
- [x] Documented formatting, analysis and baseline checks pass; CI does not require paid runner capacity.

## Verification

Run Flutter analysis/build smoke checks, backend contract/serialization tests and a health/API-docs smoke check. Use tests for state/contract invariants rather than duplicating boilerplate implementation.

## Implementation record

Completed locally on 2026-10-20. The previous session's socket, package-download, JDK/Python and Git-write gates are resolved.

### Changes

- Flutter Android shell with Riverpod, GoRouter guards, disabled sign-in placeholders, and explicitly labeled debug-only patient/doctor/administrator previews. Release/profile cannot enable previews.
- FastAPI factory, liveness/readiness, Swagger UI/OpenAPI, server request IDs and safe error envelopes. Authentication/workflow routes and the worker deliberately fail closed until their later-ticket adapters exist.
- Versioned Pydantic contracts and generated Dart wire models preserve printed laboratory strings, optional fields, page evidence, validation issues, immutable candidates, review corrections and qualified approved snapshots. Processing, assignment, review and expiry remain separate.
- Review requests require expected analysis, case and prior review versions. Report/case read contracts expose the versions needed after reopening a case; review versions increase monotonically per report across reprocessing.
- Azure document/queue, Firebase identity and AI provider protocols; configuration templates; deny-by-default Firebase rules; no credentials or real records.
- Deterministic OpenAPI/JSON Schema/Dart export and shared synthetic fixtures.
- Python 3.12 dependency lock, typed backend interfaces, Ruff formatting/linting and mypy checks. Development, CI and the Dockerfile use the same locked dependencies.
- GitHub Actions with standard Ubuntu runners, bounded timeouts, backend checks, Flutter analysis/tests and a debug APK build. Added development commands and build/secret exclusions.
- Fixed a phone-width sign-in header overflow and disambiguated the navigation test's page scroll target.

### Verification

- Python 3.12.15 fresh locked environment: all 24 backend tests pass.
- Ruff formatting/linting, mypy (all 8 backend source files) and Python compilation pass.
- All 8 generated contract artifacts are current.
- Flutter 3.35.5/Dart 3.9.2: analysis and formatting pass; all 11 Flutter tests pass; Dart contract/client smoke checks pass.
- Real local Uvicorn process serves liveness, Swagger UI and exactly the generated OpenAPI contract over HTTP; readiness remains intentionally unavailable.
- JDK 17 debug APK build passes. Artifact: `app/build/app/outputs/flutter-apk/app-debug.apk` (ignored build output).
- Android 15/API 35 emulator: APK installs and cold-starts; patient, doctor and administrator previews open with explicit notices and return to sign-in. Screenshots inspected; no Flutter/Android runtime errors in logcat.
- Local Markdown links resolve; source/config credential-pattern scan passes; build outputs, SDKs, environments and keys are excluded from Git.

### Review

Standards review: no actionable findings. Spec review found missing readable review versions and unknown JSON-key reflection in validation errors. Both were fixed, covered at the existing contract/API seams and re-reviewed with no outstanding findings.

### Limits and handoff

Source is committed locally on the existing `main` branch. No push, remote CI run, cloud deployment or release signing was performed. Remote CI awaits an authorized push; Docker execution was not verified locally. These are not claims of cloud/workflow readiness.

Ticket 02 is complete, so tickets 03 and 04 may proceed. Ticket 01's separate cloud-feasibility gates remain open.

## Comments

- 2026-10-20: Created from the user-confirmed project plan. No implementation performed.


- 2026-10-20: Began implementation following user authorization. Code and local checks are recorded above; moved to ready-for-human for the remaining environment/toolchain/source-control gates.

- 2026-10-20: Verified the user's completed Git setup: main tracks origin/main, README commit b7541e3 exists, and origin points to the requested GitHub repository. Remaining project files have not been staged, committed or pushed.


- 2026-10-20: Completed the unrestricted environment checks, corrected review-version read contracts and validation-error redaction, passed both review axes, and committed the foundation locally. No push or deployment.
