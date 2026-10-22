# Tickets 04 and 07: integration and review

Date: 2026-10-23

## Integration

- Baseline: `0c6ba59`.
- Ticket 04: separate worktree `/private/tmp/mediflow-ticket-04`, branch `implement/ticket-04`, implementation `74c5d4d`, integrated by `0e7912d`.
- Ticket 07: separate worktree `/private/tmp/mediflow-ticket-07`, branch `implement/ticket-07`, implementation `a731f89`, integrated by `2ca6417`.
- Shared dependency/CI/documentation coordination, cloud smoke tooling and verification records were integrated on `main`, through `575ff5f`.

## Verification

- Combined Linux backend suite: **74 passed, 1 skipped**. Real Tesseract ran; the skipped test requires paired Firebase emulators.
- Separate real Firebase Auth/Firestore emulator test: **1 passed**, including five seeded identities, 60 direct-access denials and reassignment revocation.
- Flutter: **19 passed**, analysis clean. Debug APK built, installed and launched in the Android API 35 emulator.
- Backend mypy: **25 sources passed**. Ruff lint/format, eight generated contract artifacts and two cloud mutation guard tests passed.
- Live Firebase Spark: email/password and Standard Firestore configured, deny-all client rules deployed, five synthetic identities seeded. Production app settings passed live token/policy checks through a local test client; all five identities also passed role checks through the separately running local HTTP API. No hosted production API was deployed.
- Bounded OCR worker: all **35** development, negative and supplemental observations matched expectations at **0.5 vCPU / 1 GiB**. Ten scanned pages took **10.71 s**; aggregate memory peak was **172,625,920 bytes**. This measures page processing, not row or clinical accuracy. Held-out data was not used for tuning.
- New CI gates cover real OCR, the resource-bounded container benchmark and Firebase emulator/rules checks. Remote CI has not been run in this session.

## Standards

Parallel review of the integrated implementation (`0c6ba59...2ca6417`), followed by the final shared changes (`2ca6417...575ff5f`): **0 actionable findings**. Final review found no documented-standard breaches or substantial baseline smells. CI and the Azure runtime share the report gate; cloud operations guard subscription/ownership and keep private responses in ignored state.

## Spec

The same two review ranges produced **0 actionable code findings**. Final review confirmed that documentation distinguishes local verification from deployment.

One acceptance requirement remains incomplete: ticket 07, “The OCR container can run in the available Azure job resources established by ticket 01.” The Azure subscription guard returned `AADSTS530035` before mutation. **No temporary Azure resources were created.**

## Current status and resumption

- Ticket **04 completed**; tickets **05 and 06 are unblocked**.
- Ticket **07 in progress**: implementation and local verification complete; actual Azure execution remains unchecked.
- Owner action: run `.tooling/issue-1/login-azure.sh` from the repository root and complete sign-in. Keep codes and tokens out of chat.
- After authentication, resume the staged commands in [the cloud smoke guide](../../tools/processing_smoke/README.md), collect successful bounded-job evidence, delete the temporary group and verify its absence before completing 07. The isolated implementation worktrees are retained for this follow-up.

Summary: Standards **0 findings**; Spec **0 actionable code findings**, with **1 explicitly pending operational acceptance criterion**.
