# Synthetic extraction evaluation

Dataset: `synthetic-labs-v1`

| Split / medium | Samples | Correct / expected / predicted | Precision | Recall | Failures |
| --- | ---: | --- | ---: | ---: | ---: |
| development/all | 20 | 65 / 112 / 111 | 0.5856 | 0.5804 | 0 |
| development/digital | 10 | 54 / 56 / 56 | 0.9643 | 0.9643 | 0 |
| development/scanned | 10 | 11 / 56 / 55 | 0.2000 | 0.1964 | 0 |

Missing submissions count as failures and remain in recall denominators.
Null observations mean unmeasured. Complete field, evidence, classification, latency and resource metrics are in report.json.
This small synthetic benchmark does not establish real-world clinical accuracy.

## development/all

| Field | Correct / expected / predicted | Precision | Recall |
| --- | --- | ---: | ---: |
| analyte | 109 / 112 / 111 | 0.9820 | 0.9732 |
| result | 107 / 112 / 111 | 0.9640 | 0.9554 |
| unit | 84 / 112 / 111 | 0.7568 | 0.7500 |
| reference_range | 104 / 112 / 111 | 0.9369 | 0.9286 |
| abnormality_flag | 96 / 112 / 111 | 0.8649 | 0.8571 |
| collection_date | 109 / 112 / 111 | 0.9820 | 0.9732 |

Evidence mismatches: 46. Classification failures: 0. Missing submissions: 0.

Latency in seconds: {"max": 28.19661225000027, "mean": 11.519311327150103, "measured_documents": 20}.

| Observation | Total | Assessed documents |
| --- | ---: | ---: |
| unsupported_summary_claims | unmeasured | 0 |
| flagged_rows | 102 | 20 |
| unresolved_rows | 102 | 20 |
| provider_cost_usd | 0.0 | 20 |
| student_credit_charge_usd | unmeasured | 0 |
| out_of_pocket_usd | 0.0 | 20 |

Resource observations: 20 documents.

- provider_input_tokens: 9105.0 tokens
- provider_output_tokens: 15747.0 tokens
- provider_thinking_tokens: 0.0 tokens

## development/digital

| Field | Correct / expected / predicted | Precision | Recall |
| --- | --- | ---: | ---: |
| analyte | 56 / 56 / 56 | 1.0000 | 1.0000 |
| result | 56 / 56 / 56 | 1.0000 | 1.0000 |
| unit | 56 / 56 / 56 | 1.0000 | 1.0000 |
| reference_range | 54 / 56 / 56 | 0.9643 | 0.9643 |
| abnormality_flag | 55 / 56 / 56 | 0.9821 | 0.9821 |
| collection_date | 56 / 56 / 56 | 1.0000 | 1.0000 |

Evidence mismatches: 2. Classification failures: 0. Missing submissions: 0.

Latency in seconds: {"max": 28.19661225000027, "mean": 12.716514683400145, "measured_documents": 10}.

| Observation | Total | Assessed documents |
| --- | ---: | ---: |
| unsupported_summary_claims | unmeasured | 0 |
| flagged_rows | 47 | 10 |
| unresolved_rows | 47 | 10 |
| provider_cost_usd | 0.0 | 10 |
| student_credit_charge_usd | unmeasured | 0 |
| out_of_pocket_usd | 0.0 | 10 |

Resource observations: 10 documents.

- provider_input_tokens: 4737.0 tokens
- provider_output_tokens: 7781.0 tokens
- provider_thinking_tokens: 0.0 tokens

## development/scanned

| Field | Correct / expected / predicted | Precision | Recall |
| --- | --- | ---: | ---: |
| analyte | 53 / 56 / 55 | 0.9636 | 0.9464 |
| result | 51 / 56 / 55 | 0.9273 | 0.9107 |
| unit | 28 / 56 / 55 | 0.5091 | 0.5000 |
| reference_range | 50 / 56 / 55 | 0.9091 | 0.8929 |
| abnormality_flag | 41 / 56 / 55 | 0.7455 | 0.7321 |
| collection_date | 53 / 56 / 55 | 0.9636 | 0.9464 |

