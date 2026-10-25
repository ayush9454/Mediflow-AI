# Retention and operation of the synthetic demo

Verified originals expire 30 days after upload verification. Every protected report
operation denies expired content before physical cleanup. Result/review transactions
check expiry again; original downloads recheck after storage I/O. Worker deadlines
cannot extend past source expiry, and claim, failure, reconciliation and result commit
check the authoritative report. Removing an expired report cannot make a stale queue
delivery recreate it.

## Cleanup schedule and recovery

Deploy [jobs.bicep](../backend/jobs.bicep) with the worker image and existing backend
credentials. It defines separate five-minute reconciliation and retention Jobs,
each with one replica, zero platform retries, a 120-second execution timeout and
0.25 vCPU / 0.5 GiB. The cleanup Job runs:

```sh
python -m mediflow.worker --maintenance --limit 20
```

The same trusted boundary can be run locally with configured backend credentials:

```sh
backend/.venv/bin/python -m mediflow.uploads --limit 100
```

There is no client deletion endpoint and no Firestore TTL dependency. Scheduling
uses the existing [Container Apps Jobs configuration](https://learn.microsoft.com/en-us/azure/templates/microsoft.app/jobs).
Provisioning the template is required for automatic cleanup; merely running the
API does not start a scheduler.

Each sweep handles a bounded page of abandoned sessions and tracked Blob prefixes,
then advances a persistent document-ID cursor through reports. Expired reports are
deleted in phases: source objects, analyses/page text/provider output, reviews,
review indexes, processing runs/attempts, hash indexes, then source/session/case/report
metadata and the approved snapshot. Each child page has at most 100 records.
Expiry remains effective throughout these phases. A failing source does not stop
the scan from reaching other reports. A cleanup lease lasts two minutes; retry
after that lease if an execution stops. Object deletion and database transitions
are idempotent, including when a successful delete loses its response.

Each invocation also removes a bounded batch of expired idempotency responses,
quota/rate records and audit events. Audit expiry uses its stored timestamp type.
The final expiry event retains opaque resource/hospital IDs, time, action and outcome;
it contains no filename, rows, source text, review comment or model payload and
expires after another 30 days. Keep running maintenance until any backlog clears;
a bounded batch can report zero completed reports while advancing deletion phases.

## Initial resource limits

| Control | Initial limit |
| --- | --- |
| Original PDF | 10,000,000 bytes; 10 pages |
| Accepted uploads | 5/patient and 20/hospital per UTC day |
| Pending reservations | 5/patient and 20/hospital; one-hour lifetime |
| Registration churn | 20/patient and 100/hospital per UTC day |
| Source write and verification attempts | 3 each per reservation |
| Storage payload budget | 1,000,000,000 bytes per hospital; configurable downward |
| Serialized analysis/review/snapshot | 900,000 UTF-8 JSON bytes per record |
| Manual reprocessing | 2/report per UTC day; 60-second cooldown |
| Processing attempts | Initial attempt plus 2 automatic retries |
| Active processing | 1 transactional lease per hospital |
| PDF/OCR admission / worker page processing | 240 / at most 200 seconds |
| Provider | One bounded call/attempt; at most 40 seconds and 8,192 output tokens |
| Complete job | At most 270 seconds, also capped by report expiry |
| API upload stream | 60 seconds; one active stream per API process |
| Access / transition audit writes | Separate 10,000-event budgets per UTC day |
| Unexpected API error logging | At most 100 short entries per process per minute |

These are conservative admission controls, not promises that every daily upload
can use the maximum size for 30 days. The earlier hosting estimate allowed 6 GB of
maximum-size originals; this implementation intentionally stops sooner. The
[hosting measurements](../.scratch/mediflow-mvp/hosting-costs.md) and
[bounded OCR measurements](document-processing.md) motivate keeping one worker,
finite deadlines and a smaller storage allowance for a college demonstration.

`MEDIFLOW_STORAGE_LIMIT_BYTES` must match on API and workers and may be set from
1 through 1,000,000,000. Registration atomically reserves three times the declared
source bytes for three possibly uncertain immutable writes. Analyses, reviews and
approved snapshots charge their serialized UTF-8 bytes to the same ledger;
replacement snapshots charge only the size difference. A quota failure rolls back
approval rather than publishing a partial record. An analysis capacity failure
becomes a safe terminal `quota_exhausted` outcome.

The budget measures source bytes plus serialized clinical payloads. Platform
metadata, indexes, container images and minimal audit events have separate bounds;
the ledger is not an Azure/Firestore billable-byte meter. Orphan and duplicate
source allowances remain reserved in their prefix-sweep records for up to 31 days,
even after an apparent successful delete, to cover delayed writes. Completed report
cleanup releases its source allowance after deletion. A full ledger returns 429;
it does not silently discard a report or buy more capacity.

Stop old writers before upgrading. An absent capacity-policy marker with existing
upload/source/clinical payload records fails closed rather than assuming zero usage.
Use the old environment's trusted export/cleanup procedure or a fresh isolated demo
environment before accepting uploads with the new policy. Seeded account/workflow
metadata without clinical payloads does not consume this payload budget.

Audit-budget exhaustion fails closed with 429; it does not drop required events
and continue access. Idempotent state transitions do not charge the same audit event
twice. The separate access budget keeps repeated access attempts from consuming
the state-transition budget. Audit budgets and daily quotas are also swept.

## Safe diagnostics

An active hospital administrator may read
`GET /api/v1/reports/{reportId}/operations`. It returns only report/job/attempt IDs,
attempt count, processing status, safe failure code, update/deadline timestamps,
the current request ID and the hospital's storage budget. Patients and doctors
cannot use this route. Administrators still cannot read clinical results or PDFs.

Every API response has a server-generated `X-Request-ID`; operational JSON returns
the same ID. Unexpected-error logs contain only `internal_error` and that ID.
Production API access logging is disabled so request paths are not copied into
logs. Worker/cleanup command failures use a short safe message rather than a raw
exception or traceback. Do not enable SDK HTTP-body/debug logging or add paid log
ingestion/export. Audit events provide durable bounded transition history.

## Credits, stopping, export and reset

The account owner checks the Azure credit balance/expiry and spending protection
before a hosted demo and daily while hosting is retained. Record dated observations
privately; the [2026-10-21 estimate](../.scratch/mediflow-mvp/hosting-costs.md) is not
a current balance. Keep spending protection On, Firebase without linked billing,
and the explicitly confirmed provider free tier. A budget alert is a notification;
these application limits do not query or enforce a live credit balance.

Before credits/benefits become unavailable, set `MEDIFLOW_ACCEPT_NEW_WORK=false`
on both API and worker/reconciler deployments. New registrations, unfinished writes,
verification, reprocessing, dispatch and execution claims stop. Existing verified
private reads remain authorized until expiry. An already-running attempt may finish
within its original deadline. Run cleanup/export while credentials and services
still work, then stop/delete the owned event worker, schedules and API resources;
the flag alone does not remove infrastructure or eliminate read/registry costs.
Queued logical jobs remain durable and can be redispatched after a legitimate
resume. Never remove spending protection or select a paid fallback to resume.
[Azure documents service disablement at the credit limit](https://learn.microsoft.com/en-us/azure/cost-management-billing/manage/spending-limit).

Before expiry, an owner can export their original PDF and approved result through
the existing authenticated endpoints. A currently assigned doctor can export draft
and review history through their authorized endpoints. Use only synthetic records
and keep exports private. For example, with a patient token supplied privately:

```sh
umask 077
mkdir -p .tooling/synthetic-export
curl --fail --silent --show-error \
  "$API_BASE_URL/api/v1/reports/$REPORT_ID/document" \
  --header "Authorization: Bearer $PATIENT_ID_TOKEN" \
  --output .tooling/synthetic-export/original.pdf
curl --fail --silent --show-error \
  "$API_BASE_URL/api/v1/reports/$REPORT_ID/result" \
  --header "Authorization: Bearer $PATIENT_ID_TOKEN" \
  --output .tooling/synthetic-export/approved.json
```

Expired content cannot be exported by bypassing API authorization. For a repeatable
demonstration, regenerate development fixtures and follow the
[sample journey](sample-journey.md). The trusted seed command can reset account
passwords/enablement and revoke sessions without erasing reports or quota usage:

```sh
backend/.venv/bin/python -m mediflow.seed \
  --confirm-project "$MEDIFLOW_FIREBASE_PROJECT_ID" --synthetic-only \
  --secrets-file /private/path/to/synthetic-accounts.json --reset-accounts
```

For disposable hosted runs, use their recorded, ownership-checked
[cleanup procedure](../tools/journey_smoke/README.md) and verify resource-group and
run-owned payload absence. Preserve seeded accounts and truthful audit/quota records.
Do not edit clinical outcomes or counters to reset a demonstration.

## Verification

The [retention tests](../backend/tests/test_retention.py) exercise controllable time,
lost deletion responses, a persistently unavailable object, approved/review copies,
capacity release and stale processing. The same suite runs against real Firestore
transactions through `MEDIFLOW_UPLOAD_TEST_FIRESTORE=1` inside the documented
[Firebase emulator command](development.md). Blob failures are injected at the
external object-store boundary. Deployment-template compilation validates the
schedule definition; it does not establish a deployed hosted scheduler.
