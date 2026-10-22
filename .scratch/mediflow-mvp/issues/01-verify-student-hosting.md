# 01: Verify student benefits and deploy a minimal hosted slice

Status: completed
Progress: complete
Type: task
Blocked by: None
Estimate: 8 hours
Target week: 1

## Outcome

Confirm the selected ₹0 cloud architecture is actually available to this student account before cloud-dependent implementation.

## Context

- [Agreed specification](../spec.md)
- [Roadmap and gates](../roadmap.md)
- [Decisions and external-source checks](../decisions.md)
- [Ticket index](../README.md#implementation-tickets)

Human involvement is limited to academic/account verification and account-owned settings. Agent deployment can follow once the account exists and access is available. Do not request secrets in issue comments.

## Scope

- The account owner activates Azure for Students using legitimate academic verification. GitHub Education access and Azure student activation/credit have been verified; the account-specific protection/capacity checks have passed. Record credit expiry, spending protection, available region and Container Apps/Jobs quota without recording private identity documents.
- Using the activated account, deploy the smallest HTTPS API plus a private Blob object and a queue-triggered Container Apps Job. Use Consumption resources, bounded concurrency, no paid subscription conversion, no Marketplace add-ons, and no unnecessary dedicated networking.
- Keep Firebase Auth/Firestore on Spark. Verify the current Gemini free API option and account-specific rate limits with a synthetic-only sample; do not install keys in the APK.
- Estimate compute, storage/queue transactions, registry, logs and network usage for twenty daily reports, including idle/reconciliation activity. Document resource caps, credit expiry and service shutdown behavior.
- Inspect selected dependency licenses and Android/cloud build feasibility before locking the processing/PDF packages. Record a verified alternative if quota or student eligibility blocks Azure; preserve ₹0 hosted availability.

## Acceptance criteria

- [x] Account owner has verified Azure student activation and active credit; document only nonsecret references.
- [x] Verify student spending protection and an allowed region with sufficient quotas.
- [x] An authenticated HTTPS request from an Android device reaches the hosted test API while the development laptop is off.
- [x] A private test object denies anonymous access, and one queue message produces a durable completion record from a hosted job.
- [x] The resource estimate includes costs outside free compute grants; no pay-as-you-go upgrade or separate paid product is needed.
- [x] Deployment/cleanup commands and feasibility findings are saved. If a gate fails, record its exact cause and leave dependent tickets blocked until an alternative is agreed.

## Verification

Capture sanitized deployment outputs, one successful remote request, one denied public-object request, queue/job evidence, and the account's quota/credit constraints. Delete temporary spike resources after recording reproducible setup.

## Implementation record

Completed on 2026-10-21. On 2026-10-20, the signed-in Education overview showed USD100 of USD100, expiry 20 October 2027 and October costs USD0.00. These are dated observations, not a current invoice. The owner completed Azure CLI sign-in on 2026-10-21; ARM independently confirms Enabled / Azure for Students / spending protection **On**. The wizard's earlier `off` entry was incorrect. No billing conversion or change to spending protection was needed.

- Jio India Central was not listed for Container Apps/Jobs. Central India was listed and the selected subscription allowed one standard environment. The deployed standard environment reported a **100 Consumption-core** quota.
- Deployed one temporary tagged group containing a standard Container Apps environment with only its Consumption profile, HTTPS API, event-driven Job, Hot LRS private storage and user-assigned managed identity. Storage-scoped Blob/Queue data roles were granted only to that probe identity. No private registry, Log Analytics workspace, dedicated compute, Marketplace purchase or paid upgrade was created.
- The old CLI's consumption-only flag unexpectedly created an Express environment. Azure rejected Jobs with `ExpressEnvironmentResourceNotSupported`. Explicit ARM `environmentMode=WorkloadProfiles` fixed this; the unused Express environment was deleted and its absence verified. Reproduction uses API 2026-07-01 and only Consumption.
- Hosted HTTPS: valid test credential HTTP 200, missing/wrong credentials HTTP 401. After an authenticated write of the actual synthetic object, anonymous Blob GET returned HTTP 409 / `PublicAccessNotPermitted` with the default service version and HTTP 401 / `NoAuthenticationInformation` with an explicit current service version.
- One queue message automatically triggered the hosted job (no manual start). Azure execution status **Succeeded**; completion receipt hash matched the fixed synthetic object and a subsequent API read returned the same durable receipt. A repeated `/run` returned completed without another message.
- API and worker each use 0.25 vCPU / 0.5 GiB; min zero, maximum one API replica and one event execution. Worker timeout 180 seconds, platform retries zero, queue message TTL ten minutes. Test credential expires after 24 hours. The application foundation's auth/workflows remain unchanged.
- Gemini `gemini-3.5-flash-lite` returned HTTP 200 and exactly preserved the four invented fixture fields, including `<0.50` and a null missing range; 63 prompt / 41 output tokens. This establishes one successful bounded call, not unlimited quota or general extraction quality. Owner-authorized Cloud Billing and Service Usage reads now verify no linked billing account and model-specific Free limits: 15 RPM, 250,000 input TPM and 500 RPD. These are dated effective limits, not an unlimited allowance.
- Regional cost scenarios, credit/shutdown behavior and selected dependency/build feasibility are recorded in [hosting costs](../hosting-costs.md). Production OCR allocation, retention bounds and retry/recovery work still require measurement/enforcement in their own tickets.
- Nine local probe/guard tests and Ruff checks pass. Deployment/verification/cleanup source is in [tools/hosting_spike](../../../tools/hosting_spike/README.md); [sanitized evidence](../hosting-evidence.json) records the checks. Private account/project IDs, credentials and cloud responses remain ignored under `.tooling/issue-1/`.

Owner Google sign-in is complete. Enabled Firebase on the existing Gemini project only after verifying that no Cloud Billing account was linked, and repeated that verification afterward: Firebase ACTIVE, billing disabled, no linked billing account (Spark). Actual Auth provider/account seeding and Firestore database/rules deployment remain ticket 04; this account-feasibility check does not implement them. Verified project/model/limits are in ignored `.tooling/issue-1/verified-settings.env`; the original wizard capture is preserved.

The owner reported the instructed physical Android/laptop-off test succeeded: server time `2026-10-20T19:34:35.415060+00:00`, receipt `bead827307388142`. This is explicitly owner-reported device evidence; the earlier automated test is separate.

Temporary Azure cleanup is complete: `group exists` returned false after deletion. The API, worker, environment, storage and managed identity are gone, and there was no separate infrastructure group. Obsolete local test credentials and phone handoff artifacts were retired. The no-billing Firebase project is retained for ticket 04. All acceptance criteria have passed; implementation of dependent features remains in their own tickets.

## Comments

- 2026-10-20: Created from the user-confirmed project plan. No implementation performed.


- 2026-10-20: User authorized project implementation and confirmed Azure student activation/browser sign-in. Portal credit/expiry verified read-only; remaining cloud checks are pending.


- 2026-10-21: Owner completed the wizard. Captured spending protection is off (not independently verified), regional quotas are unknown and Firebase is not yet created. Installed isolated Azure CLI 2.91.0 and prepared the owner sign-in helper. Gemini model discovery authenticated successfully, but the captured model entry was a project ID and bounded generation probes did not establish extraction success. No cloud resources, billing changes or paid fallback. See [preflight findings and estimate inputs](../hosting-preflight.md). Owner Azure CLI sign-in is the next access step.

- 2026-10-21: Owner completed Azure CLI sign-in. Independently verified spending protection On, deployed the Central India hosted synthetic slice, confirmed authenticated HTTPS/private Blob denial/automatic queue-job completion, and obtained a successful Gemini 3.5 Flash-Lite structured fixture. See the implementation record, cost scenarios and sanitized evidence above. Firebase login, numeric Gemini quota verification, the physical laptop-off Android request and subsequent resource cleanup remain open; no paid conversion or model fallback was used.

- 2026-10-21: Owner completed Google sign-in and reported the instructed Android/laptop-off HTTPS success. Enabled and verified Firebase Spark without linking billing; independently read Gemini model-specific Free limits (15 RPM / 250,000 input TPM / 500 RPD). Deleted the temporary Azure group and verified it absent. All ticket-01 acceptance criteria are complete; retained only the no-billing Firebase project for subsequent authentication work.
