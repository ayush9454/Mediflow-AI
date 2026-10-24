# 08: Implement structured laboratory extraction, validation and summaries

Status: in-progress
Type: task
Blocked by: 03, 06, 07
Estimate: 12 hours
Target week: 4

## Outcome

Turn page text into versioned, evidence-linked laboratory candidates without unsupported clinical interpretation.

## Context

- [Agreed specification](../spec.md)
- [Roadmap and gates](../roadmap.md)
- [Decisions and external-source checks](../decisions.md)
- [Ticket index](../README.md#implementation-tickets)

Do not log full model/document payloads. The 95% target is measured formally in ticket 14; do not present development performance as held-out accuracy.

## Scope

- Integrate the current benchmarked Gemini free model through a provider interface, versioned schema/prompt/model settings and server-only credentials.
- Extract printed analyte, numeric/qualitative result, unit, interval, abnormality flag, collection date and source page/quote. Preserve original strings, inequalities, uncertainty and missing fields.
- Validate schema/types, numeric syntax, page bounds, quote matching and detectable source inconsistencies; attach explicit field/row issues. Do not claim these checks establish semantic correctness.
- Generate source-grounded descriptive summaries from structured information; no diagnosis, treatment advice, inferred ranges, unit conversions or fabricated confidence percentages.
- Persist immutable candidate data and version/config/usage metadata through the durable job commit path.
- Translate quota/unavailable/provider/schema failures into safe states and bounded retry classifications. Treat document prompt injection as untrusted content and give the model no tools or clinical write access.

## Acceptance criteria

- [x] Development examples return schema-valid candidates with preserved printed data and valid source references, or an explicit processing failure.
- [x] Missing/conflicting information is flagged rather than filled with assumptions.
- [x] AI/provider versions and extraction resource use can be traced for every completed candidate.
- [x] Quota exhaustion/unavailability never returns a canned successful analysis or silently uses a paid model.
- [x] Development evaluation reports and error analysis guide improvements without using held-out examples.

## Verification

Run development benchmarks and cases for omitted ranges, inequalities, qualitative/negative results, wrong evidence, schema failure, prompt-injection text and quota exhaustion. Inspect summaries for unsupported claims.

## Implementation record

Implemented the `extract_laboratory` candidate interface, strict Gemini provider,
deterministic validation/structural summary, retained original provider output and
page evidence, generation/source/usage provenance, worker subprocess integration,
safe error/retry classification, server-only configuration and secure worker
deployment parameters. The three test interfaces were explicitly confirmed by the
user. No result approval or patient draft access was added.

The normal worker now invokes real processing and Gemini, while the existing
Firestore transaction retains immutable candidate and analysis-commit metadata.
A failing worker-interface test exposed dropped transient flags across the child
process boundary; the regression now passes. The first live JSON-Schema request
was rejected by the provider; the final inline nullable OpenAPI schema passed a
real request and is covered by an HTTP-interface regression test.

Verification so far: Linux backend suite **153 passed, one opt-in Firebase emulator
test skipped**, including real Tesseract; focused extraction checks **33 passed**
after an additional blank-field regression. Mypy checks **37 sources**; Ruff
lint/format, compileall and eight exported artifacts pass. Flutter **19 passed**,
analysis/format clean, Dart contract smoke passed. Temporary deployment guard
tests **2 passed**; hosting probe tests **9 passed**. Final two-axis review pending.

Live development evaluation: all **20** synthetic PDFs produced candidates using
real Linux OCR and real `gemini-3.5-flash-lite` calls; no held-out examples or gold
transcripts were model input. Strict row precision/recall: **63.06%/62.50%** overall,
**96.43%/96.43%** digital, **29.09%/28.57%** scanned. Scanned units/characters,
flags and one omitted row remain release-quality limitations. Quotes and fields
with deterministic discrepancies carry blocking issues; all OCR rows require
visual review. The scorer was not weakened. Ticket 14's held-out target is not
measured or claimed passed.

Evidence and reproduction:
[development report](../../../evaluation/reports/laboratory-development.md),
[machine-readable report](../../../evaluation/reports/laboratory-development.json),
[extraction guide](../../../docs/laboratory-extraction.md).
The successful run consumed **9,105 input / 15,747 output tokens**, mean **11.52 s**
and maximum **28.20 s** model/extraction latency, excluding reused OCR. Billing was
confirmed disabled with no linked account; provider pricing was $0 on the verified
free tier. This was local Linux OCR plus hosted Gemini, not a new Azure pipeline
deployment; no new Azure resources were created. Raw payloads and credentials stay
in ignored local state.

## Comments

- 2026-10-20: Created from the user-confirmed project plan. No implementation performed.

- 2026-10-24: Ticket 07 completed and all blockers satisfied. User confirmed all
  three proposed testing interfaces and authorized continuing ticket 08.
