# Issue 01 hosting estimate and dependency feasibility

Checked 2026-10-21, Central India, USD retail, 30-day month. This estimates student-credit consumption, not a promise of permanently free hosting. Account IDs and credentials are excluded.

## Rates and scope

The [Azure Retail Prices API](https://learn.microsoft.com/en-us/rest/api/cost-management/retail-prices/azure-retail-prices) was queried with `armRegionName eq 'centralindia'`, `priceType eq 'Consumption'`, and the relevant service/product. Private raw snapshots are under ignored `.tooling/issue-1/prices-*.json`. Relevant returned meters:

| Meter | Rate |
| --- | --- |
| Container Apps Standard active CPU | $0.000024 / vCPU-second |
| Container Apps Standard active memory | $0.000003 / GiB-second |
| Container Apps Standard idle CPU and memory | $0.000003 / vCPU-second and / GiB-second respectively |
| App requests | $0.40 / million above grant |
| General Block Blob v2, Hot LRS storage | $0.020 / GB-month |
| Hot LRS writes; list/create-container operations | $0.055 / 10,000 |
| Hot reads; other Blob operations | $0.0044 / 10,000 |
| Queues v2 LRS storage | $0.045 / GB-month |
| Queues v2 class 1, class 2, additional IO | $0.004 / 10,000 operations |
| Basic private registry | $0.1666 / day, about $5.00 / 30 days |
| Registry storage beyond included allowance | $0.10 / GB-month |
| Registry task CPU, after first 6,000 vCPU-seconds | $0.0001 / vCPU-second |
| Internet egress, Microsoft global network route | First 100 GB/month free; next tier $0.12 / GB |
| Inter-region transfer meter | $0.08 / GB; avoid cross-region placement |

The selected environment has only a Consumption workload profile. No dedicated profile, premium ingress, private endpoint, NAT gateway, paid Marketplace service, or paid conversion is required by the spike. The spike uses an official public Python image resolved to its digest, and therefore creates **no private registry or remote build**. A production registry is nevertheless included below; its availability/build must still be exercised in production deployment work.

The subscription-level grants are 180,000 vCPU-seconds, 360,000 GiB-seconds and two million app requests per month. These can be shared with other apps. Jobs incur active execution charges, with no idle execution charge. See [Container Apps pricing](https://azure.microsoft.com/en-us/pricing/details/container-apps/), [registry pricing](https://azure.microsoft.com/en-us/pricing/details/container-registry/) and [bandwidth pricing](https://azure.microsoft.com/en-us/pricing/details/bandwidth/).

## Twenty reports/day scenario

These are explicit modeling assumptions to benchmark in tickets 06/07/13, not implemented production limits:

- 600 new reports/month. Each original is at most 10,000,000 bytes. Thirty-day originals can occupy 6 GB decimal; budget another 6 GB for analyses, versions, staging and abandoned objects, requiring enforced cleanup and a total storage bound.
- Each processing attempt gets 0.5 vCPU / 1 GiB for at most 300 seconds. A ten-page OCR benchmark is still required; a larger allocation or deadline changes this estimate.
- Each upload/API interaction gets 60 active seconds plus 300 seconds of cold-start/scale-down overhead, conservatively all at the active rate: 600 × 360 seconds at 0.25 vCPU / 0.5 GiB = 54,000 vCPU-seconds and 108,000 GiB-seconds.
- Reconciliation every five minutes: 8,640 executions × five seconds at 0.25 vCPU / 0.5 GiB = 10,800 vCPU-seconds and 21,600 GiB-seconds. Daily cleanup: 30 × 60 seconds adds 450 vCPU-seconds and 900 GiB-seconds. These include recovery work; queue scaler polling is priced separately below.
- Min replicas/executions zero. Max API replica one and worker concurrency one; recovery must share a controlled scheduling budget. At most 100,000 HTTP requests/month, including bounded foreground result polling. No always-on app polling.
- The last scenario models 20% of reports receiving one manual reprocessing cycle of up to three attempts, beyond the initial three-attempt ceiling. This is a sensitivity case, not permission for unlimited manual retries; ticket 06 must enforce a finite manual allowance.

| Scenario | Worker attempts | Total vCPU-seconds | Total GiB-seconds | Compute after unused grants |
| --- | ---: | ---: | ---: | ---: |
| One successful attempt/report | 600 | 155,250 | 310,500 | $0.00 |
| Every report uses all three automatic attempts | 1,800 | 335,250 | 670,500 | $4.66 |
| Above, plus the bounded manual-reprocessing scenario | 2,160 | 389,250 | 778,500 | $6.28 |

Beyond compute, budget:

| Category | Assumption | Monthly estimate |
| --- | --- | ---: |
| Blob capacity | 12 GB Hot LRS | $0.24 |
| Blob transactions | 30,000 writes/list/create, 100,000 reads, 30,000 other | $0.223 rounded up |
| Queue capacity and operations | ≤0.01 GB, ≤150,000 metered IO units; includes 86,400 scaler polls, reconciliation and receive/delete/retry work | $0.061 rounded up |
| Registry | One Basic registry; image versions pruned within included 10 GB | $5.00 rounded up |
| Remote builds | 12,000 vCPU-seconds/month; first 6,000 included | $0.60 |
| Logs | No paid ingestion/export destination or Log Analytics workspace; bounded application diagnostics retained only when configured/priced separately | $0.00 |
| Internet egress | 30 GB for repeated downloads/provider traffic; free allowance unused elsewhere | $0.00; $3.60 if allowance unavailable |
| Same-region traffic | Co-locate API, worker and storage; no intentional cross-region transfer | $0.00 cross-region budget |
| Firebase/Gemini | Spark/Free only; verified model quotas apply; reject/back off when exhausted | $0 paid capacity |

With the modeled registry/build path and free allowances available, totals are approximately **$6.13 / $10.79 / $12.41 per month** for the three scenarios. If the internet allowance is already consumed, add $3.60. If compute grants are also consumed elsewhere, the manual-reprocessing scenario's gross compute is $11.68, making its total about $21.41 with charged egress. Taxes, currency conversion and actual billing adjustments are not modeled; the account's student balance is the actual limit. These totals are estimates, not measured invoices. The disposable spike has much less storage/work and no registry/build standing charge.

## Verified Google account capacity

After owner Google sign-in, Cloud Billing reports billing disabled with no linked billing account. Firebase was enabled on the same existing Gemini project and verified ACTIVE with that billing state unchanged, establishing Spark access. Auth account/provider seeding and Firestore deployment remain ticket 04.

The owner-authorized [Service Usage quota API](https://cloud.google.com/service-usage/docs/reference/rest/v1beta1/services.consumerQuotaMetrics/list), with `view=FULL`, reports model-specific effective Free limits for `gemini-3.5-flash-lite`: **15 requests/minute, 250,000 input tokens/minute and 500 requests/day**. The model-specific buckets take precedence over unrelated/default/paid-tier rows; the wizard's unlimited values are discarded. [Cloud Billing project status](https://cloud.google.com/billing/docs/reference/rest/v1/projects/getBillingInfo) was read before and after Firebase enablement. Firebase without a linked billing account uses [Spark](https://firebase.google.com/docs/projects/billing/firebase-pricing-plans).

At one bounded inference call/attempt, twenty reports with three automatic attempts consume at most 60 requests/day; the modeled manual-reprocessing case adds 12/day. Per-page or follow-up calls increase this count and must fit the same shared project/model limits. Tickets 06/08 must enforce deadlines, token/request budgets and the total attempt ceiling, with backoff/rejection on quota exhaustion. One successful four-field synthetic sample does not benchmark ten-page extraction or establish medical correctness. Recheck effective limits before deployment; no paid fallback is selected.

## Credit expiry, shutdown and caps

The owner verified USD100 student credit expiring **20 October 2027**. ARM independently confirms the subscription is Enabled, the offer is Azure for Students, and `spendingLimit` is **On**. Keep it On and do not convert to pay-as-you-go. Microsoft describes service disablement when the protected allowance is exhausted; expiry/disablement can interrupt API availability and processing. Retention is not a backup guarantee. See [spending protection](https://learn.microsoft.com/en-us/azure/cost-management-billing/manage/spending-limit).

Before release, track the balance and expiry, cap attempts/time/memory/concurrency, enforce report and retained-byte allowances, and stop accepting new work before the safety reserve is reached. A budget alert alone is not a hard stop. Expired student credit does not establish another free hosted tier; preserve an explicit unavailable state until legitimate renewal or a verified ₹0 alternative is agreed.

The spike uses 0.25 vCPU / 0.5 GiB each for API and worker, one API replica, one event-driven execution, no platform retries, a 180-second worker deadline, a ten-minute queue message TTL and a test credential expiring after 24 hours. Credential expiry does **not** delete resources or prevent public health/page traffic. Delete its tagged resource group after the physical Android test and verify absence. With the API continuously active for 24 hours, its gross compute is about $0.648 before grants; concurrency caps bound usage but do not make it free.

## Dependencies and build feasibility

Inspected installed metadata/LICENSE files for the selected foundation dependencies:

| Dependency | License observed |
| --- | --- |
| FastAPI 0.116.1; Pydantic 2.11.7; pydantic-core 2.33.2 | MIT |
| Uvicorn 0.35.0; Starlette 0.47.3; httpx 0.28.1 | BSD-3-Clause |
| AnyIO 4.15.1; h11 0.16.0 | MIT |
| Click 8.5.0 | BSD-3-Clause |
| flutter_riverpod / riverpod 2.6.1 | MIT |
| go_router 14.8.1; Dart http 1.6.0 | BSD-3-Clause |

The issue-02 debug APK already built and ran on an Android API-35 emulator using the isolated Flutter/JDK toolchain. The cloud probe uses Python's standard library and the [official Python container image](https://hub.docker.com/_/python), so local Docker is unnecessary for this probe. This does not establish a built production OCR image or release-signed APK.

For ticket 07, feasible candidates inspected without adding or locking them:

- `pypdf` 6.21.1: BSD-3-Clause, Python ≥3.9, a platform-independent wheel. Native text extraction candidate ([upstream license](https://github.com/py-pdf/pypdf/blob/main/LICENSE)).
- `pypdfium2` 5.14.0: upstream Apache-2.0/BSD-3-Clause; Linux x86-64 wheel available, compatible with the intended Python 3.12 worker. Bundled PDFium and dependency notices must accompany the exact binary distribution. Rendering candidate; wheel availability is not a runtime/memory benchmark ([upstream packaging and license notes](https://pypdfium2.readthedocs.io/en/stable/readme.html#licensing)).
- Tesseract: Apache-2.0 upstream; include exact engine, trained-data and transitive native-library notices when packaging. Its ten-page performance remains ticket 07's acceptance test ([upstream license](https://github.com/tesseract-ocr/tesseract/blob/main/LICENSE)).

This is a feasibility review of selected dependencies and candidates, not a complete release notice inventory. No PDF/OCR package was locked by this spike.
