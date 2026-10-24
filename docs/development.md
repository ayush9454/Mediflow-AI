# Development

## Toolchain and setup

Use Python 3.12, Flutter 3.35.5 / Dart 3.9.2, JDK 17 and an Android SDK. CI uses standard Ubuntu GitHub-hosted runners with bounded job timeouts. No cloud account is needed for the foundation.

From the repository root:

```sh
python3.12 -m pip install uv==0.13.4
uv sync --project backend --locked --extra dev --extra evaluation --extra processing
backend/.venv/bin/python -m uvicorn mediflow.main:app --reload
```

The backend environment template is [backend/.env.example](../backend/.env.example). Export configuration through your shell or deployment environment; the application does not implicitly load `.env` files. Never commit account keys or service-account files.

The evaluation extra supplies offline synthetic PDF generation/rendering tools for
ticket 03's tests; production installation does not need it. See the
[benchmark guide](../evaluation/README.md) for fixture regeneration, frozen held-out
data, scoring rules and evaluation commands. See [laboratory extraction](laboratory-extraction.md)
for provider setup and development evaluation. Held-out release accuracy remains
a separate ticket-14 gate.

The liveness endpoint is `http://127.0.0.1:8000/health/live`; Swagger UI is `/api/v1/docs` and OpenAPI is `/api/v1/openapi.json`. Overall readiness remains 503 while document workflows are pending. Configure `MEDIFLOW_FIREBASE_PROJECT_ID` and backend-only Application Default Credentials for real token verification and server-owned account permissions. Missing/invalid tokens are denied; an unconfigured identity adapter fails closed. See [authentication setup and emulator checks](authentication.md).

In another terminal:

```sh
cd app
../tools/flutterw pub get --enforce-lockfile
../tools/flutterw run --dart-define=API_BASE_URL=http://10.0.2.2:8000
../tools/flutterw build apk --debug --no-pub
```

`10.0.2.2` reaches the host from an Android emulator. API configuration is optional for interface previews. You can also pass `--dart-define-from-file=dart-defines.example.json`. The application ID is currently `dev.mediflow.mediflow_ai`.

[tools/flutterw](../tools/flutterw) uses an ignored workspace-local Flutter SDK/pub cache under `.tooling/` if available, otherwise the installed Flutter. It suppresses analytics. These local copies are not project dependencies. Do not commit or upload `.tooling/`.

Use a JDK compatible with Gradle, preferably JDK 17. If Flutter selects Android Studio's bundled Java, select the installed JDK with `flutter config --jdk-dir=/path/to/jdk17` or pass `GRADLE_OPTS=-Dorg.gradle.java.home=/path/to/jdk17` for a single build. The local verification uses the latter with an ignored JDK under `.tooling/jdk17/Contents/Home`, and `GRADLE_USER_HOME` under `.tooling/gradle`.

## Baseline checks

From the repository root:

```sh
backend/.venv/bin/ruff format --check --config backend/pyproject.toml backend tools
backend/.venv/bin/ruff check --config backend/pyproject.toml backend tools
backend/.venv/bin/mypy --config-file backend/pyproject.toml backend/src
backend/.venv/bin/python -m pytest backend/tests
backend/.venv/bin/python tools/export_contracts.py --check
```

Focused backend checks use, for example, `backend/.venv/bin/python -m pytest backend/tests/test_contracts.py`. To apply Python formatting, omit `--check` from `ruff format`.

From `app/`:

```sh
../tools/flutterw analyze --no-pub
../tools/flutterw test --no-pub test/navigation_test.dart
../tools/flutterw test --no-pub
# Use dart from the same Flutter SDK.
dart format --output=none --set-exit-if-changed lib test tool
dart run tool/contract_smoke.dart
../tools/flutterw build apk --debug --no-pub
```

CI runs these checks on pushes and pull requests. Publishing the workflow and observing a remote run require a push; local verification does not establish remote CI success.

## Shared contracts

Edit the Pydantic contracts/routes, then regenerate and review the artifacts together:

```sh
backend/.venv/bin/python tools/export_contracts.py
backend/.venv/bin/python tools/export_contracts.py --check
```

Commit OpenAPI, JSON Schema, Dart models and synthetic fixtures together. Do not hand-edit `contracts.g.dart`. `backend/uv.lock` pins dependencies used by development, CI and the Docker build. Update dependencies intentionally, regenerate contracts and rerun both language checks when the lock changes.

Dart wire models enforce JSON types; semantic constraints and authorization belong on the backend. Parsed lists are unmodifiable. Fixtures are never served as clinical results. Report metadata exposes case and review versions, and case summaries also expose review versions. Review versions start at zero and increase monotonically per report across reprocessing. Review requests include analysis, case and prior review versions; future persistence must compare these atomically with current assignment and review records.

## Adapter and Android boundaries