Evidence mismatches: 44. Classification failures: 0. Missing submissions: 0.

Latency in seconds: {"max": 24.71890595800005, "mean": 10.32210797090006, "measured_documents": 10}.

| Observation | Total | Assessed documents |
| --- | ---: | ---: |
| unsupported_summary_claims | unmeasured | 0 |
| flagged_rows | 55 | 10 |
| unresolved_rows | 55 | 10 |
| provider_cost_usd | 0.0 | 10 |
| student_credit_charge_usd | unmeasured | 0 |
| out_of_pocket_usd | 0.0 | 10 |

Resource observations: 10 documents.

- provider_input_tokens: 4368.0 tokens
- provider_output_tokens: 7966.0 tokens
- provider_thinking_tokens: 0.0 tokens

## Development findings

This is a development run, not the held-out release evaluation. All 20 documents
returned schema-valid candidates. Strict row precision/recall were **58.56% /
58.04%** overall: **96.43% / 96.43%** digital and **20.00% / 19.64%** scanned.
There were 112 expected and 111 predicted rows, with 65 complete correct rows.
The 95% held-out release target remains unmeasured and these development results
are insufficient to claim release quality. The scorer was not weakened.

The clearest scanned weakness is printed units: 28/56 field matches (50% recall),
versus 56/56 for digital inputs. Synthetic examples include `mg/dL` extracted as
`mg/dl.`, `U/L` as `UA`, and `10^9/L` as `10*9/L`. Lowercasing, punctuation changes
and lost superscript notation remain strict errors. Numeric results, printed
flags and one omitted scanned row also need improvement. Two digital rows failed
strict matching; their reference-range and flag errors remain in the report.

Valid OCR quotations can support inaccurate text relative to the original PDF.
The deterministic validator deliberately does not repair OCR by guessing units or
reference intervals. Every scanned row receives an OCR visual-review issue.
Improve source-character preservation and extraction on development data before
freezing the pipeline for ticket 14; do not tune against held-out documents or
normalize away these mismatches.

All twenty structural summaries were inspected: they describe row/page/issue
counts and require doctor review, with no diagnosis or treatment claims. The
scorer's optional free-text assessment fields remain null; the separate summary
review is recorded in the JSON report.

## Resources and reproduction

The final successful run made 20 requests to `gemini-3.5-flash-lite` with the
recorded prompt/schema hashes and minimal thinking. Usage: **9,105 input tokens**,
**15,747 output tokens**, zero reported thinking tokens. Mean extraction latency
was **11.52 s**, maximum **28.20 s**, excluding reused PDF/OCR processing and the
five-second inter-request pause. Free-tier provider cost was $0; this local run
does not measure Azure student-credit consumption.

Real Linux PDF/OCR was run separately under 0.5 vCPU / 1 GiB / 64 PIDs. The live
command verified every cached page result against its synthetic PDF SHA-256.
No gold transcript was supplied to Gemini. No held-out example was loaded. Raw
candidate files, page text and account identifiers stay in ignored local state.
See [the extraction guide](../../docs/laboratory-extraction.md) for the repeatable
command and environment settings.

The first live request format using JSON Schema references returned HTTP 400.
The final inline OpenAPI nullable schema succeeded; a provider-interface
regression test covers that request contract. Those interrupted diagnostic
requests are excluded from the final twenty-document timing/quality figures.

The final deterministic validator was replayed against the exact recorded model
responses after review fixes, with zero additional provider calls. Unsupported
quotations were removed from usable evidence while retained verbatim in original
provider output; numeric-looking strings are checked independently of model type.
Removing unsupported quotations reduced complete correct rows from 70 to 65;
five original quotations matched the authored transcript but not actual OCR text.
The scorer was unchanged and the lower final scores are reported above.
