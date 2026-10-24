# Hosted three-role journey

This reuses the real patient-upload deployment with a separate private directory,
unpredictable run prefix and ownership tags for ticket 12. It runs the production
API, queue-triggered extraction worker and scheduled reconciler. No result or
approval fixtures are served. Prerequisites and resource bounds are the same as
the [patient probe](../patient_smoke/README.md).

From the repository root, pass `--docker-binary` and `--docker-host` if needed:

```sh
backend/.venv/bin/python tools/journey_smoke/cloud.py init
backend/.venv/bin/python tools/journey_smoke/cloud.py infrastructure
backend/.venv/bin/python tools/journey_smoke/cloud.py provisioning
backend/.venv/bin/python tools/journey_smoke/cloud.py build-push
backend/.venv/bin/python tools/journey_smoke/cloud.py deploy
backend/.venv/bin/python tools/journey_smoke/cloud.py status
```

Azure can return an in-progress conflict while environment/storage creation is
still running. Check `provisioning` and resume `infrastructure` when both report
`Succeeded`. Do not create another run to bypass a pending operation.

Build/install the Android development APK using
`.tooling/issue-12/azure/app-defines.json`. Use only invented PDFs whose names start
with `ticket12-<first 12 characters of private spike_id>-`. Use different bytes
for each patient's source. Keep all credentials and raw UI dumps private; redact
input fields in saved inspection artifacts. The inherited deploy refreshes the
short-lived backend Google token; repeat it when necessary during acceptance.

Complete the [sample journey](../../docs/sample-journey.md) on the installed APK:
two patients, two doctors, administrator assignment/reassignment, source-grounded
correction, unresolved qualification, approval, reprocessing, rejection and a new
approval. Check the patient default result endpoint before and after approval and
while replacements run. It must never return a draft. Lists use role-authorized
views with bounded scans; a page may be empty with a next cursor. Continue loading
until the desired case or the end of the list. Cursors cannot cross accounts/views.

```sh
backend/.venv/bin/python tools/journey_smoke/cloud.py collect
backend/.venv/bin/python tools/journey_smoke/cloud.py cleanup
backend/.venv/bin/python tools/journey_smoke/cloud.py cleanup-status
```

Stop the app and let processing become terminal before cleanup. Cleanup removes
only run-prefixed synthetic reports, sources, analyses, approved snapshots, review
payloads, assignment/review/reprocess operation bookkeeping and reservations. It
preserves accounts, truthful upload quotas and minimal audit events. The private
manifest makes deletion resumable. Repeat `cleanup-status` until both payload
absence and temporary resource-group absence are verified. If only an empty
environment remains scheduled for deletion, use `cleanup-environment` and verify
again. The acceptance APK needs fresh server configuration after teardown.
