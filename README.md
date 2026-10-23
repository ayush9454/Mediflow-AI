# MediFlow AI

An Android college project for evidence-linked extraction from **synthetic laboratory PDFs** and simulated doctor review, with a hosted backend planned around Azure student benefits and ₹0 out-of-pocket spending.

[Agreed specification](.scratch/mediflow-mvp/spec.md) · [Roadmap](.scratch/mediflow-mvp/roadmap.md) · [Tickets](.scratch/mediflow-mvp/README.md) · [Development setup](docs/development.md) · [API contracts](contracts/README.md)

## Current implementation

The current implementation includes:

- Flutter Android shell with Riverpod, GoRouter, synthetic-only messaging and debug-only patient/doctor/administrator interface previews.
- FastAPI liveness/readiness endpoints, safe errors/request IDs and versioned OpenAPI workflow contracts.
- Pydantic models and generated Dart models for reports, evidence, laboratory rows, processing jobs, assignment and versioned review.
- Configurable real Firebase authentication, server-owned roles and resource permissions, trusted synthetic seeding, Android sign-in/session handling and deny-by-default Firebase rules.
- Forty synthetic benchmark fixtures with independent annotations and frozen held-out data.
- Authenticated bounded private PDF uploads, stored-byte verification, patient-scoped duplicates, atomic quotas and durable processing-job intent.
- Isolated native PDF/OCR processing with page evidence, explicit rejection outcomes, and a worker container with bounded resources.
- Backend tests, Flutter contract/navigation tests, a socket-free Dart smoke check, a backend Dockerfile and GitHub Actions checks.

Private uploads are implemented; see the [upload guide](docs/private-uploads.md). Durable queue/worker integration, AI row extraction and clinical review remain in later tickets. PDF/OCR processing verifies upload admission and is also available as an offline worker module. No hosted production API is deployed. Debug previews remain distinct from real sign-in. Release builds cannot enable previews.

The issue-01 synthetic hosting probe verified protected Azure student access, Central India capacity, authenticated HTTPS, private Blob access and an automatic queue-triggered job. The owner reported a successful Android request with the laptop off. Firebase Spark and Gemini Free access/quotas are verified; the temporary Azure resources were deleted and group absence was verified. See [hosting evidence](.scratch/mediflow-mvp/hosting-evidence.json) and [cost/expiry notes](.scratch/mediflow-mvp/hosting-costs.md). This probe does not connect or deploy the application workflows above.

## Quick start

Use Python 3.12, Flutter 3.35.5/Dart 3.9.2, and JDK 17 for the documented build baseline. An Android SDK/emulator or Android device is required for APK installation.

From the repository root:

```sh
python3.12 -m pip install uv==0.13.4
uv sync --project backend --locked --extra dev --extra evaluation --extra processing
backend/.venv/bin/python -m uvicorn mediflow.main:app --reload
```

The API exposes:

- GET /health/live: process liveness.
- GET /health/ready: currently 503/not_ready while the complete processing workflow remains pending.
- /api/v1/docs: interactive API contracts.
- /api/v1/openapi.json: machine-readable OpenAPI.

In another terminal:

```sh
cd app
flutter pub get --enforce-lockfile
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000
```

The example URL reaches the host from the standard Android emulator. For a physical phone, use a reachable development API address. Debug Android builds allow local HTTP; profile/release builds require HTTPS. Omit API_BASE_URL to explore the interface without a backend.

To sign in, configure the backend Firebase project and trusted Application Default Credentials, seed the synthetic accounts, and provide the app's public `FIREBASE_API_KEY` alongside `API_BASE_URL`. See [authentication setup](docs/authentication.md). With no configuration, the interface previews remain available in debug builds.

See the [benchmark guide](evaluation/README.md) for fixture regeneration/evaluation and
[PDF/OCR guide](docs/document-processing.md) for bounded processing and container commands.
Page-processing success does not establish row extraction accuracy; that remains unmeasured.

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
