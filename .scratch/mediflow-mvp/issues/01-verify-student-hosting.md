# 01: Verify student benefits and deploy a minimal hosted slice

Status: ready-for-human
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

- The account owner activates Azure for Students using legitimate academic verification. GitHub Education access is established, but Azure activation is not. Record credit expiry, spending protection, available region and Container Apps/Jobs quota without recording private identity documents.
- Using the activated account, deploy the smallest HTTPS API plus a private Blob object and a queue-triggered Container Apps Job. Use Consumption resources, bounded concurrency, no paid subscription conversion, no Marketplace add-ons, and no unnecessary dedicated networking.
- Keep Firebase Auth/Firestore on Spark. Verify the current Gemini free API option and account-specific rate limits with a synthetic-only sample; do not install keys in the APK.
- Estimate compute, storage/queue transactions, registry, logs and network usage for twenty daily reports, including idle/reconciliation activity. Document resource caps, credit expiry and service shutdown behavior.
- Inspect selected dependency licenses and Android/cloud build feasibility before locking the processing/PDF packages. Record a verified alternative if quota or student eligibility blocks Azure; preserve ₹0 hosted availability.

## Acceptance criteria

- [x] Account owner has verified Azure student activation and active credit; document only nonsecret references.
- [ ] Verify student spending protection and an allowed region with sufficient quotas.
- [ ] An authenticated HTTPS request from an Android device reaches the hosted test API while the development laptop is off.
- [ ] A private test object denies anonymous access, and one queue message produces a durable completion record from a hosted job.
- [ ] The resource estimate includes costs outside free compute grants; no pay-as-you-go upgrade or separate paid product is needed.
- [ ] Deployment/cleanup commands and feasibility findings are saved. If a gate fails, record its exact cause and leave dependent tickets blocked until an alternative is agreed.

## Verification

Capture sanitized deployment outputs, one successful remote request, one denied public-object request, queue/job evidence, and the account's quota/credit constraints. Delete temporary spike resources after recording reproducible setup.

## Implementation record

In progress; student activation and credit were verified on 2026-10-20 in the signed-in Azure Education overview.

- Available credit: USD100 of USD100.
- Credit expiry: 20 October 2027.
- Displayed October costs: USD0.00.
- Account contact details and subscription identifiers were not copied into project files.
- Azure CLI and Docker are not installed locally. The account owner confirmed browser sign-in.
- No Azure resources, network ingress, role grants, paid upgrades or deployments were created.
- Spending-protection settings, actual regional quotas, a private Blob/queue/job slice, cost estimate and remote Android HTTPS test remain unverified.

Keep cloud-dependent tickets blocked until these checks pass. Activation alone does not complete the feasibility gate.

## Comments

- 2026-10-20: Created from the user-confirmed project plan. No implementation performed.


- 2026-10-20: User authorized project implementation and confirmed Azure student activation/browser sign-in. Portal credit/expiry verified read-only; remaining cloud checks are pending.
