# Issue 01 hosting preflight

Updated: 2026-10-21 (Asia/Kolkata). Status: **complete; all checks passed and temporary Azure resources deleted**.

## Account-owner handoff

The owner completed the wizard and Azure CLI sign-in. Earlier activation evidence showed USD100 credit expiring 20 October 2027. ARM now independently confirms an Enabled Azure for Students subscription with spending protection **On**. The wizard's `off` observation was incorrect; no billing change was made.

Jio India Central was not listed for Container Apps/Jobs. Central India was supported: the selected subscription allowed one standard environment, and the deployed standard environment reports **100 Consumption cores**. Firebase is now ACTIVE on the existing Gemini project, with Cloud Billing disabled and no linked billing account (Spark). Owner-authorized Service Usage reads verify model-specific Gemini 3.5 Flash-Lite Free limits: 15 requests/minute, 250,000 input tokens/minute and 500 requests/day. The original unlimited entries were wrong. One bounded structured fixture succeeded.

Subscription/project identifiers, API keys and authentication state remain only in ignored workspace files; none are reproduced here.

## Work completed after the wizard

- Installed Azure CLI 2.91.0 in an isolated ignored Python environment; the application/backend environment was not changed.
- Prepared and completed Microsoft's device-code login flow; the isolated session stays under ignored `.tooling/issue-1/azure/`.
- Verified subscription policy, supported region and actual quotas. Created one tagged temporary group with exactly five top-level resources: a standard environment containing only Consumption, HTTPS app, queue-triggered Job, private LRS storage account and user-assigned managed identity. Storage-scoped roles are limited to that account. No paid conversion, registry, Log Analytics workspace or dedicated network was created.
- Corrected a real platform mismatch: the older CLI consumption-only flag created Express; Jobs failed with `ExpressEnvironmentResourceNotSupported`. Explicit ARM `environmentMode=WorkloadProfiles` supports Jobs. The unused Express environment was deleted and verified absent. The saved reproduction uses current API 2026-07-01.
- Hosted API health/authenticated request returned 200; missing/wrong test credentials returned 401. The written private Blob denied anonymous access (default version 409 / `PublicAccessNotPermitted`; explicit current version 401 / `NoAuthenticationInformation`). One queue message automatically produced a Succeeded hosted execution and a durable, hash-matching completion receipt; a subsequent read was stable. No manual job start was used.
- Added [reproducible source and cleanup commands](../../tools/hosting_spike/README.md), nine passing local authentication/idempotency/guard tests and [sanitized deployment evidence](hosting-evidence.json). The final runtime AST matches the deployed runtime after repository formatting. The owner completed the phone test; temporary Azure deletion is complete and group absence was verified.
- Gemini's model-catalogue endpoint returned HTTP 200 using the locally captured key. The captured model entry was a project identifier and was not a valid catalogue model ID.
- Tested only invented synthetic input, with finite output caps and request deadlines. No real records or raw model/error payloads were logged. No billing settings were changed and no paid-model fallback was used.
- Installed an isolated Firebase CLI and prepared `bash .tooling/issue-1/login-firebase.sh`. Owner Google sign-in is complete. Added Firebase only after checking billing disabled with no linked billing account, then repeated those checks after enablement. Firebase is ACTIVE (Spark); no Firestore database, Auth provider or seeded accounts were created by this feasibility task. Credentials remain in ignored private configuration.

## Gemini probes

| Candidate | Bound | Observed result | What it establishes |
| --- | --- | --- | --- |
| `gemini-2.5-flash-lite` | One request, 256 output tokens | HTTP 404 / NOT_FOUND | Listed metadata did not establish that this model could serve generation on this account |
| `gemini-3.8-flash` | One request, 256 output tokens | HTTP 200; exact structured fixture did not match; no candidate-output token count reported | Service/key reachable; extraction correctness not established |
| `gemini-3.8-flash` | One request, 1024 output tokens, minimal thinking | HTTP 400 / INVALID_ARGUMENT | Probe used an unsupported thinking setting |
| `gemini-3.8-flash` | One corrected request, 1024 output tokens, low thinking, 40-second deadline | ReadTimeout | Completion and fixture preservation not established; no further automatic attempts made |
| `gemini-3.5-flash-lite` | One request, 1024 output tokens, supported minimal thinking, 40-second deadline | HTTP 200 / STOP; four synthetic fields exactly matched; 63 prompt and 41 output tokens | One successful bounded structured extraction; missing range remained null and printed comparator was preserved |

One bounded synthetic inference is verified for `gemini-3.5-flash-lite`. Numeric account quotas were independently read after owner sign-in; see the verified limits below. One successful call does not establish workload latency or general extraction quality. The original project-ID model entry and unlimited observations are excluded from verified settings.

Google documents Free input/output for Gemini 3.5 Flash-Lite in the [pricing table](https://ai.google.dev/gemini-api/docs/pricing). [Structured output](https://ai.google.dev/gemini-api/docs/structured-output) and [thinking controls](https://ai.google.dev/gemini-api/docs/thinking) need model-specific configuration. The owner-authorized [Service Usage quota API](https://cloud.google.com/service-usage/docs/reference/rest/v1beta1/services.consumerQuotaMetrics/list) reports the selected model's effective free-tier buckets: 15 RPM, 250,000 input TPM and 500 RPD. Unrelated default and paid-tier buckets are not the selected Free limits. [Cloud Billing project status](https://cloud.google.com/billing/docs/reference/rest/v1/projects/getBillingInfo) independently confirms billing disabled and no linked account. Recheck [current limits](https://ai.google.dev/gemini-api/docs/rate-limits) before future deployment; no paid fallback is selected.

## Resource estimate

The [regional cost and dependency review](hosting-costs.md) includes compute, API start/scale-down overhead, retries/manual reprocessing, reconciliation/cleanup, 12 GB retained storage, Blob/Queue transactions including idle scaler polls, registry/build, logs and egress. At twenty reports/day, modeled totals with a private production registry/build path are approximately USD6.13–12.41/month of student credit when shared free allowances are available. No private registry/build was created for this much smaller spike.

Those are scenario estimates rather than invoices or implemented production caps. OCR runtime/memory and retry/retention policies must be benchmarked/enforced in their own tickets. The review records licenses for the selected foundation packages and feasible pypdf/pypdfium2/Tesseract candidates without locking PDF/OCR packages. The issue-02 Android build/emulator evidence remains valid independently.

## Final verification and cleanup

The account owner reported the instructed Android/laptop-off HTTPS test succeeded: server time `2026-10-20T19:34:35.415060+00:00`, receipt `bead827307388142`. This is owner-reported physical-device evidence; the automated cloud checks are recorded separately.

Azure teardown completed using `backend/.venv/bin/python tools/hosting_spike/cloud.py cleanup`, followed by `cleanup-status`. The resource group is absent; there was no separate environment infrastructure group. API, worker, environment, storage and identity are gone. Obsolete private test credentials and phone artifacts were retired. Firebase's no-billing project is retained for ticket 04. Verified project/model/limits stay privately in `.tooling/issue-1/verified-settings.env`; original owner capture is preserved.

Ticket 01 is complete. This establishes account and infrastructure feasibility; whole-application release and clinical-processing readiness remain dependent feature work.
