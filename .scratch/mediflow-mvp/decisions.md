# Decisions and verified source notes

Agreed by the user on 2026-10-20 after the grilling interview. This records the resulting scope rather than preserving every intermediate proposal.

## Settled decisions

| Questions | Decision |
| --- | --- |
| Q1 | Synthetic-data college demonstration; real hospital use is a separate future milestone. |
| Q2 | One developer, eight weeks, 15–20 hours/week. |
| Q3 | Flutter/Riverpod, Firebase Auth/Firestore, Python/FastAPI retained. Hosting and storage adapted for ₹0. |
| Q4 | Laboratory end-to-end workflow mandatory; radiology stretch; broad ERP features deferred. |
| Q5/Q10 | Android replaces the earlier web-first proposal. Signed APK shared free with classmates/examiners; target up to 20 authorized devices. |
| Q6 | One hospital, pre-created patient/doctor/administrator accounts; no public signup or multi-hospital onboarding. |
| Q7 | English digital/scanned PDFs, maximum 10 pages and 10 MB. |
| Q8/Q21 | Synthetic benchmark: 20 development, 10 held-out valid, 10 negative cases; measured fidelity/access/workflow evidence. |
| Q9 | ₹0 out of pocket. The earlier proposed monthly budget was rejected. |
| Q11 | Hosted backend must work while laptop is off. The local-only proposal was rejected. |
| Q12 | Each uploaded report creates one case, manually assigned by an administrator. |
| Q13/Q18 | Approve, correct and approve, or reject; preserve original candidates and review history; require explicit handling of flagged/unresolved information. |
| Q14 | Azure for Students is the primary hosting route, subject to activation/quota checks and spending protection. User has GitHub Education access. |
| Q15 | Cold-start delay acceptable with a clear loading state. |
| Q16 | Gemini free API for synthetic reports, provider abstraction, explicit unavailable state on quota exhaustion, no fabricated fallback. |
| Q17 | Patient-owned access; currently assigned doctor access; administrator metadata/assignment without automatic clinical access. |
| Q19 | At most two automatic retries after the initial transient-failure attempt; bounded manual retry; versioned reprocessing and fresh approval. |
| Q20 | Five uploads/patient/day, twenty/hospital/day, thirty-day retention of PDFs and analyses, configurable. |
| Q22 | Preserve printed laboratory fields and source evidence; no diagnoses, treatment advice, inferred ranges or unit conversion. |
| Q23 | Supporting quotation plus navigation to the source PDF page; tabs/split view; bounding-box highlighting deferred. |
| Q24 | In-app state refresh; separate processing/review states; push notifications deferred. |
| Q25 | APK, source, deployment instructions, architecture/API docs, measured evaluation, limitations and recorded demo. Routine implementation details may be chosen within agreed cost/scope/behavior. |
| Final confirmation | User explicitly confirmed shared understanding before this plan was written. |

Routine details made concrete in the specification include UTC quota boundaries, backend-only record access, authenticated bounded upload/download, immutable candidate/review records, atomic review-version checks, a strict row metric that penalizes omissions and extras, and short-lived operational audit retention. They implement the agreed behavior without adding product features.

## Hosting and distribution facts checked during planning

These are external-service facts, not promises that the user's accounts are activated. Recheck them at ticket 01 and before release; provider plans and regional capacity can change.

### Azure for Students

- India offer: USD100 credit usable within 12 months, no credit card; annual renewal while eligible.
- Eligibility includes age 18+, full-time enrollment at an accredited degree-granting institution and academic verification. GitHub Education does not by itself prove successful Azure activation.
- Credit exhaustion/expiry disables services unless the owner explicitly upgrades. Retain student spending protection; avoid Marketplace services with separate billing.
- Container Apps Consumption has free compute/request grants and supports scaling to zero. Jobs use resources only while executing, but storage, registry, logs, queue transactions and network use can still consume credit.
- Container Apps quotas depend on subscription and region. Do not assume a student subscription can obtain a paid quota increase.

Sources: [India student offer](https://azure.microsoft.com/en-in/free/students/), [eligibility](https://learn.microsoft.com/en-us/azure/education-hub/about-azure-for-students), [disabled subscription](https://learn.microsoft.com/en-us/azure/cost-management-billing/manage/azurestudents-subscription-disabled), [spending limits](https://learn.microsoft.com/en-us/azure/cost-management-billing/manage/spending-limit), [Container Apps pricing](https://azure.microsoft.com/en-us/pricing/details/container-apps/), [quotas](https://learn.microsoft.com/en-us/azure/container-apps/quotas), [queue-driven jobs](https://learn.microsoft.com/en-us/azure/container-apps/tutorial-event-driven-jobs).

### Firebase

- Live Cloud Storage for Firebase requires Blaze with a linked billing account; replace it with private Azure Blob Storage.
- Firebase Auth nonphone methods and Firestore Spark can fit a small invited demo, within current quotas.
- Firestore paid TTL/backups are outside this plan; implement bounded expiry/cleanup through the hosted backend.
- Local emulators are useful for development but do not satisfy hosted availability.

Sources: [Storage billing changes](https://firebase.google.com/docs/storage/faqs-storage-changes-announced-sept-2024), [Firebase plans](https://firebase.google.com/docs/projects/billing/firebase-pricing-plans), [Firestore quotas/pricing](https://firebase.google.com/docs/firestore/pricing), [Auth limits](https://firebase.google.com/docs/auth/limits).

### Gemini

Free API options exist, with changing model-specific quotas. Free-service data may be used for product improvement and reviewed by humans; do not submit sensitive/personal/confidential records. Developer terms restrict clinical-practice/medical-advice use. This project remains synthetic extraction and simulated review. Model availability/structured output and actual free quota must be benchmarked on the activated account; do not assume unlimited inference.

Sources: [pricing](https://ai.google.dev/gemini-api/docs/pricing), [rate limits](https://ai.google.dev/gemini-api/docs/rate-limits), [terms](https://ai.google.dev/gemini-api/terms), [regions](https://ai.google.dev/gemini-api/docs/available-regions).

### Android distribution

A new Google Play developer account costs USD25 once, outside this project's ₹0 requirement. Signed APK distribution is supported outside Google Play. Android's free limited-distribution account supports up to twenty authorized devices; account/verification/install requirements must be checked for the release region and date. A free payments profile may be part of account setup; do not promise the absence of all account-verification steps.

Sources: [Play account setup](https://support.google.com/googleplay/android-developer/answer/6112435), [Android publishing](https://developer.android.com/studio/publish), [limited distribution](https://developer.android.com/developer-verification/guides/limited-distribution).

## Remaining implementation facts to establish

- Azure student activation was verified during implementation (USD100 credit, expiry 20 October 2027); confirm spending protection, a usable region and quotas. See ticket 01.
- Measure a minimal cloud slice and bound storage/log/registry/network costs.
- Verify the current free AI model, structured-output support, quota and representative extraction quality.
- Benchmark OCR quality, memory and execution time for the accepted 10-page/10-MB limit.
- Verify Android build tools, minimum supported device/API, PDF-viewer authenticated loading, and release-signing setup.
- Record actual dataset metrics, latency and consumed resources.

These are implementation investigations with explicit tickets, not unresolved product decisions. No dependency licenses, model quality, uptime, free-tier capacity or clinical accuracy is assumed to have been validated by the planning conversation.
