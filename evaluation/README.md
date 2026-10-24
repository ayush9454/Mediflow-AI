# Synthetic laboratory benchmark

Ticket 03 establishes data and measurement. Ticket 08's
[development results](reports/laboratory-development.md) measure the real pipeline
on development data only. The 95% strict row precision and recall target is a later
held-out release gate. These forty
invented documents support a college demonstration, not a clinical effectiveness claim.

## Reproduce

From the repository root, with the documented Python 3.12 toolchain:

```sh
uv sync --project backend --locked --extra dev --extra evaluation
backend/.venv/bin/python -m mediflow.benchmark prepare
```

This one command regenerates all forty PDFs, annotations, a hash manifest, and
`evaluation/generated/report.json` and `report.md`. It makes no network, OCR or
model calls. Large raster fixtures and previews stay ignored. Source definitions,
the frozen hashes, and the preparation manifest/report are committed as text.

The output is separated into `development/`, `held-out/`, and `negative/`, each
with PDFs and its own `annotations.json`. Only `development/` is available to
prompt examples and tuning. Do not glob the generated directory as model input.
All patient labels use `SYNTHETIC-<document-id>` or its French equivalent; no
personal records, real names or identifiers are used.

## Frozen dataset v1

`fixtures/v1/` contains independently authored source fields, collection dates,
page placement, layout, medium, negative-case kind and random seeds. Ground truth
is constructed from these definitions, never from PDF text, OCR or AI output.
Missing units, intervals and dates remain null with `not_printed` annotation issues.
An absent printed flag remains null. References are invented printed strings;
they are not clinical advice or inferred ranges.

| Split | Digital | Scanned | Documents |
| --- | ---: | ---: | ---: |
| Development | 10 | 10 | 20 |
| Held-out valid | 5 | 5 | 10 |
| Negative | 7 | 3 | 10 |

The valid fixtures cover numeric and qualitative results, exact decimal precision,
`<`, `>`, `<=`, `>=`, null units/ranges/dates, printed flags, repeated analytes with
different results/dates, and tables spanning up to three pages. Three layouts vary
spacing, embedded Bitstream Vera typeface styles and table styling. This is a small set of authored templates;
it does not represent the variety of real laboratory layouts.

Valid scans are rasterized from the authored digital originals, converted to
grayscale, rotated slightly, contrast-reduced, blurred, speckled and JPEG-compressed.
The three bounded recipes and each seed are recorded in the generated manifest.
Scanned PDFs have image streams and no hidden laboratory text layer. Gold page
transcripts include headings, table labels, rows and footers, composed from the
same authored content used for rendering. They are not OCR performance results.

| Negative IDs | Expected rejection | Construction |
| --- | --- | --- |
| neg-01 | corrupt | Invalid PDF objects/xref |
| neg-02 | truncated | A PDF cut off before its object table/trailer |
| neg-03, neg-04 | unreadable | Destructive downsampling, blur; one also occluded |
| neg-05, neg-06 | unsupported_category | Radiology text and an appointment receipt |
| neg-07 | unsupported_language | French laboratory document |
| neg-08 | password_protected | Encrypted PDF, public fixture password `synthetic-fixture-only` |
| neg-09 | over_size | Three real lossless noisy raster pages; more than 10,000,000 bytes |
| neg-10 | over_pages | Eleven readable PDF pages |

The size limit is decimal 10,000,000 bytes; the page limit is ten. The password
fixture uses deterministic RC4 solely to test rejection of encrypted input. It is
not a storage encryption mechanism. No oversized binaries are committed.

`freeze.json` pins source SHA-256 hashes, dataset/render versions, and held-out PDF
hashes before extraction tuning exists. Regeneration refuses changed definitions
or held-out PDF bytes. Use the locked dependencies. An intentional source/render
change requires a new dataset version, an explained freeze, and new held-out data
if previous held-out results have already informed tuning. Do not silently refresh
the freeze to satisfy a failing check. Hashes detect changes; separation and an
explicit release flag enforce workflow, not a security boundary against developers.

## Evaluate a run

Write a JSON file with `dataset_version: "synthetic-labs-v1"` and a `documents`
array. Each document has `document_id`, `outcome` (`succeeded`, `rejected`, `failed`),
optional `rejection_reason` (the fixture kind above), and `rows` using the existing
`LaboratoryRow` wire schema. Row IDs and row order do not need to match annotations.
Map provider/pipeline outcomes into this offline taxonomy before evaluation.

