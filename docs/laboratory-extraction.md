# Laboratory extraction

`mediflow.laboratory.extract_laboratory(lease, document, provider)` turns accepted
page evidence into an immutable, unreviewed candidate. `LaboratoryProcessor` runs
real bounded PDF/OCR first; the normal worker's subprocess runs this pipeline.
Existing Firestore lease, expiry, attempt, version and result-commit transactions
remain authoritative. Extraction cannot assign or approve a patient result.

## Configuration

Set these only on the backend/worker:

```sh
MEDIFLOW_GEMINI_MODEL=gemini-3.5-flash-lite
MEDIFLOW_GEMINI_FREE_TIER_CONFIRMED=true
GEMINI_API_KEY=<backend-secret>
```

The confirmation means the owner verified this key's project uses the free tier
with billing disabled. It does not change Google billing. Before the development
benchmark, the existing project was rechecked: billing disabled, no linked billing
account, 15 requests/minute, 250,000 input tokens/minute and 500 requests/day.
Recheck eligibility and quotas before deployment. Other models, missing keys and
missing confirmation fail as `integration_not_configured`; there is no fallback.
Secrets are excluded from settings representations, client contracts and logs.

`backend/jobs.bicep` accepts the key as a secure parameter and installs it only in
the worker's secret environment. The reconciler needs no AI key. The offline
`python -m mediflow.worker --check-config` reports configuration presence, not
cloud availability or full endpoint readiness.

The `CandidateProvider` interface separates Gemini HTTP/schema handling from
workflow/storage. Requests use a fixed HTTPS endpoint and an API-key header,
without environment proxies, redirects, tools or automatic retries. The system
instruction is separate from JSON-encoded untrusted page data. Generation uses a
JSON schema, temperature zero, minimal thinking and an 8,192-token output ceiling.

Google's [structured-output guide](https://ai.google.dev/gemini-api/docs/structured-output),
[REST contract](https://ai.google.dev/api/generate-content),
[thinking controls](https://ai.google.dev/gemini-api/docs/thinking) and
[pricing](https://ai.google.dev/gemini-api/docs/pricing) were checked on 2026-10-24.
Schema compliance does not prove field correctness.

## Preserved data and checks

Printed analyte, result, unit, interval, flag and collection date stay strings.
No conversions, inferred ranges, date interpretation, diagnosis, treatment or
confidence percentage is generated. Required nullable fields must be present;
unknown properties, wrong types, malformed JSON, empty rows and truncated output
fail explicitly.

Each candidate retains exact structured provider output, validated rows,
original/native page text and native/OCR origin. Invalid page references remain
in the provider output, are excluded from usable evidence and receive blocking
issues. Quotes use whitespace-only normalization. Fields must also occur with
character boundaries in valid cited quotes: `0.5` cannot claim support from
`0.50`. Matching proves traceability, not table association or medical correctness.

Missing optional values, OCR uncertainty, suspected embedded instructions and
ambiguous numeric dates remain visible. Malformed numeric strings, wrong pages
or quotes, unsupported fields and different values for a repeated analyte/date
are flagged. Repetition can be legitimate; every proposal remains for review.
Neither nulls nor matching quotes guarantee that nothing was omitted.

The summary deterministically describes extracted row/page/issue counts and the
need for doctor review; source-linked rows contain the extracted information.
Provenance records requested/returned model versions, pipeline/prompt versions,
prompt/schema hashes, generation settings, source hash, page-processing time/RSS,
and provider input/output/thinking/total tokens and latency.

## Bounds and failures

The ten-page/10,000,000-byte document contract still applies. Extraction also
limits source text to 60,000 characters, rows to 100, citations to ten per row,
printed fields to 500 characters, quotes to 5,000 characters, HTTP response bytes
to 300,000, structured provider output to 200,000 characters, and the serialized
candidate to 750,000 bytes. Nothing is silently truncated. PDF processing gets up
to 200 seconds of the remaining job budget. HTTP inactivity timeouts are capped
at 40 seconds and the remaining lease; the subprocess enforces the whole-job
deadline.

| Failure | Durable behavior |
| --- | --- |
| 429 | `quota_exhausted`; no automatic retry |
| Timeout, network error, 408, 5xx | `temporarily_unavailable`; existing three-attempt backoff |
| 401, 403, 404, absent configuration | `integration_not_configured`; no automatic retry |
| Malformed, blocked, incomplete or invalid output | `provider_invalid_response`; no automatic retry |
| Extraction/candidate bound | `processing_limit_exceeded`; no automatic retry |
| Unsupported/rejected PDF | `invalid_upload`; document rejection |

429 is conservative because daily exhaustion cannot be reliably distinguished
from short rate limits by status alone. Authorized manual reprocessing may start
a fresh run after availability returns. Diagnostics exclude raw errors, keys and
document payloads. The test adapter requires an explicit flag and test environment.

## Development evaluation

With real Tesseract, processing/evaluation extras and backend configuration:

```sh
backend/.venv/bin/python -m mediflow.laboratory \
  --output evaluation/generated/laboratory-development
```

Only twenty frozen synthetic development documents are loaded, with five seconds
between requests and no per-document retries. The command stops on quota
exhaustion and includes missing/failed documents in scoring. Candidate/prediction
files are separate from sanitized aggregate reports. Held-out examples are never
loaded. `--pdfs` optionally supplies PDFs; `--page-results` explicitly reuses real
`ProcessingResult` JSON named `dev-NN.json`, each verified against its PDF hash.
This permits Linux OCR followed by host-side Gemini calls without using gold
transcripts as OCR. Model latency and reused page processing are distinguished.
Supplied PDFs must match the frozen synthetic manifest before any provider call.

The ticket-03 strict-row/field scorer measures results; unassessed summary claims
remain null. Token usage is separate from free-tier zero-dollar pricing. The
ticket-14 held-out 95% release target remains a separate gate.
See [the measured development report](../evaluation/reports/laboratory-development.md):
scanned character/unit preservation remains a substantial quality limitation.
