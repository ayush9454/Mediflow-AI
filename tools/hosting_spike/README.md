# Issue 01: disposable hosted probe

This isolates infrastructure feasibility from the real application. It accepts only one fixed synthetic fixture. The existing FastAPI/Flutter workflows retain their fail-closed behavior; this probe does not implement Firebase roles, report extraction or clinical review.

The API exposes public `/health` and a temporary phone-test page. `/probe`, `/run` and `/result` require a random bearer test credential. It expires after 24 hours. The API writes a private fixture and enqueues work; an event-driven Container Apps Job reads it with managed identity, writes an immutable completion receipt, then acknowledges the queue message. Duplicate delivery preserves the first receipt.

## Prerequisites

- Owner Azure sign-in through the prepared private `.tooling/issue-1/az` wrapper; authentication state must stay ignored. The wrapper uses the isolated Azure CLI and `AZURE_CONFIG_DIR=.tooling/issue-1/azure`.
- A private `.tooling/issue-1/.env` containing `AZURE_SUBSCRIPTION_ID` for the selected account. Shell-style single-quoted values are parsed as data, never executed. No Gemini/Firebase secret is required by this deployment.
- Student subscription Enabled with ARM spending protection On; this is rechecked before creation/update.
- Central India must support the resources and have capacity. The measured standard environment reported 100 Consumption cores; rerun quotas for future deployments.
- Python 3.12; `httpx` is needed only by the local verifier, already in `backend/.venv`. Deployed code uses only the standard library.

Private state lives under `.tooling/issue-1/` (directory 0700, sensitive files 0600). Never print or commit `.env`, OAuth state, request bodies, test credentials, raw ARM responses or the phone handoff. The ARM request for the API includes its test secret.

## Reproduce or resume

From the repository root:

```bash
backend/.venv/bin/python -m unittest discover -s tools/hosting_spike -p 'test_*.py'
backend/.venv/bin/python tools/hosting_spike/cloud.py init
backend/.venv/bin/python tools/hosting_spike/cloud.py infrastructure
backend/.venv/bin/python tools/hosting_spike/cloud.py deploy
backend/.venv/bin/python tools/hosting_spike/verify.py
```

`init` creates one randomly named, tagged group and saves its private state. It refuses to overwrite existing state; resume that deployment instead. `environment` resumes a pending environment creation after `init`. `infrastructure` and `deploy` operate on the same state; do not resubmit updates while ARM provisioning is still in progress. Inspect private provisioning status first. A failed mutation is not an automatic cleanup or a successful acceptance check.

The environment explicitly sets ARM API `2026-07-01` `environmentMode=WorkloadProfiles` with **only** the Consumption profile, and no log export destination. The older CLI's `--enable-workload-profiles false` unexpectedly produced Express on this account, and Azure rejected Jobs with `ExpressEnvironmentResourceNotSupported`. Do not repeat that configuration. [Microsoft documents environment modes](https://learn.microsoft.com/en-us/rest/api/resource-manager/containerapps/managed-environments/create-or-update?view=rest-resource-manager-containerapps-2026-07-01) and [Express feature limits](https://learn.microsoft.com/en-us/azure/container-apps/express-overview).

Storage is Hot LRS with anonymous Blob access and shared-key authorization disabled, HTTPS required and TLS 1.2 minimum. The user-assigned managed identity receives Blob/Queue Data Contributor only at this disposable storage account's scope. The scaler uses that identity; no storage connection string is installed. See [managed identity token access](https://learn.microsoft.com/en-us/azure/container-apps/managed-identity) and the [queue scaler](https://keda.sh/docs/2.18/scalers/azure-storage-queue/).

The official public Python 3.12 slim image is resolved to an immutable digest and saved in private state. The checked-in runtime is injected as nonsecret base64 code; no code/image upload to a public registry and no private ACR are needed. This is a small probe delivery technique, not the production container pipeline. It has no runtime package installation. API and worker each use 0.25 vCPU / 0.5 GiB, max one replica/execution; min zero. The worker has no platform retries, a 180-second timeout and a ten-minute message TTL.

## Evidence and physical Android check

`verify.py` prints and saves sanitized status codes, completion hash agreement, durable receipt stability and execution statuses to `.tooling/issue-1/hosting-evidence.json`. It never emits cloud IDs, the endpoint or credentials. It checks that anonymous access fails **after** an authenticated write of the actual object. Completion is polled through the hosted API; the verifier does not manually start the worker. An unversioned anonymous Blob read returns 409 / `PublicAccessNotPermitted`; an explicit modern service version returns a 401 bearer challenge / `NoAuthenticationInformation`, as [Microsoft documents](https://learn.microsoft.com/en-us/azure/storage/blobs/anonymous-read-access-prevent).

The physical Android test is separate from these automated checks. Open the private phone handoff, scan its QR on the Android device, load the page and let it fill the test credential. Then power off the development laptop and tap **Verify hosted API** on the phone. Record the server timestamp and receipt after success; never include the credential in issue comments. An emulator running on an awake laptop does not satisfy this acceptance criterion.

## Cleanup

After recording the physical test:

```bash
backend/.venv/bin/python tools/hosting_spike/cloud.py cleanup
backend/.venv/bin/python tools/hosting_spike/cloud.py cleanup-status
```

Cleanup validates the group's ownership tags, then requests deletion of the whole temporary group, including the environment, API, job, storage and managed identity/role assignments. It does not change subscription billing or unregister shared service providers. `cleanup-status` saves a private absence check and exits 2 while the group still exists; retry it after deletion has had time to finish. Confirm absence before recording completion. Credential expiry does **not** delete resources. Preserve a sanitized evidence record and remove obsolete private test credentials/phone artifacts after cleanup. To reproduce later, archive the previous private `cloud-state.json` after verified cleanup before running `init`; never overwrite state for live resources.

## Google account checks

The account owner signs in using the isolated Firebase CLI. For the selected existing Google project, read `GET https://cloudbilling.googleapis.com/v1/projects/PROJECT_ID/billingInfo` and require `billingEnabled=false` with no linked billing account. Then use Firebase CLI `projects:addfirebase PROJECT_ID` (or the [Firebase add API](https://firebase.google.com/docs/reference/firebase-management/rest/v1beta1/projects/addFirebase)) and poll its operation. Verify the Firebase project is ACTIVE and repeat the billing read afterward. This establishes Spark access without configuring a database, provider, seeded user or paid capacity.

Read the [Service Usage API](https://cloud.google.com/service-usage/docs/reference/rest/v1beta1/services.consumerQuotaMetrics/list) at `projects/PROJECT_NUMBER/services/generativelanguage.googleapis.com/consumerQuotaMetrics?view=FULL`, following pagination. Select the chosen model's **free-tier effective buckets**, rather than paid-tier or default rows. On this account, Gemini 3.5 Flash-Lite returned 15 RPM, 250,000 input TPM and 500 RPD. Recheck before future deployment. Private owner-authorized responses and verified settings stay under `.tooling/issue-1/`; keys and OAuth tokens are not logged or committed.

Cost assumptions, credit expiry and dependency review: [hosting-costs.md](../../.scratch/mediflow-mvp/hosting-costs.md). Current feasibility gates: [hosting-preflight.md](../../.scratch/mediflow-mvp/hosting-preflight.md).
