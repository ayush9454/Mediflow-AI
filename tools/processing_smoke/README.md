# Temporary Azure OCR acceptance probe

This validates the actual private Linux/amd64 worker in a manual Azure Container
Apps Job. It is a disposable synthetic-only check, not the durable application
worker or a deployment command for patient records. Its Basic registry and short
job consume the student credit modeled in ticket 01.

Prerequisites: complete the existing owner Azure login; private issue-01 settings
must identify an Enabled subscription with spending protection **On**. The probe
refuses other states. The repo's final integrated dependencies must already be
synced, including development, evaluation, and processing extras. Use a running
Linux Docker engine with amd64 support. No registry administrator password,
shared storage key, SAS, model credential, or service-account file is needed.

Run each stage from the repo root. All raw responses, credentials and IDs stay in
ignored `.tooling/issue-7/azure/` with private directory/file permissions. Do not
copy those raw files into tickets, PRs, or Git. A previous `state.json` means resume
or clean that probe; `init` refuses to create another one.

```sh
backend/.venv/bin/python tools/processing_smoke/cloud.py init
backend/.venv/bin/python tools/processing_smoke/cloud.py infrastructure
backend/.venv/bin/python tools/processing_smoke/cloud.py build-push
backend/.venv/bin/python tools/processing_smoke/cloud.py deploy
backend/.venv/bin/python tools/processing_smoke/cloud.py start
backend/.venv/bin/python tools/processing_smoke/cloud.py status
# Run collect after status reports Succeeded.
backend/.venv/bin/python tools/processing_smoke/cloud.py collect
```

Use `--workspace /path/to/integrated/repo` when invoking from another worktree.
`build-push` accepts `--docker-binary /path/to/docker` and optional
`--docker-host unix:///path/to/socket`; otherwise it uses `docker` and `DOCKER_HOST`.
It generates exactly 35 allowlisted development/negative/supplemental fixtures
from the integrated source, never reads held-out definitions or artifacts, builds
locally for linux/amd64, authenticates to private ACR through an owner token on
stdin, pushes, and logs Docker out afterward. Registry admin access remains disabled.

The new tagged group contains only a Basic private registry, a standard environment
with the Consumption profile, one user identity, private result Blob storage, and
one manual Job. The identity has registry-scoped AcrPull and storage-scoped Blob
Contributor; the current owner receives storage-scoped Blob Reader for collection.
There is no public app ingress, dedicated profile, Log Analytics, Marketplace
service, subscription conversion, or private networking. The Job has 0.5 vCPU,
1 GiB, one replica/completion, a 300-second timeout, and zero platform retries.
The processing interface retains its stricter 240-second document deadline.

`runtime.py` runs the real benchmark and independently checks expected negative
outcomes and ten-page OCR numbering before uploading synthetic metadata via managed
identity. It does not upload source text or PDFs as a result. `collect` refuses an
unsuccessful execution, verifies the execution's actual ARM allocation and checks
the report and expected-outcome marker. The current Azure runtime exposes v1
counters: 1 GiB memory and observed CPU quota/period values of `50000 100000`
(0.5 cores) and `400000 100000` (4 cores), for the same requested 0.5 vCPU.
The cloud gate allows only those observed quotas; the
offline gate continues to require `50000 100000` (a strict 0.5-core cap). These are
separate measurements; always report the actual quota alongside cloud timing.
The private
`azure-processing.json` can be inspected and sanitized for a committed report;
execution IDs, account IDs, endpoint names and tokens belong only in ignored state.

Always finish cleanup, including after a failed build or Job:

```sh
backend/.venv/bin/python tools/processing_smoke/cloud.py cleanup
backend/.venv/bin/python tools/processing_smoke/cloud.py cleanup-status
```

`cleanup` verifies the probe's exact ownership tags before requesting group deletion.
Repeat `cleanup-status` until it reports **all temporary resources deleted: True**.
A deletion request alone is not evidence of removal. Cleanup remains available if
credit/session status changes; it never modifies unrelated issue-01 resources.

Azure provisioning can outlast an individual ARM request. If `infrastructure`
reports `StorageAccountIsNotProvisioned` or `ManagedEnvironmentOperationInProgress`,
wait for the recorded resources to finish provisioning and repeat that same stage.
Keep the existing private state; do not run `init` again. A regional environment
quota conflict can also persist while an earlier probe's environment is being
deleted. Confirm that earlier probe's cleanup before retrying; do not change
regions, subscription limits, or spending protection to bypass the conflict.
