# Disposable hosted durable-jobs acceptance

This is explicitly a synthetic integration adapter, isolated under one disposable
`jobSmokeRuns/{opaque-id}` Firestore namespace. It runs the actual coordinator,
private Blob adapter, Azure queue adapter and worker entry function. The candidate
adapter produces no laboratory rows/summary and marks its result with a blocking
`test_adapter` issue. It cannot be selected in a production or demo worker.

Prerequisites: the existing owner Azure login and private issue-01 settings; active
student subscription with spending protection On; existing private issue-04 Google
owner ADC and project settings; a Linux Docker engine with amd64 support. Nothing
links Cloud Billing, converts the subscription or creates an account/service key.

```sh
backend/.venv/bin/python tools/jobs_smoke/cloud.py init
backend/.venv/bin/python tools/jobs_smoke/cloud.py infrastructure
# If Azure storage is still provisioning, repeat infrastructure once it is ready.
backend/.venv/bin/python tools/jobs_smoke/cloud.py build-push
backend/.venv/bin/python tools/jobs_smoke/cloud.py deploy
backend/.venv/bin/python tools/jobs_smoke/cloud.py seed
# Wait for the independent five-minute schedule and subsequent queue execution.
backend/.venv/bin/python tools/jobs_smoke/cloud.py collect
# After the initial run succeeds, exercise a new authorized run and duplicates:
backend/.venv/bin/python tools/jobs_smoke/cloud.py reprocess
# Wait for the replacement to succeed, then:
backend/.venv/bin/python tools/jobs_smoke/cloud.py duplicate
backend/.venv/bin/python tools/jobs_smoke/cloud.py collect
```

`build-push` accepts `--docker-binary` and `--docker-host`. For a Homebrew Docker
installation the probe preserves its BuildKit plugin search path while isolating
registry login configuration. Logins use short-lived owner tokens on stdin and
logout runs after push. The deployed image is pinned by digest.

The tagged temporary group contains a private Basic ACR, a standard Consumption
environment, user-assigned identity, private LRS storage, one event Job and one
scheduled Job. Shared storage keys/public Blob access/registry admin access are
disabled. The worker has 0.5 vCPU/1 GiB, timeout 420 seconds, one replica/completion,
parallelism one, maximum event executions one and zero platform retries. The
scheduled reconciler has a 120-second timeout and runs every five minutes. These
resources consume student credit. No Log Analytics or dedicated networking is added.

The owner seed accepts one synthetic upload using real Blob and Firestore adapters
but deliberately does not enqueue it. The hosted schedule finds the intent and
dispatches it, and the event scaler starts the hosted worker. The laptop has no
dispatcher/worker role after seeding. `collect` verifies durable job/candidate/attempt
and audit counts plus a successful hosted event execution, rather than HTTP success.
The reprocessing stage preserves the initial run and verifies an identical request
returns the same new run. Duplicate messages must yield two additional successful
worker executions without another candidate, attempt, quota charge or success audit.

The temporary Google credential is a refreshed, short-lived owner OAuth access
token stored only as an Azure secret and in ignored private ARM request files.
This is not the production credential design. Complete the probe within that token's
lifetime; rerun deploy to refresh before seeding if needed. `deploy` does not start
a worker manually. There is no public API or clinical content serving from this probe.

Private settings, cloud responses, registry login and execution details remain under
ignored `.tooling/issue-6/azure/`. Only sanitized evidence belongs in the ticket.
Always clean up, including after a failed stage:

```sh
backend/.venv/bin/python tools/jobs_smoke/cloud.py cleanup
backend/.venv/bin/python tools/jobs_smoke/cloud.py cleanup-status
```

Cleanup checks the exact ownership tags, deletes only the recorded Azure group,
and removes the disposable Firestore namespace. Repeat `cleanup-status` until it
confirms the group is absent. Production resources, seeded users and existing reports
are never part of this probe's cleanup.
