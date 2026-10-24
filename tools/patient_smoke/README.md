# Hosted Android patient acceptance

This probe deploys the normal API, queue-triggered worker and five-minute reconciler with real Firebase/Firestore, private Azure storage and the configured Gemini free-tier provider. It does not simulate processing status. Use only invented PDFs and the existing synthetic seed accounts.

Run from the repository root with the backend environment installed. Prerequisites are the owner-authorized Azure/Google configuration from the earlier smoke probes, spending protection On, the confirmed free model configuration, Docker, and a running Android emulator. The probe checks ownership tags and spending protection before infrastructure mutations. Never commit `.tooling/`.

```sh
backend/.venv/bin/python tools/patient_smoke/cloud.py init
backend/.venv/bin/python tools/patient_smoke/cloud.py infrastructure
backend/.venv/bin/python tools/patient_smoke/cloud.py build-push
backend/.venv/bin/python tools/patient_smoke/cloud.py deploy
backend/.venv/bin/python tools/patient_smoke/cloud.py status
```

Pass `--docker-binary` and `--docker-host` for a non-default Docker runtime. Responses and generated public Android configuration stay private under `.tooling/issue-9/azure/`. The hosted services receive a short-lived Google access token with no reusable refresh credential; rerun `deploy` to refresh it if the test exceeds its lifetime. Only the extraction worker receives the AI key. API and worker concurrency are bounded to one replica/execution; the API has zero minimum replicas and debug previews are disabled in generated defines.

Build/install the development APK with that ignored configuration:

```sh
cd app
../tools/flutterw build apk --debug --no-pub --dart-define-from-file=../.tooling/issue-9/azure/app-defines.json
adb install -r build/app/outputs/flutter-apk/app-debug.apk
```

Sign in with a synthetic patient. Acknowledge invented data and use the system picker to select an invented laboratory PDF named `ticket09-<first 12 characters of private spike_id>-synthetic.pdf`. This unpredictable run prefix scopes cleanup. Interrupt networking, restore it and continue the same upload. Stop the app while queued, observe server processing independently, reopen/sign in and verify the same report/case. Open the protected original PDF; sign out and sign in as the other synthetic patient to verify separation. Inspect only redacted UI dumps: text-field values must never appear in logs or screenshots. Do not put passwords into shell command arguments.

For a real cold-start check, stop the app so polling ceases, leave the endpoint idle and run `replicas` until it records zero. Then reopen/sign in and record the successful first hosted request and latency. Zero minimum replicas alone is not evidence of an observed cold start. Automated app tests cover session expiry, quota responses, bounded retries, duplicate completion and background polling without modifying real users/quotas.

```sh
backend/.venv/bin/python tools/patient_smoke/cloud.py replicas
backend/.venv/bin/python tools/patient_smoke/cloud.py collect
backend/.venv/bin/python tools/patient_smoke/cloud.py cleanup
backend/.venv/bin/python tools/patient_smoke/cloud.py cleanup-status
```

Stop the test app and wait for its processing jobs to become terminal before cleanup; the tool rejects active processing. Cleanup deletes only run-prefixed reports and their case/job/analysis/upload payload bookkeeping, releases their reservations, and requests deletion of the exact tagged Azure group. Minimal audit and real quota usage remain truthful; existing users are retained. Repeat `cleanup-status` until all temporary Azure resources are absent and run-owned Firestore payload/reservation checks pass. The persisted private manifest makes an interrupted cleanup resumable; cleanup also requeries report/job references and discovers duplicate upload aliases independently. The installed acceptance APK will need a new live API configuration after teardown. Never describe a temporary smoke deployment as an always-available production service.
