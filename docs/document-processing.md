# Bounded PDF page evidence

Ticket 07 adds `mediflow.processing.process_pdf(source_bytes, limits=Limits())`.
It returns page evidence and explicit outcomes; it does not extract laboratory rows,
interpret results, call an LLM, approve records, or start a durable queue worker.
The durable worker entry point is integrated by ticket 06. The actual laboratory
candidate provider remains unavailable until ticket 08; page extraction and OCR
continue to be independently verifiable through this module.

Each page has its original, unnormalized extracted text, a one-based page number,
`native` or `ocr` origin, the native text even when OCR is selected, measured native
adequacy fields, and flags. The source SHA-256 identifies the untouched original PDF.
All text has `trust: untrusted_document_data`. Embedded-instruction detection adds
an inspectable flag; it is not an exhaustive instruction detector. Consumers must
keep every page as document data, never as system instructions or executable input.

`PageText.supports_quote()` and `normalized_text` trim and collapse Unicode whitespace
only. Case, punctuation, signs, inequalities, decimal zeros, units, dates and negation
remain exact. Matching proves text traceability, never table association or medical
correctness. No parser or OCR heuristic is exposed as a confidence percentage.

## Native adequacy and category checks

Native text needs at least 40 alphabetic characters, eight whitespace-delimited words,
a printable non-whitespace ratio of at least 0.98, and no replacement character.
These are observable routing heuristics, not accuracy measures. A page containing
raster objects covering at least 15% of page area also gets full-page OCR, so a
readable digital heading does not hide a scanned table. Overlapping raster areas are
summed conservatively. OCR uses Tesseract English LSTM, automatic segmentation
(`--oem 1 --psm 3`), and always adds `ocr_requires_visual_review`. OCR failing the same
adequacy check adds `unreadable` and rejects the document; no fabricated text is added.

The conservative English rule classifier requires a laboratory heading, result and
reference headers, and a recognizable analyte. Explicit radiology/appointment/receipt
vocabulary rejects unsupported documents; recognizable unsupported-language vocabulary
rejects those examples. Other documents return `uncertain_category`. This initial
classifier can reject unfamiliar valid laboratory formats and does not prove language,
medical correctness, or resistance to adversarial category spoofing. Future consumers
must preserve uncertainty and the doctor's original-page inspection.

## Outcomes and limits

`outcome` is `succeeded`, `rejected`, or `failed`; `reason` is a sanitized code.
Rejections include `corrupt` (including truncation), `encrypted`, `over_size`,
`over_pages`, `render_limit`, `unreadable`, `unsupported_category`,
`unsupported_language`, and `uncertain_category`. Operational failures include
`timeout`, `resource_limit`, `ocr_unavailable`, `ocr_failed`, and `processing_failed`.
Invalid and unsupported documents should not enter automatic retry loops. Ticket 06
owns durable attempts/retry policy and ticket 08 owns laboratory row validation.

| Resource | Upper limit |
| --- | --- |
| Original bytes | 10,000,000 decimal bytes |
| Pages | 10 |
| Raster resolution | 150 DPI, reduced to meet pixel/dimension limits |
| Raster pixels | 4,000,000/page; each side at most 2,000 pixels at default settings |
| PDF page dimensions | Positive and at most 14,400 points on each side |
| Text | 100,000 characters/page |
| OCR processes | One page at a time; one document per caller process |
| Tesseract threads | `OMP_THREAD_LIMIT=1`, `OMP_NUM_THREADS=1` |
| Per-page OCR deadline | 30 seconds |
| Document deadline | 240 seconds including local concurrency wait |
| Linux parser/OCR address space | 768 MiB per process |
| Linux parser/OCR CPU time | 240 seconds per process |
| Azure job allocation | Requested 0.5 vCPU, 1 GiB cgroup memory, max job parallelism one |
| Container deadline | 300 seconds; application deadline leaves cleanup time |

`Limits` allows stricter values and refuses values above these ceilings. PDF parsing,
native extraction, rendering and OCR all run in an isolated subprocess group. The
caller kills that entire group on timeout and after any exit to remove descendants.
Tesseract inherits Linux address-space/CPU bounds; container cgroups bound the
aggregate workload. The local acceptance gate enforces a hard 0.5-core limit.
Azure Consumption has exposed both 0.5-core and 4-core hard quotas for the
requested 0.5-vCPU allocation. Report each run's actual quota; only describe Azure
timing as strict-cap timing when its observed quota is 0.5 cores. Memory is
hard-limited to 1 GiB in both environments. Run one worker
process per job and max executions /
replica parallelism one: the Python semaphore is process-local, not a distributed
scheduler. Do not expose this synchronous function on an API event loop.