```sh
backend/.venv/bin/python -m mediflow.benchmark evaluate \
  --split development --predictions /path/to/development-run.json \
  --output evaluation/generated/development-run
```

Every selected source document is scored. Missing documents count as failures and
their rows stay in recall denominators. Duplicate document IDs, unknown/out-of-split
IDs, wrong dataset versions and malformed rows are rejected. A zero denominator
produces null, never an invented perfect score. Predictions from a failed/rejected
run cannot earn correct rows; any emitted rows still count in precision denominators.

After prompts and processing are frozen, use the held-out split explicitly:

```sh
backend/.venv/bin/python -m mediflow.benchmark evaluate \
  --split held-out --release-evaluation --predictions /path/to/held-out-run.json \
  --output evaluation/generated/release-run
```

Never use held-out PDFs, annotations or evaluation feedback as prompt examples or
tuning data. Negative evaluation uses `--split negative` and checks rejection kinds
as well as failures and extra rows. No predictor, prompt or cloud adapter is added
by this ticket.

## Matching and observations

Only leading/trailing whitespace and runs of whitespace (including newlines and
nonbreaking spaces) are normalized. Case, decimal zeros, signs, inequalities, units,
range punctuation, negation, date text and null versus a printed string remain exact.
There is no unit conversion, date interpretation, case folding or clinical synonym map.

A strict row requires all six printed fields and supporting page evidence. Matching
is one-to-one within each document, independent of provider row IDs/order. Every
citation must exist on its claimed page, and at least one must contain the complete
annotated row quotation on the annotated page. Partial analyte-only citations fail;
a larger page quotation may pass if it includes the complete row. This conservative
benchmark policy measures full-row support, not semantic medical correctness.
All supplied quotations are checked, so adding a fabricated extra citation fails.

Strict precision is correct rows / emitted rows; strict recall is correct rows /
expected rows. Per-field scores independently match multisets scoped to the printed
analyte and collection date (the date score is scoped to analyte). This preserves
duplicate counts. Independent field scores do not establish complete-row correctness.
Null is scored as a field value, so inventing missing content fails.

The JSON report includes split and digital/scanned breakdowns, row/field counts,
precision/recall, evidence mismatches, missing documents, classification failures,
failure rates and measured latency. Optional per-document observations are:

- `latency_seconds`, `unsupported_summary_claims`, `flagged_rows`, `unresolved_rows`.
- `provider_cost_usd`, `student_credit_charge_usd`, `out_of_pocket_usd` separately.
- `resources`: objects with `name`, `unit`, and nonnegative `amount`, e.g.
  `provider_input_tokens` / `tokens`, `cpu_seconds` / `seconds`, `blob_bytes` / `bytes`.

Each observation reports its assessed-document count; missing values stay null.
Unsupported summary claims require a recorded human assessment. The harness cannot
prove their absence from unassessed free text. Zero out-of-pocket spend must be
reported separately from resource charges covered by student credit.

## Checks and licenses

```sh
backend/.venv/bin/python -m pytest backend/tests/test_benchmark.py
backend/.venv/bin/mypy --config-file backend/pyproject.toml backend/src
```

The evaluator is tested with known omissions, additions, changed printed fields,
duplicates, formatting-only changes, bad evidence and failed/missing runs. The
generation command is checked against source annotations, image-only scan structure,
rejection fixtures, freeze changes and reproducible hashes. Representative rendered
digital/scanned pages are visually inspected during implementation.

Evaluation dependencies are optional and excluded from the production dependency
set: ReportLab (BSD, with bundled Bitstream Vera font notices), Pillow (MIT-CMU),
pypdf (BSD-3-Clause), and pypdfium2
(Apache-2.0/BSD-3-Clause, with bundled PDFium/transitive notices). Preserve the exact
binary distribution's license notices if redistributing tools. The renderer uses
[ReportLab's canvas](https://docs.reportlab.com/reportlab/userguide/ch2_graphics/),
[pypdfium2's rendering API](https://pypdfium2.readthedocs.io/en/stable/python_api.html),
and [pypdf encryption](https://pypdf.readthedocs.io/en/stable/user/encryption-decryption.html).
