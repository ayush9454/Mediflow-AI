# MediFlow AI

An Android college project for evidence-linked extraction from **synthetic laboratory PDFs** and simulated doctor review, with a hosted backend planned around Azure student benefits and ₹0 out-of-pocket spending.

[Agreed specification](.scratch/mediflow-mvp/spec.md) · [Roadmap](.scratch/mediflow-mvp/roadmap.md) · [Tickets](.scratch/mediflow-mvp/README.md) · [Development setup](docs/development.md) · [API contracts](contracts/README.md)

## Current implementation

The foundation includes:

- Flutter Android shell with Riverpod, GoRouter, synthetic-only messaging and debug-only patient/doctor/administrator interface previews.
- FastAPI liveness/readiness endpoints, safe errors/request IDs and versioned OpenAPI workflow contracts.
- Pydantic models and generated Dart models for reports, evidence, laboratory rows, processing jobs, assignment and versioned review.
- Fail-closed authentication/workflow/worker boundaries and deny-by-default Firebase rules.
- Backend tests, Flutter contract/navigation tests, a socket-free Dart smoke check, a backend Dockerfile and GitHub Actions checks.

Authentication, report upload, cloud adapters, OCR, AI extraction and clinical review are **not connected yet**. Preview selection never authenticates a user or loads patient records. Release builds cannot enable role previews.

The issue-01 synthetic hosting probe verified protected Azure student access, Central India capacity, authenticated HTTPS, private Blob access and an automatic queue-triggered job. The owner reported a successful Android request with the laptop off. Firebase Spark and Gemini Free access/quotas are verified; the temporary Azure resources were deleted and group absence was verified. See [hosting evidence](.scratch/mediflow-mvp/hosting-evidence.json) and [cost/expiry notes](.scratch/mediflow-mvp/hosting-costs.md). This probe does not connect or deploy the application workflows above.

## Quick start

Use Python 3.12, Flutter 3.35.5/Dart 3.9.2, and JDK 17 for the documented build baseline. An Android SDK/emulator or Android device is required for APK installation.

From the repository root:

```sh
python3.12 -m pip install uv==0.13.4
uv sync --project backend --locked --extra dev
backend/.venv/bin/python -m uvicorn mediflow.main:app --reload
```

The API exposes:

- GET /health/live: process liveness.
- GET /health/ready: currently 503/not_ready until actual adapters exist.
- /api/v1/docs: interactive API contracts.
- /api/v1/openapi.json: machine-readable OpenAPI.

In another terminal:

```sh
cd app
flutter pub get --enforce-lockfile
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000
```

The example URL reaches the host from the standard Android emulator. For a physical phone, use a reachable development API address. Debug Android builds allow local HTTP; profile/release builds require HTTPS. Omit API_BASE_URL to explore the interface without a backend.

No account can sign in yet. Debug builds expose clearly labeled interface previews; production authentication is the next foundation dependency.

## Checks

```sh
backend/.venv/bin/ruff format --check --config backend/pyproject.toml backend tools
backend/.venv/bin/ruff check --config backend/pyproject.toml backend tools
backend/.venv/bin/mypy --config-file backend/pyproject.toml backend/src
backend/.venv/bin/python -m pytest backend/tests
backend/.venv/bin/python -m unittest discover -s tools/hosting_spike -p 'test_*.py'
backend/.venv/bin/python tools/export_contracts.py --check
cd app
dart format --output=none --set-exit-if-changed lib test tool
flutter analyze --no-pub
flutter test --no-pub
dart run tool/contract_smoke.dart
flutter build apk --debug --no-pub
```

See [local validation notes](docs/development.md#verification-record) for checks actually run and their limits. CI configuration exists but has not run on a remote repository yet.

## Project layout

```text
app/                 Flutter Android application and typed client
backend/src/mediflow/ FastAPI, contracts, configuration and adapter interfaces
backend/tests/       Contract and API-boundary tests
contracts/           Generated OpenAPI, schemas and synthetic examples
firebase/            Deny-by-default rules
tools/               Contract exporter and local Flutter wrapper
.github/workflows/   CI checks (no deployment credentials required)
.scratch/mediflow-mvp/Agreed specification and dependency-ordered tickets
```

Provider keys, service accounts and signing keys stay outside source control. No patient or student credentials are needed to run the foundation contracts and tests.
