# 03: Build synthetic PDFs, independent annotations and evaluation harness

Status: completed
Progress: complete
Type: task
Blocked by: 02
Estimate: 8 hours
Target week: 1–2

## Outcome

Make extraction quality measurable before prompts and processing behavior are tuned.

## Context

- [Agreed specification](../spec.md)
- [Roadmap and gates](../roadmap.md)
- [Decisions and external-source checks](../decisions.md)
- [Ticket index](../README.md#implementation-tickets)

The small synthetic dataset supports a college benchmark, not a clinical effectiveness claim. If package selection affects generated PDFs, keep the fixture schema stable.

## Scope

- Create a reproducible manifest of forty synthetic documents: twenty development (ten digital/ten scanned), ten valid held-out (five digital/five scanned), and ten negative cases.
- Generate expected fields from independently authored fixture definitions. Include numeric/qualitative values, inequalities, missing units/ranges, printed flags, repeated analytes, collection dates and multipage tables.
- Create reproducibly degraded scanned versions and negative cases covering unsupported category/language, corrupt/unreadable PDFs, password protection and upload limits. Include realistic size/page-limit fixtures without adding large unnecessary binaries to source control.
- Implement strict row matching, row precision/recall, per-field metrics, evidence checks and split-specific reports. Document formatting-only normalization; omitted and additional rows must count.
- Freeze/version the held-out set and keep it out of model prompt examples and tuning runs. Add result fields for latency, failures, unsupported summary claims and consumed resources.

## Acceptance criteria

- [x] Manifest counts match the agreed 20/10/10 split, and all names/identifiers/content are synthetic.
- [x] Ground truth is independent of AI output and traceable to fixture definitions.
- [x] A known missing row lowers recall; an invented row lowers precision; a changed unit/value/inequality fails the strict match.
- [x] One command regenerates fixtures and produces a machine-readable and Markdown evaluation report with sample counts and digital/scanned breakdowns.
- [x] The held-out manifest/version is fixed before extraction tuning begins; no measured accuracy claim is made yet.

## Verification

Run harness checks using deliberately correct, omitted, extra and altered rows. Inspect representative rendered digital/scanned PDFs and verify annotations against their source fixture.

## Implementation record

Completed locally on 2026-10-23. Implementation commits: `dcb779d` and `789ac6a`.

### Changes

- Added the isolated offline `mediflow.benchmark` package and [benchmark guide](../../../evaluation/README.md). It does not run from the production API or worker.
- Independently authored, entirely synthetic source definitions produce 20 development documents (10 digital/10 scanned; 112 rows), 10 held-out valid documents (5 digital/5 scanned; 66 rows), and 10 negative documents (7 digital/3 scanned). Source definitions retain exact printed strings, nulls, dates, flags, repeated analytes and page placement.
- Added three layouts with embedded fonts and deterministic scan recipes covering grayscale, rotation, contrast, blur, noise and JPEG compression. Scans contain image streams without hidden laboratory text. Native page content is composed once for rendering and independent complete annotation transcripts; gold values never come from OCR or AI output.
- Added corrupt, truncated, unreadable/occluded, unsupported category/language, encrypted, over-size and over-page-limit fixtures. The oversized file is a real three-page raster PDF of 19,828,518 bytes; the page-limit fixture has eleven pages. Large generated artifacts remain ignored.
- Added whitespace-only normalization, one-to-one strict matching, row precision/recall, independent per-field metrics, source-page/quotation checks, split and medium breakdowns, failure/classification counts, and latency/summary/flag/resource observations. Missing documents remain in denominators; unassessed observations remain null. Student-credit charges and out-of-pocket spend are separate.
- Frozen `synthetic-labs-v1` source hashes and all ten held-out PDF hashes before any extraction tuning. Default evaluation selects development only; held-out evaluation requires an explicit release flag. The held-out set is excluded from prompt examples and tuning by the documented workflow.
- Added locked optional evaluation dependencies and CI installation. Existing dependency versions and shared wire contracts are unchanged.

### Reproduce and verify

From the repository root:

```sh
uv sync --project backend --locked --extra dev --extra evaluation
backend/.venv/bin/python -m mediflow.benchmark prepare
backend/.venv/bin/python -m pytest backend/tests/test_benchmark.py
```

The generation command writes all forty PDFs, separate split annotations, a machine-readable manifest and JSON/Markdown preparation reports under ignored `evaluation/generated/`. Committed snapshots: [manifest](../../../evaluation/manifest.json), [JSON report](../../../evaluation/reports/preparation.json), and [Markdown report](../../../evaluation/reports/preparation.md).

- All **48 backend tests** pass, including **24 benchmark tests**. Controlled omission/addition/alteration checks reduce the appropriate scores; duplicates cannot reuse expected rows; failed runs cannot earn correct rows; missing documents count as failures.
- Native annotations and complete transcripts match the actual pages for all 15 digital fixtures. All valid scan pages have images and no hidden text. Parser/encryption checks verify real malformed, password, size and page-limit conditions.
- Two independent regenerations produce identical manifests and PDF hashes. Frozen definition changes and implicit held-out evaluation are refused. Review corrections preserve all forty original PDF hashes and the held-out freeze.
- Representative final digital/scanned pages, multipage continuations, French, unreadable and oversized fixtures were rendered and visually inspected. Fixed a row background overlapping the header during initial authoring, before finalizing the freeze.
- Ruff formatting/lint, mypy (15 backend source files), Python compilation and all eight generated contract artifact checks pass.
- All **11 Flutter tests** and **nine hosting-probe tests** pass. Their local socket tests required sandbox escalation; no cloud deployment was performed.

### Review

#### Standards

No actionable documented-standard or baseline-smell findings, including the follow-up review of the correction.

#### Spec

The first review found that an authentic full-page quotation containing headings was rejected by row-only annotation transcripts. A failing 0/7 regression reproduced the issue. Shared authored page composition now supplies complete transcripts; the regression passes 7/7, and the reviewer independently verified all 15 digital fixtures with full-page quotations. No outstanding findings.

### Limits and next work

**Extraction accuracy is not measured.** No OCR pipeline, model prompt or prediction run was used. The preparation report explicitly retains a null accuracy result; 95% precision/recall remains a later release target. Synthetic templates do not establish clinical or real-world accuracy. Summary assessments and consumed resources require observations from actual future runs.

Changes are committed locally on the current `main` branch. No push, remote CI execution or cloud deployment was performed. Pre-existing hosting work remains separate. Ticket 03 is complete; tickets 04 and 07 are now unblocked.

## Comments

- 2026-10-20: Created from the user-confirmed project plan. No implementation performed.

- 2026-10-23: Implemented ticket 03 following the user's `/implement ticket 3` instruction. Dataset, freeze, harness, generation/report commands, focused/full checks and both review axes are complete. Extraction accuracy remains unmeasured.
