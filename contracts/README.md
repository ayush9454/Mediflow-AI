# Shared API contracts

The source of truth is [backend/src/mediflow/contracts.py](../backend/src/mediflow/contracts.py) and the FastAPI routes. Generated artifacts:

- [OpenAPI](openapi.json): versioned endpoints, request/response bodies, bearer authentication and idempotency headers.
- [Model schemas](models.schema.json): strict Pydantic models, including worker/analysis types.
- [Dart models](../app/lib/core/contracts/contracts.g.dart): generated typed JSON parsing/serialization.
- [Examples](examples): synthetic contract fixtures used in Python/Dart checks; never served as analysis results.

From the repository root, with backend dependencies available:

```sh
backend/.venv/bin/python tools/export_contracts.py
backend/.venv/bin/python tools/export_contracts.py --check
```

Dart models preserve wire types but do not replace backend semantic validation or authorization. Generated lists are unmodifiable. The Python model validators enforce constraints such as rejection reasons, distinct result kinds and explicit missing evidence.

Public health endpoints work. With Firebase configured, protected routes verify real ID tokens and current server-owned account permissions; `/me` returns the trusted account and permitted report metadata is readable. Missing/invalid identities and forbidden resource relationships are denied. An unconfigured identity adapter fails closed. With configured Firestore and private Azure Blob storage, registration, bounded upload, stored-byte verification and authorized document streaming are implemented; see [private uploads](../docs/private-uploads.md). Completion returns a durable queued job intent. Queue dispatch, clinical results and review operations remain pending; OpenAPI availability does not establish full workflow readiness.

The current schema version is 1.0. Keep printed laboratory values as strings, keep processing and review states independent, and require explicit versions when reviewing or assigning. Review submissions carry the expected analysis, case and prior review versions; zero means no prior review. Report metadata exposes the current case and review versions, and case lists also expose review versions. Review versions increase monotonically per report, including across reprocessing; they are never reset for a replacement analysis. The future review operation must check these atomically against server records, including the current assignment.
