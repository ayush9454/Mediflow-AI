# Development

## Toolchain and setup

Use Python 3.12, Flutter 3.35.5 / Dart 3.9.2, JDK 17 and an Android SDK. CI uses standard Ubuntu GitHub-hosted runners with bounded job timeouts. No cloud account is needed for the foundation.

From the repository root:

```sh
python3.12 -m pip install uv==0.13.4
uv sync --project backend --locked --extra dev --extra evaluation
backend/.venv/bin/python -m uvicorn mediflow.main:app --reload
```

The backend environment template is [backend/.env.example](../backend/.env.example). Export configuration through your shell or deployment environment; the application does not implicitly load `.env` files. Never commit account keys or service-account files.

The evaluation extra supplies offline synthetic PDF generation/rendering tools for
ticket 03's tests; production installation does not need it. See the
[benchmark guide](../evaluation/README.md) for fixture regeneration, frozen held-out
data, scoring rules and evaluation commands. No extraction accuracy is measured yet.

The liveness endpoint is `http://127.0.0.1:8000/health/live`; Swagger UI is `/api/v1/docs` and OpenAPI is `/api/v1/openapi.json`. Readiness intentionally returns 503 until working adapters exist. Protected routes return 401 without a token and 503 for token-shaped text until real Firebase verification is implemented. There is no fake authenticated account or production in-memory clinical store.

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

Azure, Firebase and AI integration protocols are in `backend/src/mediflow/ports.py`. Configuration alone does not instantiate or verify a cloud adapter. Check worker configuration without consuming messages:

```sh
backend/.venv/bin/python -m mediflow.worker --check-config
```

The actual worker deliberately exits unsuccessfully until the durable queue/processing adapter exists.

Debug builds provide clearly labeled patient, doctor and administrator previews, independent of authentication. `ENABLE_ROLE_PREVIEW=false` disables them; release/profile cannot enable them. Sign-in and workflow controls are placeholders for subsequent tickets.

`API_BASE_URL` must be an origin URL without credentials, query or fragment. Local HTTP is debug-only; profile/release requires HTTPS. Android backup is disabled. Release signing remains unconfigured until ticket 15; debug signing is never used for a release. The debug APK is a foundation interface build.

## Verification record

Python 3.12.15 was installed into the ignored workspace tooling directory and a fresh locked backend environment was created. Contract/API checks, Python formatting/linting, static type checking, generated-artifact checks, Flutter analysis, routing tests and Dart fixture tests pass. All 24 backend tests and 11 Flutter tests pass. The JDK 17 debug APK build passes and the APK installs/cold-starts on an Android 15/API 35 emulator. All three role previews open, remain explicitly labeled, and return to sign-in; screenshots were inspected and runtime error logs were empty. A real Uvicorn process served health, Swagger UI and OpenAPI locally.

The previous restricted-session socket, package-download and Git-write limitations no longer apply. See [ticket 02](../.scratch/mediflow-mvp/issues/02-foundation-contracts-ci.md) for final suite/build results and remaining limits.

## Azure feasibility

Student activation was verified on 2026-10-20: USD100 credit available, expiry 20 October 2027, and displayed October costs USD0.00. No account/subscription identifiers or personal details are recorded.

Ticket 01's isolated synthetic probe verified spending protection On, Central India capacity (100 Consumption-core quota), authenticated HTTPS, denied anonymous Blob access and automatic queue-triggered completion. The owner reported the physical Android/laptop-off request succeeded. Firebase is ACTIVE on Spark with no linked Cloud Billing account; Gemini 3.5 Flash-Lite's model-specific Free limits are 15 requests/minute, 250,000 input tokens/minute and 500 requests/day. Temporary Azure teardown is complete and group absence was verified; Firebase remains for authentication work in ticket 04.

See [sanitized evidence](../.scratch/mediflow-mvp/hosting-evidence.json), [costs and expiry](../.scratch/mediflow-mvp/hosting-costs.md) and [probe deployment/cleanup commands](../tools/hosting_spike/README.md). The probe uses its own temporary test credential and fixed object. The actual application still requires real Firebase verification, storage/queue adapters and processing; readiness remains fail-closed.