Upload database/document protocols and real Firestore/Azure adapters are in `backend/src/mediflow/uploads/`; other integration protocols remain in `backend/src/mediflow/ports.py`. Configuration selects real upload adapters but does not establish end-to-end workflow readiness. Check worker configuration without consuming messages:

```sh
backend/.venv/bin/python -m mediflow.worker --check-config
```

The worker receives one queue delivery per execution and uses Firestore-authoritative
leases and result commits. Run `python -m mediflow.worker --reconcile` from an
independent scheduled Job for missed dispatches and expired leases. The normal
provider runs the configured [laboratory extraction pipeline](laboratory-extraction.md)
and never substitutes test rows. See [job deployment, recovery and retry bounds](jobs.md).

Debug builds provide clearly labeled patient, doctor and administrator previews, independent of authentication. `ENABLE_ROLE_PREVIEW=false` disables them; release/profile cannot enable them. Real sign-in requires the public `FIREBASE_API_KEY` and an API configured with Firebase/Firestore credentials. The patient Reports/History tabs implement [PDF upload and status recovery](patient-upload.md); doctors can open the [result/evidence viewer](evidence-viewer.md) using an assigned report reference. Assigned-case discovery, review writes and administrator workflows remain in later tickets. Tokens and temporary clinical bytes stay in memory and are cleared on logout/account change/expiry.

## PDF/OCR worker and verification

Install the processing extra and Tesseract English to run real OCR tests. Both `backend/Dockerfile` and `backend/Dockerfile.worker` install the native OCR
engine: the API verifies stored uploads, and the worker supplies isolated page
processing. See [processing limits and benchmark commands](document-processing.md).
The benchmark uses only development/negative fixtures and dedicated supplements.
Do not use the held-out set for processing heuristics or extraction tuning.

CI runs native/OCR behavior tests, a container benchmark at 0.5 vCPU / 1 GiB, and
the report gate in `tools/check_processing_report.py`. A separate Firebase job uses
Node 24, Java 25 and the pinned Firebase CLI to exercise actual emulator token and
Firestore-rule behavior. These tests need no production credentials. Local Android
builds continue to use JDK 17.

`API_BASE_URL` must be an origin URL without credentials, query or fragment. Local HTTP is debug-only; profile/release requires HTTPS. Android backup is disabled. Release signing remains unconfigured until ticket 15; debug signing is never used for a release. The debug APK includes patient upload/status screens when configured with a live API.

## Verification record

Python 3.12.15 was installed into the ignored workspace tooling directory and a fresh locked backend environment was created. Contract/API checks, Python formatting/linting, static type checking, generated-artifact checks, Flutter analysis, routing tests and Dart fixture tests pass. All 24 backend tests and 11 Flutter tests pass. The JDK 17 debug APK build passes and the APK installs/cold-starts on an Android 15/API 35 emulator. All three role previews open, remain explicitly labeled, and return to sign-in; screenshots were inspected and runtime error logs were empty. A real Uvicorn process served health, Swagger UI and OpenAPI locally.

The previous restricted-session socket, package-download and Git-write limitations no longer apply. See [ticket 02](../.scratch/mediflow-mvp/issues/02-foundation-contracts-ci.md) for final suite/build results and remaining limits.

## Azure feasibility

Student activation was verified on 2026-10-20: USD100 credit available, expiry 20 October 2027, and displayed October costs USD0.00. No account/subscription identifiers or personal details are recorded.

Ticket 01's isolated synthetic probe verified spending protection On, Central India capacity (100 Consumption-core quota), authenticated HTTPS, denied anonymous Blob access and automatic queue-triggered completion. The owner reported the physical Android/laptop-off request succeeded. Firebase is ACTIVE on Spark with no linked Cloud Billing account; Gemini 3.5 Flash-Lite's model-specific Free limits are 15 requests/minute, 250,000 input tokens/minute and 500 requests/day. The probe's temporary Azure teardown is complete. Ticket 04 subsequently configured email/password, a Standard Firestore database and deny-all client rules; five synthetic live sign-ins and server-side policy checks pass. Public API configuration and owner credentials stay ignored under `.tooling/issue-4/`.

See [sanitized evidence](../.scratch/mediflow-mvp/hosting-evidence.json), [costs and expiry](../.scratch/mediflow-mvp/hosting-costs.md) and [probe deployment/cleanup commands](../tools/hosting_spike/README.md). The probe uses its own temporary test credential and fixed object. Subsequent tickets add real storage/queue adapters, durable extraction and the patient Android workflow. Overall readiness remains fail-closed until the full role workflow is ready.

## Private uploads (ticket 05)

See [private upload setup and verification](private-uploads.md) for Azure managed identity, private container provisioning, bounded admission, transaction records for ticket 06, and trusted orphan cleanup. The API image now includes English Tesseract for stored-byte PDF verification. The app upload screen is documented in [patient uploads](patient-upload.md), and actual queue/worker dispatch in [jobs](jobs.md). No hosted production API was deployed by ticket 05.