The original bytes are copied into a private temporary directory and never rewritten.
Page raster/OCR files are overwritten sequentially and removed with the temporary
directory. Persist returned evidence in private artifact storage when ticket 06
integrates processing. No PDF text is printed by the runner or benchmark summary.
The `extract` CLI explicitly writes text-bearing evidence to its requested private
output file; protect it like the original.

## Worker container and repeatable development checks

API and OCR images are separate. `backend/Dockerfile.worker` installs Tesseract and
English trained data plus the optional `processing` Python dependencies. It retains
Debian package copyrights and Python distribution notices under `/service/licenses`
(and the installed packages' original paths). The API image has no OCR tools.

```sh
uv sync --project backend --locked --extra dev --extra evaluation --extra processing
# Only development.json and negative.json are read; held-out PDFs/annotations stay unused.
backend/.venv/bin/python -m mediflow.processing fixtures evaluation/fixtures/v1 \
  --output .tooling/processing-fixtures
backend/.venv/bin/python -m pytest backend/tests/test_processing.py
backend/.venv/bin/mypy --config-file backend/pyproject.toml backend/src

docker build -f backend/Dockerfile.worker -t mediflow-worker backend
mkdir -p .tooling/processing-results
docker run --rm --cpus=.5 --memory=1g --pids-limit=64 \
  -v "$PWD/.tooling/processing-fixtures:/fixtures:ro" \
  -v "$PWD/.tooling/processing-results:/results" \
  mediflow-worker python -m mediflow.processing benchmark /fixtures \
  --output /results/processing.json
```

The generator adds five supplemental development fixtures: image-only scan, alternating
native/scanned pages, scanned content with a native heading, ten scanned pages, and
an unreadable blank raster. These do not modify frozen dataset v1. The benchmark
accepts only `dev-*`, `neg-*`, and `supplemental-*` filenames in the selected directory;
it never recursively globs the combined evaluation output or accepts `hold-*` names.
This is a workflow guard, not access control against deliberate renaming.

The JSON summary contains page origins/flags, SHA-256, elapsed seconds, CPU seconds,
per-process high-water RSS, Tesseract version, platform and Linux cgroup
memory limit, peak memory and CPU quota/period. The `cgroup_memory_max`,
`cgroup_memory_peak` and `cgroup_cpu_max` fields use the same units for cgroup v2
and v1. For v1 they read `memory.limit_in_bytes`, `memory.max_usage_in_bytes`,
`cpu.cfs_quota_us` and `cpu.cfs_period_us` from their controller directories.
RSS is the maximum parser or child peak,
not simultaneous aggregate memory; use container `memory.peak` for the aggregate.
An unbounded host run cannot establish the Azure resource acceptance gate. The
40-document row benchmark and 95% held-out precision/recall remain separate,
unmeasured release gates.

Primary implementation references: [pypdf text extraction](https://pypdf.readthedocs.io/en/stable/user/extract-text.html),
[pypdfium2 rendering and object lifecycle](https://pypdfium2.readthedocs.io/en/stable/python_api.html),
and [Tesseract CLI](https://tesseract-ocr.github.io/tessdoc/Command-Line-Usage.html).
Counter semantics: [Linux v1 memory controller](https://docs.kernel.org/admin-guide/cgroup-v1/memory.html)
and [CFS bandwidth control](https://docs.kernel.org/scheduler/sched-bwc.html).

## Recorded measurements

The 2026-10-23 local Linux/amd64 worker run (Rosetta on an ARM Mac) used Tesseract
5.5.0, exactly 0.5 vCPU / 1 GiB, and a PID ceiling of 64. All 20 development, ten
negative, and five supplemental documents produced the expected processing outcomes.
The ten-page image-only PDF took 10.71 seconds; the aggregate cgroup memory peak
across the run was 172,625,920 bytes (164.6 MiB), with no OOM. See
[`page-processing.json`](../evaluation/reports/page-processing.json) for full sanitized
observations. This establishes the local capped image's compatibility with the
modeled allocation. Actual Azure job execution is recorded separately when verified.

## Observed OCR limits

Representative scanned-development and native-heading-over-raster pages were
rendered and compared with real Tesseract output. The raster table was processed
through OCR even when its heading had adequate native text. Observed character
confusions included `g/dL` becoming `g/dl` and `10^9/L` becoming `10*9/L`.
The output preserves these original OCR strings and marks OCR pages for visual
review. This confirms the need for later field validation and doctor review;
processing success is not an extraction-fidelity or clinical-accuracy claim.
